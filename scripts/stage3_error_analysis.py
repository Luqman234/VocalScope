# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Post-evaluation diagnostics only: no fitting, threshold changes or relabeling."""
import argparse,json
from dataclasses import replace
from pathlib import Path
import numpy as np
from vocalscope.datasets import Vocadito
from vocalscope.models import AnalysisConfig
from vocalscope.backends import EstimatorConfig
from vocalscope.audio import load_audio
from vocalscope.pitch import to_analysis_result
from vocalscope.prediction_cache import PredictionCache
from vocalscope.transcription.dataset import load_notes
from vocalscope.transcription.models import TranscriptionConfig
from vocalscope.transcription.onsets import extract_features
from vocalscope.transcription.pipeline import transcribe_analysis

p=argparse.ArgumentParser();p.add_argument('--dataset-path',type=Path,default=Path('data/vocadito'));p.add_argument('--report',type=Path,required=True);p.add_argument('--prediction-report',type=Path,default=Path('reports/stage2/vocadito-final/results.json'));p.add_argument('--cache-dir',type=Path,default=Path('reports/stage2/cache'));a=p.parse_args()
x=json.loads(a.report.read_text());history=json.loads(a.prediction_report.read_text());cache=PredictionCache(a.cache_dir);v=Vocadito(a.dataset_path);index={(r['track_id'],r['estimator']):r for r in history['predictions']};rows=[]
for track in x['protocol']['effective_test']:
 tr=v.load_track(track);audio=load_audio(tr.audio_path);features=extract_features(audio)
 for backend in x['protocol']['estimators']:
  c=TranscriptionConfig(**x['selection'][backend]['configuration']);raw,timing=cache.load(index[(track,backend)]['cache_key'])
  result=to_analysis_result(audio,AnalysisConfig(),EstimatorConfig(**index[(track,backend)]['estimator_configuration']),raw)
  project=transcribe_analysis(audio,result,c,features=replace(features,candidates=tuple(b for b in features.candidates if b.strength>=c.onset_threshold)),source_sha256=tr.audio_sha256)
  for annotator in ['A1','A2']:
   ref=load_notes(v,track,annotator);events=[]
   for note in project.notes:
    overlap=np.maximum(0,np.minimum(ref.intervals[:,1],note.end_seconds)-np.maximum(ref.intervals[:,0],note.start_seconds))
    if np.any(overlap>1e-8):continue
    centers=result.time_seconds[note.source_start_frame:note.source_end_frame];voiced=result.voiced[note.source_start_frame:note.source_end_frame]
    right=np.searchsorted(tr.reference_times,centers);right=np.clip(right,0,len(tr.reference_times)-1);left=np.maximum(right-1,0)
    nearest=np.where(abs(centers-tr.reference_times[left])<=abs(centers-tr.reference_times[right]),left,right)
    truth=tr.reference_f0[nearest]>0
    fraction=float(np.mean(~truth[voiced])) if voiced.any() else None
    events.append({'note_id':note.note_id,'start_seconds':note.start_seconds,'end_seconds':note.end_seconds,'reference_f0_unvoiced_fraction_at_emitted_pitch_frames':fraction,
      'diagnosis':'upstream_false_voicing_supported' if fraction is not None and fraction>.5 else 'note_vs_f0_annotation_or_boundary_disagreement'})
   rows.append({'track_id':track,'backend':backend,'annotator':annotator,'false_rest_events':events})
(a.report.parent/'rest-error-analysis.json').write_text(json.dumps({'rows':rows,'definitions':'Events with zero temporal intersection with any note by the selected annotator. F0 reference aligned to original emitted pitch centers by nearest timestamp; ties earlier. >50% unvoiced reference support suggests upstream voicing, not proof of musical intent. This is descriptive and does not modify any prediction.'},indent=2,allow_nan=False)+'\n')
print('Rest false events',sum(len(r['false_rest_events']) for r in rows),'across both annotators/backends')
