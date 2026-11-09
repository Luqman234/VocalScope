# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Transport contracts; all time values are canonical media seconds."""
from dataclasses import dataclass,field
from enum import StrEnum
from pathlib import Path
import math
from ..errors import VocalScopeError


class PlaybackError(VocalScopeError):pass
class Superseded(PlaybackError):pass


class State(StrEnum):
    EMPTY='EMPTY';LOADING='LOADING';READY='READY';PLAYING='PLAYING';PAUSED='PAUSED'
    STOPPED='STOPPED';SEEKING='SEEKING';RECOVERING='RECOVERING';ERROR='ERROR';CLOSING='CLOSING'


@dataclass(frozen=True)
class Source:
    path: Path | str
    offset_seconds: float=0.
    def __post_init__(self):
        if not math.isfinite(self.offset_seconds) or abs(self.offset_seconds)>30:raise ValueError('Alignment offset must be finite and within ±30 seconds.')
        object.__setattr__(self,'path',Path(self.path).expanduser().resolve())


@dataclass(frozen=True)
class Session:
    vocal: Source | None=None
    piano: Source | None=None
    piano_revision: int=0
    def __post_init__(self):
        if self.vocal is None and self.piano is None:raise ValueError('A playback session needs at least one source.')
        if type(self.piano_revision) is not int or self.piano_revision<0:raise ValueError('Invalid piano revision.')


@dataclass(frozen=True)
class PlaybackConfig:
    sink: str='auto'
    sample_rate: int=48000
    master_gain: float=.8
    fade_seconds: float=.02
    operation_timeout: float=10.
    capture_seconds: float=10.
    sink_sync: bool=True
    output_stall_timeout: float=2.
    def __post_init__(self):
        if self.sink not in ('auto','pipewiresink','pulsesink','fakesink','appsink'):raise ValueError('Unsupported output sink.')
        if self.sample_rate!=48000:raise ValueError('Playback canonical rate is 48000 Hz.')
        for key,low,high in [('master_gain',0.,1.),('fade_seconds',.01,.1),('operation_timeout',1.,30.),('capture_seconds',0.,120.),('output_stall_timeout',.2,30.)]:
            v=getattr(self,key)
            if not math.isfinite(v) or not low<=v<=high:raise ValueError(f'Invalid {key}.')


@dataclass(frozen=True)
class Loop:
    start_seconds: float
    end_seconds: float
    enabled: bool=True
    def validate(self,duration):
        if not all(math.isfinite(v) for v in [self.start_seconds,self.end_seconds]) or not 0<=self.start_seconds<self.end_seconds<=duration:raise ValueError('Loop must satisfy 0 <= start < end <= session duration.')
        if round((self.end_seconds-self.start_seconds)*1e9)<50_000_000:raise ValueError('Loops shorter than 50 ms are unsupported.')


@dataclass(frozen=True)
class Snapshot:
    state: State=State.EMPTY
    position_seconds: float=0.
    duration_seconds: float=0.
    position_valid: bool=False
    seeking: bool=False
    sink: str=''
    mode: str='vocal'
    loop: Loop | None=None
    piano_revision: int=0
    error: str | None=None
    sampled_monotonic: float=0.
    generation: int=0
    loop_count: int=0
    latency_seconds: float | None=None
    peak: float=0.
    vocal_duration_seconds: float=0.
    piano_duration_seconds: float=0.
