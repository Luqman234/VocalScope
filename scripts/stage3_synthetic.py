# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Controlled end-to-end tests, independent annotated event times and integrated phase."""
import argparse,json,tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from vocalscope.transcription.pipeline import transcribe_file
from vocalscope.transcription.dataset import NoteReference
from vocalscope.transcription.evaluation import evaluate
from vocalscope.backends import EstimatorConfig

p=argparse.ArgumentParser();p.add_argument('--estimator',choices=['pyin','yin','crepe'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sr=22050;duration=2.;t=np.arange(int(sr*duration))/sr;cases={}
for name,sequence in [('sustain',[(.2,1.8,69)]),('repeated',[(.2,.65,69),(.75,1.2,69),(1.3,1.8,69)]),('ascending',[(.2,.7,69),(.7,1.2,71),(1.2,1.8,72)]),('descending',[(.2,.7,72),(.7,1.2,71),(1.2,1.8,69)]),('staccato',[(.2,.32,69),(.6,.72,71),(1.,1.12,72)]),('short_gap',[(.2,1.8,69)])]:
 f=np.full(len(t),440.);gate=np.zeros(len(t))
 for start,end,midi in sequence:
  active=(t>=start)&(t<end);f[active]=440*2**((midi-69)/12);gate[active]=1
 if name=='short_gap':gate[(t>=.9)&(t<.93)]=0
 cases[name]=(f,gate,sequence)
for rate in [3,5]:cases[f'vibrato{rate}']=(440*2**(.45*np.sin(2*np.pi*rate*t)/12),((t>=.2)&(t<1.8)).astype(float),[(.2,1.8,69)])
cases['glissando']=(440*2**(3*np.clip((t-.2)/1.6,0,1)/12),((t>=.2)&(t<1.8)).astype(float),[(.2,1.8,70.5)])
rows=[]
with tempfile.TemporaryDirectory() as temp:
 for name in list(cases)+['silence','breath']:
  if name in cases:
   f,gate,events=cases[name];phase=2*np.pi*np.cumsum(f)/sr;y=gate*(.25*np.sin(phase)+.1*np.sin(2*phase))
  else:
   events=[];y=np.zeros(len(t)) if name=='silence' else np.random.default_rng(20261109).normal(0,.025,len(t))*(.4+.6*np.sin(np.pi*t/duration)**2)
  path=Path(temp)/(name+'.wav');sf.write(path,y,sr,subtype='FLOAT')
  project=transcribe_file(path,settings=EstimatorConfig(estimator_id=a.estimator,crepe_model='tiny'))
  if events:
   ref=NoteReference(name,'synthetic',np.array([[s,e] for s,e,_ in events]),np.array([440*2**((m-69)/12) for _,_,m in events]),'analytic')
   metrics=evaluate(ref,project.notes)
  else:metrics=None
  rows.append({'case':name,'backend':a.estimator,'predicted_notes':len(project.notes),'reference_notes':len(events),'midi_keys':[n.midi_note for n in project.notes],
   'metrics':metrics,'timings':project.timings,'note_flags':[n.flags for n in project.notes]})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'seed':20261109,'rows':rows,'glissando_policy':'One broad gesture; 70.5 MIDI is a deliberately ambiguous reference, not a unique musical truth.','signal_count':len(rows)},indent=2,allow_nan=False)+'\n')
