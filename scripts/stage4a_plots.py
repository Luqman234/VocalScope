# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Static measured waveform/latency and rendering-performance report figures."""
import argparse,json
from pathlib import Path
import numpy as np
import soundfile as sf
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,default=Path('results/stage4a-validation-final/a4/piano.wav'));p.add_argument('--performance',type=Path,default=Path('reports/stage4a/performance.json'));p.add_argument('--output',type=Path,default=Path('reports/stage4a'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
audio,sr=sf.read(a.audio,always_2d=True);mono=audio.mean(axis=1);times=np.arange(len(mono))/sr
fig=Figure(figsize=(11,6));upper,lower=fig.subplots(2,1)
selected=(times>=.195)&(times<=.23);upper.plot(times[selected],mono[selected],linewidth=.8)
upper.axvline(.2,color='darkorange',label='Scheduled note-on');first=np.flatnonzero(np.max(abs(audio),axis=1)>1e-7)[0]/sr;upper.axvline(first,color='green',linestyle='--',label='First stereo magnitude >1e-7')
upper.set_xlabel('Seconds');upper.set_ylabel('Float PCM');upper.legend(fontsize=8);upper.set_title('Measured TimGM6mb A4 attack: scheduled event and acoustic response')
hop=round(.005*sr);centers=[];rms=[]
for i in range(0,len(mono)-hop,hop):centers.append((i+hop/2)/sr);rms.append(20*np.log10(max(1e-8,float(np.sqrt(np.mean(mono[i:i+hop]**2))))))
lower.plot(centers,rms);lower.axvline(.8,color='darkorange',label='Unchanged note-off');lower.axvspan(.8,len(mono)/sr,color='green',alpha=.08,label='Rendered release/tail');lower.set_ylim(-120,-20);lower.set_ylabel('5 ms RMS (dBFS)');lower.set_xlabel('Seconds');lower.legend(fontsize=8);fig.tight_layout();FigureCanvasAgg(fig).print_png(a.output/'render-diagnostics.png')
x=json.loads(a.performance.read_text());rows=[r for r in x['rows'] if 'total_seconds' in r];fig=Figure(figsize=(10,5));ax=fig.subplots();positions=np.arange(len(rows));bottom=np.zeros(len(rows))
for key,label in [('synth_initialization_seconds','Synth init'),('soundfont_loading_seconds','Font load'),('render_seconds','Render / spool'),('wav_encoding_seconds','WAV encode'),('flac_encoding_seconds','FLAC encode')]:
 values=np.array([r['timings'][key] for r in rows]);ax.bar(positions,values,bottom=bottom,label=label);bottom+=values
ax.scatter(positions,[r['total_seconds'] for r in rows],color='black',marker='_',s=100,label='Total including verification/publication');ax.set_xticks(positions,[str(r['content_duration_seconds'])+(' s cold' if r['cold_process_first_call'] else ' s warm') for r in rows]);ax.set_ylabel('Elapsed seconds');ax.set_title('CPU-only stereo 48 kHz; TimGM6mb; fresh synth/font each run');ax.legend(fontsize=8);fig.tight_layout();FigureCanvasAgg(fig).print_png(a.output/'performance.png')
