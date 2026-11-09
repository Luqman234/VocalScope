# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Isolated non-flushing segment-loop experiment, never production policy."""
import json,tempfile
from pathlib import Path
from time import monotonic,sleep
import numpy as np,soundfile as sf
from vocalscope.playback.engine import Engine
from vocalscope.playback.gst import bindings
from vocalscope.playback.models import Source,PlaybackConfig
from vocalscope.playback.sources import discover
Gst,*_=bindings();results=[]
with tempfile.TemporaryDirectory() as temp:
 for rates in [(48000,48000),(44100,48000)]:
  metadata={}
  for name,sr,channel in [('vocal',rates[0],0),('piano',rates[1],1)]:
   path=Path(temp)/(name+'.wav');y=np.zeros((sr*2,2),dtype='float32');y[round(.75*sr),channel]=.1;sf.write(path,y,sr,subtype='FLOAT');metadata[name]=discover(Source(path))
  e=Engine(metadata,PlaybackConfig(sink='appsink'),'appsink');messages=[];error=None
  try:
   e.pipeline.set_state(Gst.State.PAUSED);e.pipeline.get_state(2*Gst.SECOND);e.mixer.set('mix',0,{},immediate=True);e.seek(.6,.9,True);e.pipeline.set_state(Gst.State.PLAYING);start=monotonic();repeats=0
   while monotonic()-start<4:
    m=e.bus.timed_pop(10*Gst.MSECOND)
    if not m:continue
    if m.type==Gst.MessageType.ERROR:error=m.parse_error()[0].message;break
    if m.type==Gst.MessageType.SEGMENT_DONE:
     messages.append({'source':m.src.get_name(),'seqnum':m.get_seqnum()})
     if m.src==e.pipeline and repeats<8:
      event=Gst.Event.new_seek(1.,Gst.Format.TIME,Gst.SeekFlags.SEGMENT|Gst.SeekFlags.ACCURATE,Gst.SeekType.SET,600_000_000,Gst.SeekType.SET,900_000_000)
      e.pipeline.send_event(event);repeats+=1
   captured=e.captured();sizes=[];count=0;last=-1
   for pts,data in captured:
    if pts<last:sizes.append(count);count=0
    last=pts;count+=len(data)
   sizes.append(count);results.append({'input_rates':rates,'segment_messages':messages,'nonflushing_repeats_requested':repeats,'cycle_frame_counts':sizes,'expected_frames_per_cycle':14400,'error':error})
  finally:e.close()
Path('reports/stage4b1/segment-experiment.json').write_text(json.dumps({'production_enabled':False,'rows':results},indent=2)+'\n')
