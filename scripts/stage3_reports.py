# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Derived summaries and explicitly reference-labeled overlays; no parameter tuning."""
import csv,json,argparse
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from vocalscope.datasets import Vocadito
from vocalscope.transcription.dataset import load_notes
from vocalscope.transcription.serialization import load_project
from vocalscope.transcription.plotting import draw
from vocalscope.transcription.evaluation import summarize

parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);parser.add_argument('--dataset-path',type=Path,default=Path('data/vocadito'));args=parser.parse_args()
x=json.loads(args.report.read_text());out=args.report.parent;data=Vocadito(args.dataset_path);rows=x['per_track'];singers=[];aggregate=[]
for split in ['development','test']:
 for backend in x['protocol']['estimators']:
  for method in ['naive','pitch-only','combined']:
   for singer in sorted({r['singer_id'] for r in rows if r['split']==split}):
    selected=[r for r in rows if (r['split'],r['backend'],r['method'],r['singer_id'])==(split,backend,method,singer)]
    if selected:singers.append({'split':split,'backend':backend,'method':method,'singer_id':singer,'tracks':len(selected)//2,'onset_f1':float(np.mean([r['metrics']['onset']['f1'] for r in selected])),'pitch_f1':float(np.mean([r['metrics']['pitch']['f1'] for r in selected])),'offset_f1':float(np.mean([r['metrics']['offset']['f1'] for r in selected]))})
   selected=[r for r in rows if (r['split'],r['backend'],r['method'])==(split,backend,method)]
   both=summarize(selected);valid=[r for r in selected if r['metrics']['average_overlap_ratio'] is not None]
   both['overlap']={'macro':float(np.mean([r['metrics']['average_overlap_ratio'] for r in valid])) if valid else None,
    'matched_pair_weighted':float(sum(r['metrics']['average_overlap_ratio']*r['metrics']['offset']['matches'] for r in valid)/sum(r['metrics']['offset']['matches'] for r in valid)) if valid else None}
   aggregate.append({'split':split,'backend':backend,'method':method,'equal_annotator_summary':both,'diagnostic_totals':{k:sum(r['metrics']['diagnostics'][k] for r in selected) for k in selected[0]['metrics']['diagnostics']} if selected else {}})
with (out/'singer-scores.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(singers[0]));writer.writeheader();writer.writerows(singers)
comparison=None
if {'pyin','crepe'}<=set(x['protocol']['estimators']):
 paired={b:{s['singer_id']:s['pitch_f1'] for s in singers if s['split']=='test' and s['backend']==b and s['method']=='combined'} for b in ['pyin','crepe']}
 names=sorted(set(paired['pyin'])&set(paired['crepe']));differences=np.array([paired['crepe'][s]-paired['pyin'][s] for s in names]);rng=np.random.default_rng(x['protocol']['split']['seed']);boot=differences[rng.integers(0,len(names),(2000,len(names)))].mean(axis=1)
 comparison={'comparison':'CREPE-tiny minus pYIN, combined, both annotators equally weighted','singer_ids':names,'singer_macro_difference':float(differences.mean()),'ci95':np.percentile(boot,[2.5,97.5]).tolist(),'resamples':2000}
agreement={}
for partition,ids in [('all',data.track_ids),('test',x['protocol']['effective_test'])]:
 selected=[r for r in x['inter_annotator'] if r['track_id'] in ids]
 agreement[partition]=summarize(selected)
supplement={'equal_annotator_aggregates':aggregate,'singer_scores':singers,'backend_comparison':comparison,'inter_annotator_symmetric':agreement,
 'annotation_counts':{a:sum(m['notes'][a]['count'] for m in x['manifest']) for a in ['A1','A2']},
 'annotation_overrun_policy':'Original releases preserved, verified <=10ms beyond audio on tracks30/A1 and31/both; predictions bounded by audio.',
 'uncertainty':'2000 paired singer-cluster bootstrap resamples, fixed seed; 11 held-out singers. Conditional on this small fixed corpus/split; no claim of external generalization.'}
(out/'supplement.json').write_text(json.dumps(supplement,indent=2,allow_nan=False)+'\n')
for track in x['protocol']['effective_test'][:3]:
 for backend in x['protocol']['estimators']:
  example=next((out/'examples'/f'{track}-{backend}').glob('*.json'),None)
  if not example:continue
  project=load_project(example)
  for annotator in ['A1','A2']:
   ref=load_notes(data,track,annotator);reference=[(float(s),float(e),float(69+12*np.log2(f/440))) for (s,e),f in zip(ref.intervals,ref.frequencies)]
   fig=Figure(figsize=(12,7));axes=draw(fig,project,reference=reference);axes[0].set_title(f'EVALUATION ONLY: Vocadito {track}, {backend}; red reference {annotator}',fontsize=10)
   FigureCanvasAgg(fig).print_png(out/f'reference-{track}-{backend}-{annotator}.png')
# Runtime excludes reused estimator inference; report both quantities separately.
fig=Figure(figsize=(10,5));ax=fig.subplots()
for backend in x['protocol']['estimators']:
 selected=[r for r in rows if r['backend']==backend and r['method']=='combined' and r['annotator']=='A1']
 ax.scatter([next(m['duration_seconds'] for m in x['manifest'] if m['track_id']==r['track_id']) for r in selected],[r['timings']['cached_pitch_to_notes_seconds'] for r in selected],label=backend)
ax.set_xlabel('Audio duration (s)');ax.set_ylabel('Notes from cached pitch (s; feature cache reused)');ax.legend();fig.tight_layout();FigureCanvasAgg(fig).print_png(out/'runtime.png')
fig=Figure(figsize=(11,5));ax=fig.subplots();selected=[a for a in aggregate if a['split']=='test'];positions=np.arange(len(selected))
for offset,key,label in [(-.25,'missed_notes','Missed'),(0,'extra_notes','Extra'),(.25,'incorrect_merging','Merge intersections')]:
 ax.bar(positions+offset,[a['diagnostic_totals'][key]/2 for a in selected],width=.25,label=label)
ax.set_xticks(positions,[a['backend']+'\n'+a['method'] for a in selected]);ax.set_ylabel('Count averaged over annotators');ax.legend();fig.tight_layout();FigureCanvasAgg(fig).print_png(out/'errors.png')
print(json.dumps({'counts':supplement['annotation_counts'],'backend_comparison':comparison},indent=2))
