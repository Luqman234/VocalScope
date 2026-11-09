# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Validated note contracts. Acoustic arrays are never edited or quantized."""
from dataclasses import dataclass, asdict, replace
import math
import uuid


@dataclass(frozen=True)
class TranscriptionConfig:
    method: str = 'combined'
    min_duration: float = 0.06
    bridge_gap: float = 0.08
    pitch_change: float = 0.8
    stability_window: float = 0.07
    onset_threshold: float = 0.35
    min_coverage: float = 0.55
    max_flatness: float = 0.45
    velocity: int = 80

    def __post_init__(self):
        if self.method not in ('naive', 'pitch-only', 'combined'):
            raise ValueError('Unknown segmentation method.')
        for key in ('min_duration', 'stability_window', 'pitch_change'):
            if not math.isfinite(getattr(self,key)) or getattr(self,key) <= 0:
                raise ValueError(f'{key} must be positive and finite.')
        for key in ('bridge_gap','onset_threshold','min_coverage','max_flatness'):
            if not math.isfinite(getattr(self,key)) or not 0 <= getattr(self,key) <= 1:
                raise ValueError(f'{key} must be between zero and one.')
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ValueError('Velocity must be an integer from 1 to 127.')


@dataclass(frozen=True)
class Boundary:
    time_seconds: float
    source: str
    strength: float
    boundary_type: str

    def __post_init__(self):
        if not math.isfinite(self.time_seconds) or self.time_seconds < 0 or not math.isfinite(self.strength) or self.strength < 0:
            raise ValueError('Invalid candidate boundary.')


@dataclass(frozen=True)
class NoteEvent:
    note_id: str
    start_seconds: float
    end_seconds: float
    midi_note: int
    midi_pitch: float
    cents_deviation: float
    velocity: int = 80
    pitch_coverage: float = 1.0
    source_start_frame: int | None = None
    source_end_frame: int | None = None
    onset_source: str = 'manual'
    edited: bool = False
    flags: tuple[str,...] = ()

    def __post_init__(self):
        if not self.note_id or not isinstance(self.note_id,str):
            raise ValueError('Notes require stable nonempty IDs.')
        for key in ('start_seconds','end_seconds','midi_pitch','cents_deviation','pitch_coverage'):
            if not math.isfinite(getattr(self,key)):
                raise ValueError(f'{key} must be finite.')
        if self.start_seconds < 0 or self.end_seconds <= self.start_seconds:
            raise ValueError('Note end must be after a nonnegative start.')
        if type(self.midi_note) is not int or not 0 <= self.midi_note <= 127:
            raise ValueError('MIDI pitch must be an integer from 0 to 127.')
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ValueError('MIDI velocity must be an integer from 1 to 127.')
        if not 0 <= self.pitch_coverage <= 1:
            raise ValueError('Pitch coverage must be in [0,1].')
        if abs(self.cents_deviation - 100*(self.midi_pitch-self.midi_note)) > 1e-7:
            raise ValueError('Cents deviation must describe the stored pitch center.')
        if (self.source_start_frame is None) != (self.source_end_frame is None):
            raise ValueError('Source frame bounds must both be present or absent.')
        if self.source_start_frame is not None and (type(self.source_start_frame) is not int or type(self.source_end_frame) is not int or not 0 <= self.source_start_frame < self.source_end_frame):
            raise ValueError('Invalid half-open source frame interval.')
        object.__setattr__(self,'flags',tuple(self.flags))


def validate_notes(notes, duration):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Source duration must be positive.')
    ordered=sorted(notes,key=lambda n:(n.start_seconds,n.note_id))
    if len({n.note_id for n in ordered}) != len(ordered):
        raise ValueError('Duplicate note IDs.')
    for i,n in enumerate(ordered):
        if n.end_seconds > duration+1e-8:
            raise ValueError('Note extends beyond source audio.')
        if i and n.start_seconds < ordered[i-1].end_seconds-1e-8:
            raise ValueError('Monophonic projects do not allow overlapping notes.')
    return tuple(ordered)


class TranscriptionResult:
    """Generated baseline plus editable snapshot journal; undo/redo survives save.

    Each journal entry records full before/after notes. Branching after undo drops
    only the redo branch. Acoustic analysis and generated notes remain immutable.
    """
    def __init__(self, acoustic, source_sha256, config, generated_notes, boundaries=(), timings=None):
        if not isinstance(source_sha256,str) or len(source_sha256)!=64 or any(c not in '0123456789abcdef' for c in source_sha256):raise ValueError('Invalid source SHA256.')
        from . import ALGORITHM_VERSION
        self.algorithm_version=ALGORITHM_VERSION
        expected=acoustic.backend_metadata.get('source_sha256')
        if expected and expected!=source_sha256:raise ValueError('Source identity disagrees with acoustic provenance.')
        self.acoustic=replace(acoustic,backend_metadata={**acoustic.backend_metadata,'source_sha256':source_sha256})
        self.source_sha256=source_sha256
        self.config=config
        self.generated_notes=validate_notes(generated_notes,self.duration)
        if any(n.source_end_frame is not None and n.source_end_frame>len(acoustic.time_seconds) for n in self.generated_notes):raise ValueError('Note source frames exceed acoustic analysis.')
        self.notes=self.generated_notes
        self.boundaries=tuple(boundaries)
        self.timings=dict(timings or {})
        self.journal=[]
        self.cursor=0

    @property
    def duration(self):return self.acoustic.metadata.duration_seconds

    def _commit(self,operation,notes):
        after=validate_notes(notes,self.duration)
        self.journal=self.journal[:self.cursor]
        self.journal.append({'operation':operation,'before':[asdict(n) for n in self.notes],'after':[asdict(n) for n in after]})
        self.cursor+=1
        self.notes=after

    def edit(self,note_id,**changes):
        allowed={'start_seconds','end_seconds','midi_note','velocity'}
        if set(changes)-allowed:raise ValueError('Unsupported note edit.')
        old=self.get(note_id)
        if 'midi_note' in changes:
            # Keep the measured pitch center; editing changes the piano key only.
            changes['cents_deviation']=100*(old.midi_pitch-changes['midi_note'])
        new=replace(old,**changes,edited=True)
        self._commit('edit',[new if n.note_id==note_id else n for n in self.notes])

    def get(self,note_id):
        try:return next(n for n in self.notes if n.note_id==note_id)
        except StopIteration:raise ValueError('Unknown note ID.') from None

    def add(self,start,end,pitch,velocity=80):
        n=NoteEvent(str(uuid.uuid4()),start,end,pitch,float(pitch),0.,velocity,0.,edited=True)
        self._commit('add',(*self.notes,n));return n.note_id

    def delete(self,note_id):
        self.get(note_id);self._commit('delete',[n for n in self.notes if n.note_id!=note_id])

    def split(self,note_id,time_seconds):
        n=self.get(note_id)
        if not n.start_seconds < time_seconds < n.end_seconds:raise ValueError('Split must lie inside the note.')
        right=replace(n,note_id=str(uuid.uuid4()),start_seconds=time_seconds,edited=True,flags=(*n.flags,'source_frames_cover_parent'))
        left=replace(n,end_seconds=time_seconds,edited=True,flags=(*n.flags,'source_frames_cover_parent'))
        self._commit('split',[x for x in self.notes if x.note_id!=note_id]+[left,right])
        return right.note_id

    def merge(self,first_id,second_id):
        a,b=sorted([self.get(first_id),self.get(second_id)],key=lambda n:n.start_seconds)
        if a.note_id==b.note_id or a.midi_note!=b.midi_note:raise ValueError('Merge requires two different notes with the same MIDI key.')
        i=self.notes.index(a)
        if i+1>=len(self.notes) or self.notes[i+1].note_id!=b.note_id:raise ValueError('Only adjacent notes can merge.')
        frames=[v for v in (a.source_start_frame,b.source_start_frame) if v is not None]
        ends=[v for v in (a.source_end_frame,b.source_end_frame) if v is not None]
        joined=replace(a,end_seconds=b.end_seconds,edited=True,source_start_frame=min(frames) if frames else None,source_end_frame=max(ends) if ends else None,flags=(*a.flags,'manual_merge'))
        self._commit('merge',[n for n in self.notes if n.note_id not in (a.note_id,b.note_id)]+[joined])

    def undo(self):
        if self.cursor:
            self.cursor-=1;self.notes=validate_notes([NoteEvent(**n) for n in self.journal[self.cursor]['before']],self.duration)

    def redo(self):
        if self.cursor<len(self.journal):
            self.notes=validate_notes([NoteEvent(**n) for n in self.journal[self.cursor]['after']],self.duration);self.cursor+=1
