# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Integer sample scheduling; MIDI note-offs precede note-ons at a shared sample."""
from dataclasses import dataclass
import math
from ..transcription.models import NoteEvent
from .models import RenderConfig,SynthesisError

CHANNELS=tuple(c for c in range(16) if c!=9)  # Never select a GM percussion channel.


@dataclass(frozen=True)
class ScheduledEvent:
    sample_index: int
    kind: str
    channel: int
    midi_note: int
    velocity: int
    note_id: str
    requested_seconds: float


@dataclass(frozen=True)
class Schedule:
    events: tuple[ScheduledEvent,...]
    frames: int
    content_frames: int
    last_note_off_sample: int
    max_rounding_error_seconds: float
    channels_used: tuple[int,...]


def schedule_notes(notes, config: RenderConfig, *, duration_seconds: float | None = None) -> Schedule:
    notes=tuple(notes)
    if len(notes)>config.max_notes:raise SynthesisError('Too many notes for the configured resource limit.')
    if any(not isinstance(n,NoteEvent) for n in notes):raise ValueError('Rendering requires validated NoteEvent instances.')
    if len({n.note_id for n in notes})!=len(notes):raise ValueError('Duplicate note IDs.')
    last=max((n.end_seconds for n in notes),default=0.)
    if duration_seconds is not None:
        if isinstance(duration_seconds,bool) or not math.isfinite(duration_seconds) or duration_seconds<last or duration_seconds<0:raise ValueError('Content duration must be finite and cover every note.')
        last=duration_seconds
    if last+config.tail_seconds>config.max_duration_seconds:raise SynthesisError('Render duration including tail exceeds the configured limit.')
    raw=[];errors=[]
    for n in notes:
        start=round(n.start_seconds*config.sample_rate);end=round(n.end_seconds*config.sample_rate)
        if end<=start:raise ValueError(f'Note {n.note_id} resolves to zero samples; increase rate or edit its duration.')
        raw.extend([(start,1,n),(end,0,n)])
        errors.extend([abs(start/config.sample_rate-n.start_seconds),abs(end/config.sample_rate-n.end_seconds)])
    raw.sort(key=lambda e:(e[0],e[1],e[2].note_id))
    assignments={};active=set();events=[];channels=set()
    for sample,on,n in raw:
        if on:
            channel=next((c for c in CHANNELS if (c,n.midi_note) not in active),None)
            if channel is None:raise SynthesisError('More than 15 overlapping instances of the same MIDI key; refusing ambiguous note-offs.')
            assignments[n.note_id]=channel;active.add((channel,n.midi_note));channels.add(channel)
        else:
            channel=assignments.pop(n.note_id);active.remove((channel,n.midi_note))
        events.append(ScheduledEvent(sample,'note_on' if on else 'note_off',channel,n.midi_note,n.velocity,n.note_id,n.start_seconds if on else n.end_seconds))
    assert not active and not assignments
    content=round(last*config.sample_rate);frames=max(1,content+round(config.tail_seconds*config.sample_rate))
    last_off=max((e.sample_index for e in events if e.kind=='note_off'),default=0)
    return Schedule(tuple(events),frames,content,last_off,max(errors,default=0.),tuple(sorted(channels)))
