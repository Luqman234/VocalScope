# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Original Vocadito v3 notes: headerless onset seconds, Hz, duration seconds."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from ..datasets import digest
from ..errors import VocalScopeError


@dataclass(frozen=True)
class NoteReference:
    track_id: str
    annotator: str
    intervals: np.ndarray
    frequencies: np.ndarray
    sha256: str


def load_note_csv(path,*,duration=None):
    try:rows=np.loadtxt(path,delimiter=',',ndmin=2)
    except (ValueError,OSError) as exc:raise VocalScopeError(f'Invalid note annotations: {path}: {exc}') from exc
    if rows.ndim!=2 or rows.shape[1]!=3 or not len(rows) or not np.isfinite(rows).all():raise VocalScopeError('Expected finite onset, frequency, duration columns.')
    if np.any(rows[:,0]<0) or np.any(rows[:,1:]<=0) or np.any(np.diff(rows[:,0])<0):raise VocalScopeError('Invalid note annotation timing or frequency.')
    intervals=np.column_stack((rows[:,0],rows[:,0]+rows[:,2]))
    if duration is not None and np.max(intervals[:,1])>duration+.01:raise VocalScopeError('Notes extend more than 10 ms beyond the recording.')
    # Reference overlaps, if present, remain unchanged; only editable output is
    # constrained to monophony. Original frequencies are not quantized.
    intervals.setflags(write=False);frequency=rows[:,1].copy();frequency.setflags(write=False)
    return intervals,frequency


def load_notes(dataset,identifier,annotator):
    if annotator not in ('A1','A2'):raise ValueError('Annotator must be A1 or A2.')
    track=dataset.load_track(identifier)
    relative,md5=dataset.index['tracks'][identifier]['notes'+annotator]
    path=(dataset.root/relative).resolve()
    if not path.is_relative_to(dataset.root) or not path.is_file() or digest(path,'md5')!=md5:raise VocalScopeError(f'Missing or damaged {annotator} notes for track {identifier}.')
    intervals,frequencies=load_note_csv(path,duration=track.duration_seconds)
    return NoteReference(identifier,annotator,intervals,frequencies,digest(path))


def grouped_folds(metadata,folds=5,seed=20261109):
    """Seeded greedy balancing by track count; singer identities are indivisible."""
    if folds<2:raise ValueError('At least two folds required.')
    groups={}
    for track,row in metadata.items():
        singer=row.get('singer_id')
        if not singer:raise ValueError(f'Track {track} lacks a singer identity; cannot claim singer-disjoint evaluation.')
        groups.setdefault(singer,[]).append(track)
    if len(groups)<folds:raise ValueError('More folds than singers.')
    rng=np.random.default_rng(seed);names=sorted(groups);rng.shuffle(names)
    names.sort(key=lambda n:-len(groups[n])) # stable shuffle breaks equal-size ties
    buckets=[[] for _ in range(folds)]
    for name in names:
        i=min(range(folds),key=lambda j:len(buckets[j]));buckets[i].extend(groups[name])
    return [sorted(b,key=int) for b in buckets]


def grouped_split(metadata,seed=20261109):
    folds=grouped_folds(metadata,5,seed)
    test=sorted(folds[0]+folds[1],key=int)
    development=sorted(set(metadata)-set(test),key=int)
    return {'development':development,'test':test,'folds':folds,'seed':seed,
        'development_singers':sorted({metadata[t]['singer_id'] for t in development}),
        'test_singers':sorted({metadata[t]['singer_id'] for t in test})}
