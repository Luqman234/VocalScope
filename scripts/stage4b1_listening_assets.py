# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Explicit diagnostic channel tones; never a production piano substitute."""
import argparse,io
import numpy as np
import soundfile as sf
from vocalscope.transcription.serialization import atomic_write
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();rate=48000
audio=np.zeros((rate*4,2),dtype='float32')
for start,end,frequency,channels in [(0.,1.,440,[0]),(1.5,2.5,660,[1]),(3.,4.,440,[0,1])]:
 t=np.arange(round((end-start)*rate))/rate;fade=np.minimum(np.minimum(t/.01,((end-start)-t)/.01),1);signal=.05*np.sin(2*np.pi*frequency*t)*fade
 for channel in channels:audio[round(start*rate):round(end*rate),channel]=signal
buffer=io.BytesIO();sf.write(buffer,audio,rate,format='WAV',subtype='FLOAT');atomic_write(a.output,buffer.getvalue());print(a.output)
