# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""One-to-one mir_eval note matching with explicit counts and custom diagnostics."""
import warnings
import numpy as np
from mir_eval import transcription as mt


def prf(matches,predicted,reference):
    precision=matches/predicted if predicted else None
    recall=matches/reference if reference else None
    f1=2*matches/(predicted+reference) if predicted+reference else None
    return {'precision':precision,'recall':recall,'f1':f1,'matches':int(matches),'predicted':int(predicted),'reference':int(reference)}


def evaluate(reference,notes,a4_hz=440.):
    ri=reference.intervals;rp=reference.frequencies
    ei=np.asarray([[n.start_seconds,n.end_seconds] for n in notes],dtype=float).reshape(-1,2)
    ep=np.asarray([a4_hz*2**((n.midi_note-69)/12) for n in notes])
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Estimated notes are empty.*')
        onset=mt.match_note_onsets(ri,ei,onset_tolerance=.05)
        pitch=mt.match_notes(ri,rp,ei,ep,offset_ratio=None)
        offset=mt.match_notes(ri,rp,ei,ep,offset_ratio=.2,offset_min_tolerance=.05)
    result={name:prf(len(matches),len(ei),len(ri)) for name,matches in [('onset',onset),('pitch',pitch),('offset',offset)]}
    result['average_overlap_ratio']=float(mt.average_overlap_ratio(ri,ei,offset)) if offset else None
    # Custom diagnostics are temporal intersections with matching pitch, NOT
    # alternate standard scores. A pair must overlap >= min(50ms, 25% ref).
    if len(ei):
        overlap=np.maximum(0,np.minimum(ri[:,None,1],ei[None,:,1])-np.maximum(ri[:,None,0],ei[None,:,0]))
        close=np.abs(1200*np.log2(rp[:,None]/ep[None,:]))<=50
        related=close & (overlap>=np.minimum(.05,.25*(ri[:,1]-ri[:,0]))[:,None])
        fragments=int(np.sum(np.maximum(0,related.sum(axis=1)-1)))
        merges=int(np.sum(np.maximum(0,related.sum(axis=0)-1)))
        # Predicted interval with no intersection with ANY annotated note.
        rest=int(np.sum(np.max(overlap,axis=0)<=1e-8))
        repeated=0
        for i in range(len(ri)-1):
            if abs(1200*np.log2(rp[i+1]/rp[i]))<=50 and np.any(related[i]&related[i+1]):repeated+=1
    else:fragments=merges=rest=repeated=0
    result['diagnostics']={'predicted_note_count':len(ei),'reference_note_count':len(ri),'note_count_error':len(ei)-len(ri),
        'missed_notes':len(ri)-len(pitch),'extra_notes':len(ei)-len(pitch),'incorrect_fragmentation':fragments,
        'incorrect_merging':merges,'repeated_note_split_failures':repeated,'notes_entirely_in_reference_rests':rest}
    return result


def summarize(rows):
    out={}
    for name in ('onset','pitch','offset'):
        selected=[r['metrics'][name] for r in rows]
        out[name]={'micro':prf(sum(m['matches'] for m in selected),sum(m['predicted'] for m in selected),sum(m['reference'] for m in selected)),
            'macro':{k:float(np.mean(v)) if (v:=[m[k] for m in selected if m[k] is not None]) else None for k in ('precision','recall','f1')}}
    return out
