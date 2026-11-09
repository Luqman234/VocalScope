# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Deterministic segmentation of an interpretation copy; original F0 stays intact."""
from dataclasses import asdict
import hashlib,json,uuid
from time import perf_counter
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks
from .models import NoteEvent,Boundary
from .pitch_center import pitch_center


def segments(result,features,config,source_sha256):
    begin=perf_counter();t=result.time_seconds;m=result.midi_pitch;duration=result.metadata.duration_seconds
    if len(t)>1:hop=float(np.median(np.diff(t)))
    else:hop=result.config.hop_length/result.config.sample_rate
    valid=result.voiced.copy() & (t<duration)
    # A short articulatory gap can belong to a note. Only the interpretation mask
    # bridges it; F0 remains NaN and pitch coverage records the missing frames.
    if config.method!='naive':
        gaps=np.flatnonzero(np.diff(np.r_[True,valid,True].astype(int)))
        for a,b in zip(gaps[::2],gaps[1::2]):
            if a>0 and b<len(m) and (b-a)*hop<=config.bridge_gap and abs(m[a-1]-m[b])<config.pitch_change:
                valid[a:b]=True
    starts=np.flatnonzero(np.diff(np.r_[False,valid].astype(int))==1)
    ends=np.flatnonzero(np.diff(np.r_[valid,False].astype(int))==-1)+1
    boundaries=list(features.candidates) if config.method=='combined' else []
    intervals=[]
    for a,b in zip(starts,ends):
        cuts=[(a,'voiced_start')]
        x=m[a:b].copy();finite=np.isfinite(x)
        if not finite.any():continue
        x[~finite]=np.interp(np.flatnonzero(~finite),np.flatnonzero(finite),x[finite])
        if config.method=='naive':
            changes=np.flatnonzero(np.diff(np.rint(x))!=0)+1
            cuts.extend((a+int(i),'rounded_frame_change') for i in changes)
        else:
            w=max(2,int(round(config.stability_window/hop)))
            context=max(w,int(round(.18/hop)))
            smooth=median_filter(x,size=w//2*2+1,mode='nearest')
            jump=np.zeros(len(x))
            for i in range(context,len(x)-context):
                left=smooth[i-context:i];right=smooth[i:i+context]
                # Stable plateaus distinguish note steps from slides/vibrato.
                if np.subtract(*np.percentile(left,[75,25]))<.5 and np.subtract(*np.percentile(right,[75,25]))<.5:
                    jump[i]=abs(float(np.median(right)-np.median(left)))
            peaks,_=find_peaks(jump,height=config.pitch_change,distance=max(1,w))
            cuts.extend((a+int(i),'stable_pitch_change') for i in peaks)
            boundaries.extend(Boundary(float(t[a+i]),'pitch_plateaus',float(jump[i]),'pitch_change') for i in peaks)
            if config.method=='combined':
                for onset in features.candidates:
                    i=int(np.searchsorted(t,onset.time_seconds))
                    if a<i<b and (i-a)*hop>=config.min_duration and (b-i)*hop>=config.min_duration:
                        if not any(abs(t[i]-t[j])<config.stability_window for j,_ in cuts):
                            cuts.append((i,onset.source))
        cuts=sorted(set(cuts));cuts.append((b,'end'))
        for (s,why),(e,_) in zip(cuts,cuts[1:]):
            start=max(0,float(t[s]-hop/2));end=min(duration,float(t[e-1]+hop/2))
            intervals.append((s,e,start,end,why))
    segmentation_seconds=perf_counter()-begin;center_begin=perf_counter();notes=[];rejected=[]
    for a,b,start,end,why in intervals:
        a,b=int(a),int(b)
        values=m[a:b];coverage=float(np.isfinite(values).mean())
        flat=float(np.median(features.flatness[(features.times>=start)&(features.times<end)])) if np.any((features.times>=start)&(features.times<end)) else 1.
        if config.method!='naive' and (end-start<config.min_duration or coverage<config.min_coverage or flat>config.max_flatness):
            rejected.append({'start_seconds':start,'end_seconds':end,'reason':'duration/coverage/flatness','coverage':coverage,'flatness':flat});continue
        # Trim only center calculation by 10% (at most 30ms), never the contour.
        trim=min(int(.03/hop),int((b-a)*.1));center_values=values[trim:len(values)-trim] if trim else values
        if not np.isfinite(center_values).any():center_values=values
        center,key,cents,flags=pitch_center(center_values)
        if coverage<1:flags=(*flags,'bridged_unvoiced_frames')
        identity=json.dumps([source_sha256,asdict(config),a,b],sort_keys=True)
        identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,hashlib.sha256(identity.encode()).hexdigest()))
        notes.append(NoteEvent(identifier,start,end,key,center,cents,config.velocity,coverage,a,b,why,False,flags))
    return tuple(notes),tuple(sorted(boundaries,key=lambda x:x.time_seconds)),{'segmentation_seconds':segmentation_seconds,'pitch_center_seconds':perf_counter()-center_begin,'rejected_segments':rejected}
