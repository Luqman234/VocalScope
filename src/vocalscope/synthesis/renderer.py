# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Chunked, event-boundary PCM rendering. No sleeps, sound server, or GTK."""
from dataclasses import asdict
from time import perf_counter
from pathlib import Path
import numpy as np
from .models import RenderConfig,SynthesisError,check_cancelled
from .scheduler import schedule_notes
from .fluidsynth_backend import FluidSynthBackend
from .diagnostics import WaveformDiagnostics
from . import RENDERER_VERSION


def stream_notes(notes, soundfont: str | Path, config: RenderConfig, sink, *, duration_seconds: float | None = None, cancelled=None) -> dict:
    begin=perf_counter();notes=tuple(notes);schedule=schedule_notes(notes,config,duration_seconds=duration_seconds)
    check_cancelled(cancelled)
    synth=FluidSynthBackend(soundfont,config,cancelled)
    diagnostics=WaveformDiagnostics(config.sample_rate);position=0;events=[];render_begin=perf_counter()
    def emit_until(end):
        nonlocal position
        while position<end:
            check_cancelled(cancelled)
            count=min(config.chunk_frames,end-position);block=synth.samples(count)
            diagnostics.add(block);sink(block);position+=count
    try:
        for event in schedule.events:
            emit_until(event.sample_index);check_cancelled(cancelled);synth.event(event);events.append(asdict(event))
        emit_until(schedule.frames)
        stats=diagnostics.result()
        if not notes and stats['peak_absolute']>1e-10:raise SynthesisError('Empty transcription unexpectedly produced non-silent audio.')
        if notes and stats['peak_absolute']==0:raise SynthesisError('The requested preset produced no audio; render discarded.')
        warnings=[]
        if stats['clipping_risk']:warnings.append('Raw PCM exceeds full scale; without explicit normalization, float WAV retains these values and playback or integer encoding can clip.')
        if stats['tail_residual_above_minus60_dbfs']:warnings.append('Tail limit reached with residual RMS above -60 dBFS; increase tail duration if needed.')
        return {'schema_version':'1.0.0','renderer_version':RENDERER_VERSION,'status':'complete','sample_rate':config.sample_rate,'channels':2,
            'frames':schedule.frames,'duration_seconds':schedule.frames/config.sample_rate,'configuration':asdict(config),'soundfont':dict(synth.info),'backend':dict(synth.metadata),
            'scheduler':{'events':events,'last_note_off_sample':schedule.last_note_off_sample,'content_frames':schedule.content_frames,
                'max_rounding_error_seconds':schedule.max_rounding_error_seconds,'rounding':'Python round: nearest sample, ties to even; <=0.5 sample per event',
                'ordering':'note-offs before note-ons at shared samples, then stable note_id; overlapping identical keys use different melodic channels',
                'channels_used':list(schedule.channels_used),'unreleased_midi_notes':0,'active_release_voices_at_end':synth.active_voice_count()},
            'diagnostics':stats,'warnings':warnings,'timings':{**synth.timings,'render_seconds':perf_counter()-render_begin,'initialization_and_render_seconds':perf_counter()-begin}}
    finally:
        synth.close()


def render_notes(notes, soundfont_path: str | Path, config: RenderConfig | None = None, *, duration_seconds: float | None = None, cancelled=None) -> tuple[np.ndarray, dict]:
    """Convenience bounded-array API; use stream_notes/export for long recordings."""
    config=config or RenderConfig();notes=tuple(notes);plan=schedule_notes(notes,config,duration_seconds=duration_seconds)
    if plan.frames*2*4>config.max_buffer_mb*1024**2:raise SynthesisError('PCM array exceeds buffer budget; use streaming export instead.')
    audio=np.empty((plan.frames,2),dtype=np.float32);cursor=0
    def sink(block):
        nonlocal cursor
        audio[cursor:cursor+len(block)]=block;cursor+=len(block)
    report=stream_notes(notes,soundfont_path,config,sink,duration_seconds=duration_seconds,cancelled=cancelled)
    audio.setflags(write=False)
    return audio,report
