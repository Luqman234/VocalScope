# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Serial per-backend measurements. No datasets or model downloads."""
import argparse,json,resource,platform,tempfile
from pathlib import Path
from time import perf_counter
import numpy as np
import soundfile as sf
from vocalscope.models import AnalysisConfig
from vocalscope.backends import EstimatorConfig
from vocalscope.audio import load_audio
from vocalscope.transcription.pipeline import transcribe_file,transcribe_analysis
from vocalscope.transcription.midi_export import midi_bytes
from vocalscope.transcription.serialization import atomic_write
from vocalscope.pitch import library_versions

p=argparse.ArgumentParser();p.add_argument('--estimator',choices=['pyin','yin','crepe'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
rows=[]
with tempfile.TemporaryDirectory() as temp:
 for index,duration in enumerate([1,1,5,15]):
  sr=22050;t=np.arange(sr*duration)/sr;freq=440*2**(.2*np.sin(2*np.pi*5*t)/12);phase=2*np.pi*np.cumsum(freq)/sr
  y=.25*np.sin(phase)+.12*np.sin(2*phase)+.06*np.sin(3*phase)
  path=Path(temp)/f'{duration}.wav';sf.write(path,y,sr,subtype='FLOAT')
  begin=perf_counter();project=transcribe_file(path,settings=EstimatorConfig(estimator_id=a.estimator,crepe_model='tiny'));to_notes=perf_counter()-begin
  start=perf_counter();atomic_write(Path(temp)/f'{index}.mid',midi_bytes(project.notes));midi_seconds=perf_counter()-start
  audio=load_audio(path,AnalysisConfig());start=perf_counter();cached=transcribe_analysis(audio,project.acoustic);cached_seconds=perf_counter()-start
  rows.append({'clip_seconds':duration,'cold_first_call':index==0,'backend':a.estimator,'model':'tiny' if a.estimator=='crepe' else None,
    'audio_to_notes_seconds':to_notes,'audio_to_midi_seconds':to_notes+midi_seconds,'midi_export_seconds':midi_seconds,'cached_pitch_to_notes_seconds':cached_seconds,
    'components':project.timings,'cached_components':cached.timings,'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
    'notes':len(project.notes),'runtime_over_audio':(to_notes+midi_seconds)/duration})
report={'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown'),
 'platform':platform.platform(),'versions':library_versions(),'rows':rows,
 'semantics':'Serial backend-specific process, interpreter/import startup excluded; first call includes lazy/JIT/model initialization. Warm calls reuse process; RSS is cumulative process high water. MIDI includes bytes serialization and atomic fsynced file publication. Cached pitch-to-notes includes original-audio features, segmentation and centers; audio loading measured outside this cached timer. Shared host, no CPU affinity/governor controls.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
