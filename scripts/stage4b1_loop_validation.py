# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""PCM loop boundaries, exact frame counts and real sink-clock arrival gaps."""
import argparse,hashlib,json,tempfile
from pathlib import Path
from time import monotonic,sleep
import numpy as np,soundfile as sf
from vocalscope.playback.models import *
from vocalscope.playback.transport import Transport


class Cycles:
 def __init__(self,start,end):
  self.start=start;self.end=end;self.expected=round((end-start)*48000);self.previous=-1;self.blocks=[];self.completed=[];self.partial=[];self.reference=None;self.last=None
 def feed(self,rows):
  for pts,data in rows:
   if pts<self.previous:self.finish(False)
   self.previous=pts;self.blocks.append(data)
 def finish(self,last):
  if not self.blocks:return
  a=np.concatenate(self.blocks);self.blocks=[]
  if len(a)!=self.expected:
   self.partial.append({'frames':len(a),'expected':self.expected,'last':last});return
  if self.reference is None:self.reference=a.copy()
  peaks=[]
  for channel in [0,1]:
   indices=np.flatnonzero(abs(a[:,channel])>.005)
   groups=np.split(indices,np.flatnonzero(np.diff(indices)>240)+1) if len(indices) else []
   peaks.append([int(g[np.argmax(abs(a[g,channel]))]) for g in groups])
  self.completed.append({'frames':len(a),'sha256':hashlib.sha256(a.tobytes()).hexdigest(),'peak':float(np.max(abs(a))),
   'peaks_samples':peaks,
   'max_difference_from_first_cycle':float(np.max(abs(a-self.reference))),
   'boundary_jump':float(np.max(abs(a[0]-self.last))) if self.last is not None else None})
  self.last=a[-1].copy()


def run_case(vocal,piano,start,end,cycles=6,seconds=None):
 t=Transport(PlaybackConfig(sink='appsink',capture_seconds=5));observer=Cycles(start,end);arrivals=[];last_arrival=0;next_diag=0
 try:
  t.load(Session(vocal=Source(vocal),piano=Source(piano))).result(9);t.set_mix('mix').result(5);t.set_loop(Loop(start,end)).result(5);t.capture(True).result(3);t.play().result(3);begin=monotonic()
  while t.snapshot().loop_count<cycles if seconds is None else monotonic()-begin<seconds:
   if t.snapshot().state==State.ERROR:raise RuntimeError(t.snapshot().error)
   if monotonic()-begin>(seconds+10 if seconds else (end-start+.5)*(cycles+2)):raise TimeoutError('Loop validation timeout')
   observer.feed(t.capture(True).result(3))
   if monotonic()>next_diag:
    d=t.diagnostics().result(3)
    for row in d['capture_arrivals']:
     if row['arrival_monotonic']>last_arrival:arrivals.append(row)
    if arrivals:last_arrival=arrivals[-1]['arrival_monotonic']
    next_diag=monotonic()+.8
   sleep(.01)
  t.pause().result(5);observer.feed(t.capture(True).result(3));observer.finish(True);diag=t.diagnostics().result(3)
  for r in diag['capture_arrivals']:
   if r['arrival_monotonic']>last_arrival:arrivals.append(r)
  first=[];previous=-1
  for r in arrivals:
   if r['media_ns']<previous or not first:first.append(r['arrival_monotonic'])
   previous=r['media_ns']
  excess=np.diff(first)-(end-start)
  incomplete=[r for r in observer.partial if not r['last']]
  result={'start':start,'end':end,'duration':end-start,'elapsed_seconds':monotonic()-begin,'loop_restarts':t.snapshot().loop_count,'complete_cycles':len(observer.completed),
   'cycles':observer.completed,'partial_cycles':observer.partial,'failed_or_incomplete_internal_cycles':len(incomplete),
   'arrival_interval_excess_ms':(excess*1000).tolist(),'arrival_gap_semantics':'Clock-synchronized appsink callbacks, not physical acoustic output.',
   'history':diag['history']}
  if not observer.completed or incomplete:raise RuntimeError(f'Incomplete loop PCM: {result}')
  return result
 finally:t.close().result(5);assert t.wait_closed()


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--soak-seconds',type=float,default=0);p.add_argument('--vocal',type=Path,default=Path('data/vocadito/Audio/vocadito_1.wav'));p.add_argument('--piano',type=Path,default=Path('results/stage4a-release-piano/piano.wav'));args=p.parse_args();rows=[]
 with tempfile.TemporaryDirectory(prefix='vocalscope-loop-') as temp:
  files={}
  for kind in ['sine','impulses','smooth','phrases']:
   paths=[]
   for rate,channel,ext in [(44100,0,'wav'),(48000,1,'flac')]:
    time=np.arange(rate*6)/rate;s=.1*np.sin(2*np.pi*220*time)
    if kind=='impulses':
     s=np.zeros_like(time)
     for at in [.225,.25,.75,1.25,2.25,3.25,4.25,5.25]:s[round(at*rate)]=.1
    if kind=='smooth':s*=.5-.5*np.cos(2*np.pi*time)
    if kind=='phrases':s*=np.clip(np.minimum((time%1)*100,(.6-time%1)*100),0,1)
    y=np.zeros((len(s),2),dtype='float32');y[:,channel]=s;path=Path(temp)/f'{kind}-{rate}.{ext}';sf.write(path,y,rate,subtype='FLOAT' if ext=='wav' else 'PCM_24');paths.append(path)
   files[kind]=paths
  for kind,start,end in [('sine',0.,.05),('sine',.21,.37),('smooth',1.,2.),('phrases',1.,4.),('impulses',.6,.9),('impulses',5.,5.9)]:
   r=run_case(*files[kind],start,end);r['signal']=kind;rows.append(r)
   if kind=='impulses':validate_impulses(r)
  for name,start,end in [('human',2.,3.),('human_release',31.4,32.),('human_end',33.,34.5)]:
   r=run_case(args.vocal,args.piano,start,end);r['signal']=name;rows.append(r)
  if args.soak_seconds:
   r=run_case(*files['impulses'],.2,1.2,seconds=args.soak_seconds);r['signal']='multi_minute_impulses';rows.append(r);validate_impulses(r)
 report={'schema_version':'1.0.0','status':'complete','rows':rows,'transition_policy':'exact hard cut; flushing seeks; no sample smoothing/crossfade','pcm_tolerance_samples':2,'physical_listening':'unverified'}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(args.output)


def validate_impulses(row):
 expected=[round((t-row['start'])*48000) for t in [.225,.25,.75,1.25,2.25,3.25,4.25,5.25] if row['start']<=t<row['end']]
 errors=[];relative=[]
 for cycle in row['cycles']:
  left,right=cycle['peaks_samples']
  if len(left)!=len(expected) or len(right)!=len(expected):raise RuntimeError(f'Impulse count mismatch: {cycle}')
  errors.extend(abs(np.asarray(left)-expected));errors.extend(abs(np.asarray(right)-expected));relative.extend(abs(np.asarray(left)-right))
 row['max_ground_truth_impulse_error_samples']=int(max(errors,default=0));row['max_relative_alignment_samples']=int(max(relative,default=0))
 if max(errors,default=0)>2 or max(relative,default=0)>2:raise RuntimeError(f'Impulse timing exceeded prespecified 2-sample tolerance: {row}')


if __name__=='__main__':main()
