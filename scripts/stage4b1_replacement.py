# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Measured preparation/preroll and clock-paced PCM replacement interruption."""
import argparse,json
from pathlib import Path
from time import monotonic,sleep
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import *

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cycles',type=int,default=8);a=p.parse_args()
t=Transport(PlaybackConfig(sink='appsink'));rows=[]
try:
 t.load(Session(vocal=Source('data/vocadito/Audio/vocadito_1.wav'),piano=Source('results/stage4a-release-piano/piano.wav'))).result(10);t.set_mix('mix').result(4);t.seek(4.).result(5);t.play().result(3);sleep(.2)
 for i in range(a.cycles):
  paused=i%2==1
  if paused:t.pause().result(3)
  else:t.play().result(3);sleep(.1)
  before=t.diagnostics().result(3);old=before['capture_arrivals'][-1];position=t.snapshot().position_seconds;begin=monotonic()
  t.replace_piano(Source('results/stage4a-release-piano/piano.wav'),i+1).result(8);ack=monotonic()-begin;after=t.diagnostics().result(3)
  gap=None
  if not paused:
   deadline=monotonic()+3
   while not after['capture_arrivals'] and monotonic()<deadline:sleep(.005);after=t.diagnostics().result(3)
   first=after['capture_arrivals'][0];gap=first['arrival_monotonic']-(old['arrival_monotonic']+old['frames']/48000)
  else:first=None
  rows.append({'paused':paused,'api_elapsed_seconds':ack,'position_before':position,'position_after_ack':t.snapshot().position_seconds,'position_error_seconds':t.snapshot().position_seconds-position,
   'clock_paced_pcm_interruption_seconds':gap,'first_new_buffer_media_ns':first['media_ns'] if first else None,'history':after['history'][-1]})
finally:t.close().result(5);assert t.wait_closed()
a.output.write_text(json.dumps({'status':'complete','rows':rows,'semantics':'Appsink arrival gap minus previous block duration. Software PCM delivery, not electrical/acoustic latency; paused durations are API preparation only.'},indent=2)+'\n')
