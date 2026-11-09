# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Measured synthesis diagnostics against explicit note truth, no audio-device IO."""
import argparse,json,hashlib
from pathlib import Path
from dataclasses import asdict
import numpy as np
import soundfile as sf
from vocalscope.synthesis.models import RenderConfig
from vocalscope.synthesis.renderer import render_notes
from vocalscope.synthesis.scheduler import schedule_notes
from vocalscope.synthesis.export import export_audio
from vocalscope.transcription.models import NoteEvent

p=argparse.ArgumentParser();p.add_argument('--soundfont',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
def note(key=69,start=0.,end=.5,identity='a'):return NoteEvent(identity,start,end,key,float(key),0.,80)
def frequency(audio,sr):
 import librosa
 values=librosa.yin(audio.mean(axis=1).astype(float),fmin=100,fmax=1000,sr=sr,frame_length=2048,hop_length=256)
 return float(np.median(values[2:-2]))
rows=[]
for rate in [44100,48000]:
 # Starts at different internal buffer phases measure acoustic response separately
 # from the integer dispatch position. Threshold=1e-7 absolute float amplitude.
 for frame in [0,1,17,63,64,65,round(.123456789*rate)]:
  n=note(start=frame/rate,end=frame/rate+.5);audio,r=render_notes([n],a.soundfont,RenderConfig(sample_rate=rate))
  indices=np.flatnonzero(np.max(abs(audio),axis=1)>1e-7);first=int(indices[0])
  measured=frequency(audio[frame+round(.08*rate):frame+round(.4*rate)],rate)
  rows.append({'sample_rate':rate,'requested_time_seconds':n.start_seconds,'scheduled_sample':r['scheduler']['events'][0]['sample_index'],
   'first_above_threshold_sample':first,'attack_threshold_amplitude':1e-7,'acoustic_attack_delay_samples':first-frame,
   'measured_f0_hz':measured,'expected_f0_hz':440.,'pitch_error_cents':float(1200*np.log2(measured/440.)),
   'rounding_error_seconds':r['scheduler']['max_rounding_error_seconds'],'internal_buffer_frames':r['backend']['internal_buffer_frames'],
   'peak':r['diagnostics']['peak_absolute'],'last_50ms_rms':r['diagnostics']['last_50ms_rms']})
for name,notes in [('a4',[note(start=.2,end=.8)]),('repeated',[note(start=s,end=s+.25,identity=str(i)) for i,s in enumerate([.1,.6,1.1])]),
 ('melody',[note(key=k,start=i*.5,end=i*.5+.35,identity=str(i)) for i,k in enumerate([60,62,64,67])]),('silence',[])]:
 result=export_audio(notes,a.soundfont,a.output/name,RenderConfig(sample_rate=48000))
 wav,_=sf.read(result['paths']['wav'],dtype='float32',always_2d=True);flac,_=sf.read(result['paths']['flac'],dtype='float32',always_2d=True)
 record={'case':name,'notes':len(notes),'frames':len(wav),'wav_flac_max_absolute_difference':float(np.max(abs(wav-flac),initial=0)),
  'note_on_count':len([e for e in result['report']['scheduler']['events'] if e['kind']=='note_on']),'diagnostics':result['report']['diagnostics']}
 if name=='repeated':
  record['attack_to_previous_rms_ratios']=[]
  for n in notes:
   before=wav[max(0,round((n.start_seconds-.04)*48000)):round(n.start_seconds*48000)]
   after=wav[round((n.start_seconds+.01)*48000):round((n.start_seconds+.09)*48000)]
   record['attack_to_previous_rms_ratios'].append(float(np.sqrt(np.mean(after**2))/max(1e-12,np.sqrt(np.mean(before**2)))))
 if name=='melody':record['measured_midi_pitches']=[float(69+12*np.log2(frequency(wav[round((n.start_seconds+.08)*48000):round((n.end_seconds-.03)*48000)],48000)/440.)) for n in notes]
 rows.append(record)
math_rows=[]
for rate in [44100,48000]:
 rng=np.random.default_rng(20261109)
 times=np.arange(10000)*.02+rng.uniform(0,.01,10000)
 notes=[note(start=float(t),end=float(t+.003),identity=str(i)) for i,t in enumerate(times)]
 schedule=schedule_notes(notes,RenderConfig(sample_rate=rate))
 math_rows.append({'sample_rate':rate,'events':len(schedule.events),'max_rounding_error_seconds':schedule.max_rounding_error_seconds,'max_rounding_error_samples':schedule.max_rounding_error_seconds*rate,'half_sample_bound_seconds':.5/rate,'seed':20261109})
report={'scheduler_math':math_rows,'soundfont':str(a.soundfont),'sample_truth':'explicit NoteEvents; measured F0 is compared with fixed known 440 Hz, never used as the reference',
 'latency':'Threshold-dependent acoustic attack includes native buffer and SoundFont envelope; not claimed sample accurate. No output shifts applied.',
 'rows':rows}
(a.output/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print('Measured',len(rows),'synthesis cases')
