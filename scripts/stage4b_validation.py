# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Actual captured PCM timing; fixed tolerances declared before experimentation."""
from dataclasses import asdict
from pathlib import Path
from time import monotonic,sleep
import argparse,json,tempfile
import numpy as np
import soundfile as sf
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import *

TOLERANCE_SAMPLES=2

def wait(predicate,timeout=8):
    end=monotonic()+timeout
    while not predicate() and monotonic()<end:sleep(.005)
    if not predicate():raise RuntimeError('Diagnostic timeout')


def pcm_peaks(rows,channel):
    result=[];previous=-1;reset=True
    for pts,block in rows:
        if pts<previous:reset=True
        previous=pts
        for i in np.flatnonzero(abs(block[:,channel])>.005):
            time=pts/1e9+int(i)/48000;amp=float(abs(block[i,channel]))
            if not reset and result and 0<=time-result[-1][0]<.005:
                if amp>result[-1][1]:result[-1]=(time,amp)
            else:result.append((time,amp));reset=False
    return [t for t,_ in result]


def fixtures(directory,duration=3,events=(.25,.75,1.25,2.25),mono_piano=False):
    paths=[]
    for rate,channel,extension in [(44100,0,'wav'),(48000,1,'flac')]:
        y=np.zeros((rate*duration,1 if mono_piano and channel==1 else 2),dtype='float32')
        for time in events:y[round(time*rate),0 if y.shape[1]==1 else channel]=.25
        path=directory/f'{duration}-{channel}.{extension}';sf.write(path,y,rate,subtype='FLOAT' if extension=='wav' else 'PCM_24');paths.append(path)
    return paths


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--long-real-time',action='store_true',help='Run the 120s clock test at real-time speed (test sink, no speaker output).');args=parser.parse_args();rows=[]
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    for mono in [False,True]:
        vocal,piano=fixtures(root,mono_piano=mono)
        for offset,start in [(0.,0.),(0.,.6),(0.,.74),(0.,.76),(.2,.6),(-.1,.6)]:
            t=Transport(PlaybackConfig(sink='appsink',sink_sync=False))
            try:
                begin=monotonic();t.load(Session(vocal=Source(vocal),piano=Source(piano,offset))).result(12);load=monotonic()-begin;t.set_mix('mix').result(5)
                begin=monotonic();t.seek(start).result(5);seek_elapsed=monotonic()-begin;t.capture(True).result(3);t.play().result(3);wait(lambda:t.snapshot().state==State.PAUSED)
                captured=t.capture().result(3)
                if mono:captured=[(pts,np.column_stack((block[:,0]-block[:,1],block[:,1]))) for pts,block in captured]
                observed=[pcm_peaks(captured,c) for c in [0,1]];expected=[[e for e in [.25,.75,1.25,2.25] if e>=start],[e+offset for e in [.25,.75,1.25,2.25] if e+offset>=start]]
                errors=[]
                for actual,truth in zip(observed,expected):
                    if len(actual)!=len(truth):raise RuntimeError(f'Event count mismatch: {actual} vs {truth}')
                    errors.extend((np.array(actual)-truth)*48000)
                maximum=float(np.max(abs(np.array(errors)),initial=0.));assert maximum<=TOLERANCE_SAMPLES
                rows.append({'case':'alignment','mono_piano':mono,'offset_seconds':offset,'seek_seconds':start,'observed':observed,'expected':expected,'max_absolute_error_samples':maximum,'load_seconds':load,'seek_ack_seconds':seek_elapsed})
            finally:t.close().result(5);t.wait_closed()
    events=(1.,30.,60.,90.,119.);vocal,piano=fixtures(root,120,events)
    t=Transport(PlaybackConfig(sink='appsink',sink_sync=args.long_real_time,capture_seconds=120))
    try:
        t.load(Session(vocal=Source(vocal),piano=Source(piano))).result(12);t.set_mix('mix').result(5);t.capture(True).result(3);begin=monotonic();t.play().result(3);wait(lambda:t.snapshot().state==State.PAUSED,130 if args.long_real_time else 8)
        captured=t.capture().result(3);v=pcm_peaks(captured,0);p=pcm_peaks(captured,1);assert len(v)==len(p)==len(events)
        differences=(np.array(v)-np.array(p))*48000;assert max(abs(differences))<=TOLERANCE_SAMPLES
        rows.append({'case':'long_pcm_drift','duration_seconds':120,'elapsed_seconds':monotonic()-begin,'real_time_clock':args.long_real_time,'vocal_events':v,'piano_events':p,'relative_error_samples':differences.tolist(),'drift_change_samples':float(differences[-1]-differences[0]),'semantics':'Real-time Gst clock and capture sink, not physical speaker playback.' if args.long_real_time else 'Fast offline capture with one clock, not 120 seconds of physical speaker playback.'})
    finally:t.close().result(5);t.wait_closed()
    vocal,piano=fixtures(root)
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(vocal),piano=Source(piano))).result(8);t.set_mix('mix').result(5);t.set_loop(Loop(.6,.9)).result(5);t.capture(True).result(3);t.play().result(3);wait(lambda:t.snapshot().loop_count>=6,5);t.pause().result(3)
        captured=t.capture().result(3);v=pcm_peaks(captured,0);p=pcm_peaks(captured,1)
        count=min(len(v),len(p));errors=(np.array(v[:count])-np.array(p[:count]))*48000;assert count>=6 and max(abs(errors))<=TOLERANCE_SAMPLES
        diagnostics=t.diagnostics().result(3);loops=[r['acknowledged_monotonic'] for r in diagnostics['history'] if r.get('operation') in ('loop','loop_restart')]
        groups=[];last=-1
        for pts,block in captured:
            if pts<last or not groups:groups.append({'start':pts/1e9,'frames':0,'end':0.})
            groups[-1]['frames']+=len(block);groups[-1]['end']=pts/1e9+len(block)/48000;last=pts
        assert all(g['frames']==14400 for g in groups[:-1]),groups
        rows.append({'case':'loop','loop_count':t.snapshot().loop_count,'captured_events_per_source':[len(v),len(p)],'max_alignment_error_samples':float(max(abs(errors))),
            'restart_interval_seconds':np.diff(loops).tolist(),'restart_interval_excess_over_region_seconds':(np.diff(loops)-.3).tolist(),'captured_cycles':groups,'gapless':'not claimed; flushing restart is controlled and may gap'})
        before=t.snapshot().position_seconds;sleep(.15);rows.append({'case':'paused_stability','position_before':before,'position_after':t.snapshot().position_seconds,'drift_seconds':t.snapshot().position_seconds-before})
    finally:t.close().result(5);t.wait_closed()
    # Non-periodic loop boundary demonstrates why gapless/clickless is not claimed.
    sine=root/'sine.wav';time=np.arange(96000)/48000;sf.write(sine,.1*np.sin(2*np.pi*220*time),48000,subtype='FLOAT')
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(sine))).result(8);t.set_loop(Loop(.21,.37)).result(5);t.capture(True).result(3);t.play().result(3);wait(lambda:t.snapshot().loop_count>=4,4);t.pause().result(3)
        captured=t.capture().result(3);jumps=[];previous=None;last=-1
        for pts,block in captured:
            if previous is not None and pts<last:jumps.append(float(block[0,0]-previous))
            previous=block[-1,0];last=pts
        rows.append({'case':'loop_boundary_jump','observed_sample_jumps':jumps,'max_absolute_sample_jump':float(max(abs(np.array(jumps)),default=0)),'signal':'220 Hz sine, intentionally nonperiodic loop .21–.37s'})
    finally:t.close().result(5);t.wait_closed()
    # DC test isolates gain-transition shape from the musical signal itself.
    a=root/'dc-a.wav';b=root/'dc-b.wav';signal=np.zeros((96000,2),dtype='float32');signal[:,0]=.1;sf.write(a,signal,48000,subtype='FLOAT');sf.write(b,signal[:,::-1],48000,subtype='FLOAT')
    t=Transport(PlaybackConfig(sink='appsink'))
    try:
        t.load(Session(vocal=Source(a),piano=Source(b))).result(8);t.play().result(3);sleep(.2);request=t.snapshot().position_seconds;t.set_mix('piano').result(3);sleep(.5);t.pause().result(3)
        data=np.zeros((96000,2),dtype='float32')
        for pts,block in t.capture().result(3):
            i=round(pts/1e9*48000);data[i:i+len(block)]=block[:len(data)-i]
        index=np.arange(len(data));v=data[:,0];start=int(np.flatnonzero((v<.072)&(index>round(request*48000)))[0]);end=int(np.flatnonzero((v<.008)&(index>round(request*48000)))[0]);step=float(np.max(abs(np.diff(v[int(request*48000):int(.65*48000)]))))
        assert .014<=(end-start)/48000<=.025 and step<.002
        rows.append({'case':'switch_fade','requested_media_seconds':request,'first_10_percent_change_seconds':start/48000,'fade_10_to_90_seconds':(end-start)/48000,'maximum_adjacent_sample_step':step,'nominal_full_fade_seconds':.02,'generation':t.snapshot().generation,'timeline_reset':False})
    finally:t.close().result(5);t.wait_closed()
report={'schema_version':'1.0.0','status':'complete','tolerances':{'pcm_alignment_samples':TOLERANCE_SAMPLES,'seek_query_seconds':.02,'pause_drift_seconds':.002,'fade_10_to_90_seconds':[.014,.025],'dc_adjacent_step_max':.002},'rows':rows,'physical_speaker_latency':'unverified','physical_listening':'not claimed'}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print('Measured',len(rows),'actual GStreamer capture cases')
