# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Bounded real-time transport/loop/session soak; no physical-audio claim."""
import argparse,gc,json,os,tempfile,weakref,inspect,hashlib
from pathlib import Path
from time import monotonic,sleep
import numpy as np,psutil,soundfile as sf
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport
from vocalscope import __version__


def main():
 p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=600);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 process=psutil.Process();rows=[];counts=dict(switches=0,seeks=0,pause_resume_pairs=0,sessions=0);weak=[];error=None;active=None
 def resources():
  return dict(wall_seconds=monotonic()-begin,rss_bytes=process.memory_info().rss,fd_count=process.num_fds(),threads=process.num_threads(),children=len(process.children()),cpu_percent=process.cpu_percent(None))
 begin=monotonic();process.cpu_percent(None);transport_sha256=hashlib.sha256(Path(inspect.getfile(Transport)).read_bytes()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='vocalscope-soak-') as temp:
  paths=[]
  for sr,channel in [(44100,0),(48000,1)]:
   data=np.zeros((sr*6,2),dtype='float32')
   for t in [.25,.75,1.25,2.25,3.25,4.25,5.25]:data[round(t*sr),channel]=.1
   path=Path(temp)/f'{sr}.wav';sf.write(path,data,sr,subtype='FLOAT');paths.append(path)
  session=Session(vocal=Source(paths[0]),piano=Source(paths[1]));rows.append(resources())
  try:
   # Repeated disposal before/after the sustained segment checks FD and wrapper
   # lifetimes separately from steady RSS/cache behavior.
   for _ in range(12):
    t=Transport(PlaybackConfig(sink='fakesink'));t.load(session).result(8);weak.append(weakref.ref(t.engine.pipeline));t.play().result(3);t.pause().result(3);t.close().result(5);assert t.wait_closed();counts['sessions']+=1
   gc.collect();rows.append(resources());active=Transport(PlaybackConfig(sink='fakesink'));active.load(session).result(8);active.set_loop(Loop(.2,1.2)).result(5);active.play().result(3)
   start=monotonic();next_op=start;next_sample=start;iteration=0
   while monotonic()-start<args.seconds:
    now=monotonic()
    if now>=next_op:
     active.set_mix(['vocal','piano','mix'][iteration%3]).result(3);counts['switches']+=1
     if iteration%2==0:active.pause().result(3);active.play().result(3);counts['pause_resume_pairs']+=1
     if iteration%3==0:active.seek(.21+(iteration%8)*.1).result(5);counts['seeks']+=1
     iteration+=1;next_op=now+.35
    if now>=next_sample:rows.append(resources());next_sample=now+2
    if active.snapshot().state==State.ERROR:raise RuntimeError(active.snapshot().error)
    sleep(.005)
   sustained=monotonic()-start;loops=active.snapshot().loop_count;active.close().result(5);assert active.wait_closed();active=None
   for _ in range(12):
    t=Transport(PlaybackConfig(sink='fakesink'));t.load(session).result(8);weak.append(weakref.ref(t.engine.pipeline));t.close().result(5);assert t.wait_closed();counts['sessions']+=1
  except Exception as exc:error=repr(exc);sustained=monotonic()-start if 'start' in locals() else 0;loops=active.snapshot().loop_count if active else 0
  finally:
   if active:active.close().result(5);active.wait_closed()
  del t;gc.collect();rows.append(resources())
 report=dict(schema_version='1.0.0',version=__version__,transport_sha256=transport_sha256,status='failed' if error else 'complete',error=error,requested_seconds=args.seconds,sustained_seconds=sustained,counts=counts,loop_restarts=loops,resources=rows,
  surviving_pipeline_wrappers=sum(r() is not None for r in weak),elapsed_seconds=monotonic()-begin,semantics='Test sink, real-time clock; mixed command stress differs from uninterrupted 10-minute playback. RSS includes caches/allocator. No claim of zero leaks or physical listening.')
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(args.output)
 if error:raise RuntimeError(error)


if __name__=='__main__':main()
