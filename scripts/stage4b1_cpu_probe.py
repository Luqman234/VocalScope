# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Repeated steady-state CPU probe; counts owner polls, no GTK or inference."""
import argparse,json,psutil
from pathlib import Path
from time import sleep,monotonic,thread_time
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import *

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--sink',default='pipewiresink');p.add_argument('--seconds',type=float,default=4);a=p.parse_args()
counts={'polls':0,'poll_cpu_seconds':0.};original=Transport._poll

def measured(self):
 start=thread_time()
 try:return original(self)
 finally:counts['polls']+=1;counts['poll_cpu_seconds']+=thread_time()-start
Transport._poll=measured
t=Transport(PlaybackConfig(sink=a.sink,master_gain=.03));process=psutil.Process()
try:
 t.load(Session(vocal=Source('data/vocadito/Audio/vocadito_1.wav'),piano=Source('results/stage4a-release-piano/piano.wav'))).result(10);t.set_mix('mix').result(4);t.play().result(3);sleep(.5);rows=[]
 for i in range(3):
  process.cpu_percent(None);count=counts['polls'];cpu=counts['poll_cpu_seconds'];begin=monotonic();sleep(a.seconds)
  rows.append({'elapsed_seconds':monotonic()-begin,'cpu_percent':process.cpu_percent(None),'owner_polls':counts['polls']-count,'poll_thread_cpu_seconds':counts['poll_cpu_seconds']-cpu,'rss_bytes':process.memory_info().rss})
finally:t.close().result(5);t.wait_closed()
a.output.write_text(json.dumps({'rows':rows},indent=2)+'\n')
