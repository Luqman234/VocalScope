# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Serial fresh-synth cold/warm-process render and encoding measurements."""
import argparse,json,tempfile,platform,resource
from pathlib import Path
from time import perf_counter
from vocalscope.transcription.models import NoteEvent
from vocalscope.synthesis.models import RenderConfig
from vocalscope.synthesis.export import export_audio
from vocalscope.synthesis.project import read_project_snapshot
from vocalscope.synthesis.process import render_snapshot_in_process

p=argparse.ArgumentParser();p.add_argument('--soundfont',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path);a=p.parse_args();rows=[]
with tempfile.TemporaryDirectory() as work:
 for i,duration in enumerate([1,1,5,15,120]):
  notes=[NoteEvent(str(j),j*.5,min(duration,j*.5+.4),[60,62,64,67][j%4],float([60,62,64,67][j%4]),0.) for j in range(duration*2)]
  start=perf_counter();result=export_audio(notes,a.soundfont,Path(work)/str(i),RenderConfig(sample_rate=48000),duration_seconds=float(duration));total=perf_counter()-start
  r=result['report'];rows.append({'content_duration_seconds':duration,'output_duration_seconds':r['duration_seconds'],'cold_process_first_call':i==0,'synth_policy':'new synth and SoundFont for every call; later calls share warm Python/native library and filesystem cache',
   'notes':len(notes),'timings':r['timings'],'total_seconds':total,'content_duration_over_render_time':duration/r['timings']['render_seconds'],
   'content_duration_over_total_time':duration/total,'resources':r['resources'],'font':r['soundfont'],'backend':r['backend']})
 if a.project:
  start=perf_counter();snapshot=read_project_snapshot(a.project);result=render_snapshot_in_process(snapshot,a.soundfont,Path(work)/'project',RenderConfig(sample_rate=48000));total=perf_counter()-start
  rows.append({'project':str(a.project),'content_duration_seconds':snapshot['duration_seconds'],'notes':len(snapshot['notes']),'project_to_wav_and_flac_seconds':total,
   'timings':result['report']['timings'],'resources':result['report']['resources'],'provenance':result['report']['provenance']})
report={'cpu':next(l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'platform':platform.platform(),
 'sample_rate':48000,'rows':rows,'semantics':'No pitch estimation. Serial runs, shared host without governor/affinity lock. First fresh-process renderer initialization includes optional binding load; later runs use fresh synth/font in a warm process. Filesystem caches not flushed. Full time includes spool/encoding/read-back/fsync/publication, excluding interpreter startup except explicit project worker measurement. PCM chunk=4096 stereo float32 frames, fixed RAM buffering; native font allocation and event metadata additional.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print('Measured',len(rows),'rendering performance cases')
