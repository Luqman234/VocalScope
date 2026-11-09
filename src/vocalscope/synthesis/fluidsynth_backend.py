# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Owned FluidSynth handles, pyfluidsynth bindings, three small ABI extensions.

pyfluidsynth exposes only int16 get_samples. Bind documented write_float,
interpolation and internal buffer size against the same loaded libfluidsynth.
No audio/MIDI driver, player, sequencer or wall-clock scheduling is created.
This offline backend owns its process's FluidSynth instances/driver registry.
"""
import ctypes as C
from functools import lru_cache
from importlib.metadata import version
from threading import RLock
from time import perf_counter
import numpy as np
from .models import SynthesisError,check_cancelled
from .soundfont import validate_soundfont

_LOCK=RLock()


@lru_cache(maxsize=1)
def native_api():
    try:
        import fluidsynth as fs
        lib=C.CDLL(fs.lib)
        def bind(name,result,*args):return C.CFUNCTYPE(result,*args)((name,lib))
        # A NULL-terminated empty list disables live-driver enumeration. Only
        # called once, before any settings/synth owned by this backend exists.
        register=bind('fluid_audio_driver_register',C.c_int,C.POINTER(C.c_char_p))
        if register((C.c_char_p*1)(None))!=0:raise SynthesisError('Cannot disable unused live audio drivers.')
        return fs,{
            'write_float':bind('fluid_synth_write_float',C.c_int,C.c_void_p,C.c_int,C.c_void_p,C.c_int,C.c_int,C.c_void_p,C.c_int,C.c_int),
            'interp':bind('fluid_synth_set_interp_method',C.c_int,C.c_void_p,C.c_int,C.c_int),
            'buffer_size':bind('fluid_synth_get_internal_bufsize',C.c_int,C.c_void_p),
            'version':bind('fluid_version_str',C.c_char_p)}
    except (ImportError,OSError,AttributeError) as exc:
        raise SynthesisError("FluidSynth rendering unavailable. On Arch install fluidsynth, then install VocalScope's optional synthesis extra: python -m pip install -e '.[synthesis]'. "+str(exc)) from exc


class FluidSynthBackend:
    """Context-managed native synth; use one rendering thread per instance."""
    def __init__(self,soundfont,config,cancelled=None):
        self.settings=None;self.synth=None;self.font_id=None;self.config=config;self.fs=None
        self.timings={};self.info={};self._lock_owned=False
        begin=perf_counter()
        _LOCK.acquire();self._lock_owned=True
        try:
            check_cancelled(cancelled)
            self.info=validate_soundfont(soundfont,config)
            self.fs,self.api=native_api()
            self.settings=self.fs.new_fluid_settings()
            if not self.settings:raise SynthesisError('FluidSynth settings allocation failed.')
            # Explicit effects settings make enabled effects reproducible too.
            self.effective_settings={'synth.sample-rate':float(config.sample_rate),'synth.gain':float(config.gain),
                'synth.midi-channels':16,'synth.audio-channels':1,'synth.polyphony':config.polyphony,
                'synth.cpu-cores':1,'synth.threadsafe-api':0,'synth.min-note-length':0,'synth.dynamic-sample-loading':0,
                'synth.reverb.active':int(config.reverb),'synth.chorus.active':int(config.chorus),
                'synth.reverb.room-size':.2,'synth.reverb.damp':0.,'synth.reverb.width':.5,'synth.reverb.level':.9,
                'synth.chorus.nr':3,'synth.chorus.level':2.,'synth.chorus.speed':.3,'synth.chorus.depth':8.}
            for name,value in self.effective_settings.items():
                setter=self.fs.fluid_settings_setnum if isinstance(value,float) else self.fs.fluid_settings_setint
                if setter(self.settings,name.encode(),value)!=0:raise SynthesisError(f'FluidSynth rejected setting {name}={value}.')
            self.synth=self.fs.new_fluid_synth(self.settings)
            if not self.synth:raise SynthesisError('FluidSynth synthesizer allocation failed.')
            if self.api['interp'](self.synth,-1,config.interpolation)!=0:raise SynthesisError('Interpolation mode unavailable.')
            initialized=perf_counter();self.timings['synth_initialization_seconds']=initialized-begin
            check_cancelled(cancelled)
            self.font_id=self.fs.fluid_synth_sfload(self.synth,str(self.info['path']).encode(),0)
            if self.font_id<0:raise SynthesisError('FluidSynth could not load this SoundFont; it may be damaged or use unsupported SF3 compression.')
            sfont=self.fs.fluid_synth_get_sfont_by_id(self.synth,self.font_id)
            preset=self.fs.fluid_sfont_get_preset(sfont,config.bank,config.preset)
            if not preset:raise SynthesisError(f'Requested SoundFont bank {config.bank}, preset {config.preset} does not exist; no instrument was substituted.')
            preset_name=self.fs.fluid_preset_get_name(preset).decode('utf-8',errors='replace')
            for channel in range(16):
                if channel!=9 and self.fs.fluid_synth_program_select(self.synth,channel,self.font_id,config.bank,config.preset)!=0:raise SynthesisError('SoundFont program selection failed.')
            verified=validate_soundfont(soundfont,config)
            if verified['sha256']!=self.info['sha256']:raise SynthesisError('SoundFont changed while loading; output discarded.')
            self.timings['soundfont_loading_seconds']=perf_counter()-initialized
            self.info.update({'bank':config.bank,'preset':config.preset,'preset_name':preset_name})
            self.metadata={'fluidsynth_version':self.api['version']().decode(),'pyfluidsynth_version':version('pyfluidsynth'),
                'internal_buffer_frames':self.api['buffer_size'](self.synth),'sample_format':'float32 stereo interleaved',
                'audio_driver':None,'settings':self.effective_settings,'interpolation':config.interpolation,
                'chorus_waveform':'sine (FluidSynth default type 0)','threading':'one CPU render core, no realtime driver',
                'internal_latency':'Events dispatched after the exact requested PCM count; previously synthesized native block samples may delay response by up to internal_buffer_frames-1 samples. SoundFont attack adds independent acoustic latency.'}
            check_cancelled(cancelled)
        except BaseException:
            self.close();raise

    def event(self,event):
        fn=self.fs.fluid_synth_noteon if event.kind=='note_on' else self.fs.fluid_synth_noteoff
        args=(self.synth,event.channel,event.midi_note,event.velocity) if event.kind=='note_on' else (self.synth,event.channel,event.midi_note)
        if fn(*args)!=0:raise SynthesisError(f'FluidSynth rejected {event.kind} for note {event.note_id}.')

    def samples(self,frames):
        if self.synth is None:raise SynthesisError('Synthesizer is closed.')
        out=np.empty((frames,2),dtype=np.float32)
        if self.api['write_float'](self.synth,frames,out.ctypes.data,0,2,out.ctypes.data,1,2)!=0:raise SynthesisError('FluidSynth float rendering failed.')
        if not np.isfinite(out).all():raise SynthesisError('FluidSynth returned non-finite PCM; output discarded.')
        return out

    def active_voice_count(self):return int(self.fs.fluid_synth_get_active_voice_count(self.synth))

    def close(self):
        try:
            if self.synth:
                try:
                    for channel in range(16):self.fs.fluid_synth_all_sounds_off(self.synth,channel)
                finally:self.fs.delete_fluid_synth(self.synth);self.synth=None
        finally:
            if self.settings:self.fs.delete_fluid_settings(self.settings);self.settings=None
            if self._lock_owned:_LOCK.release();self._lock_owned=False

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
