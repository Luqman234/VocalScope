# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Singer-disjoint note evaluation, both annotators, paired singer bootstrap.

Development selection precedes loading ANY held-out note reference. Historical
Stage 2 predictions are reusable only with matching audio identity and config.
"""
from dataclasses import asdict,replace
from pathlib import Path
import csv,json,hashlib,resource
from time import perf_counter
import numpy as np
from ..audio import load_audio
from ..models import AnalysisConfig
from ..backends import EstimatorConfig
from ..pitch import analyze_audio,to_analysis_result,library_versions
from ..datasets import Vocadito,digest
from ..prediction_cache import PredictionCache
from .dataset import load_notes,grouped_split,NoteReference
from .models import TranscriptionConfig,NoteEvent
from .pipeline import transcribe_analysis
from .onsets import extract_features
from .evaluation import evaluate,summarize
from .serialization import atomic_write,export_bundle
from . import ALGORITHM_VERSION

CANDIDATES=[TranscriptionConfig(),TranscriptionConfig(onset_threshold=.6),TranscriptionConfig(pitch_change=1.),TranscriptionConfig(min_duration=.1)]


def choose_configuration(development_ids,score):
    """Only supplied development identities reach the scoring callback."""
    trials=[]
    for config in CANDIDATES:
        values=[score(track,config) for track in development_ids]
        trials.append({'configuration':asdict(config),'development_macro_pitch_f1':float(np.mean(values))})
    best=max(range(len(trials)),key=lambda i:trials[i]['development_macro_pitch_f1'])
    return CANDIDATES[best],trials


def run_benchmark(dataset_path,output,*,estimators=('pyin','crepe'),prediction_report=None,cache_dir=None,seed=20261109,max_tracks=None):
    if max_tracks is not None and max_tracks<=0:raise ValueError('max_tracks must be positive.')
    if not estimators or any(b not in ('pyin','yin','crepe') for b in estimators) or len(set(estimators))!=len(estimators):raise ValueError('Choose distinct supported estimators.')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'results.json').exists():raise FileExistsError('Choose a new note benchmark output directory; existing evidence is protected.')
    begin=perf_counter();dataset=Vocadito(dataset_path);split=grouped_split(dataset.metadata,seed)
    development=split['development'][:max_tracks] if max_tracks else split['development']
    heldout=split['test'][:max_tracks] if max_tracks else split['test']
    config=AnalysisConfig();history=json.loads(Path(prediction_report).read_text()) if prediction_report else None
    if history and history['analysis']!=asdict(config):raise ValueError('Historical analysis configuration differs from the current benchmark.')
    cache=PredictionCache(cache_dir) if cache_dir else None
    rows_index={(r['track_id'],r['estimator']):r for r in history['predictions'] if r['status']=='ok'} if history else {}
    historical_sources={r['track_id']:r['audio_sha256'] for r in history['dataset']['tracks']} if history else {}
    data={};acoustics={};features={};references={};failures=[];selection={};all_rows=[];timings=[];manifest=[];projects={}
    # Capture the protocol BEFORE obtaining held-out note annotations.
    protocol={'algorithm_version':ALGORITHM_VERSION,'smoke_test':max_tracks is not None,'max_tracks_per_split':max_tracks,'split':split,'effective_development':development,'effective_test':heldout,
        'primary':'Equal weight A1/A2, track-macro onset+pitch F1; no best-of-two selection',
        'selection':'Prespecified four configurations, development only; ties choose first; each backend tuned separately',
        'candidates':[asdict(c) for c in CANDIDATES],'estimators':list(estimators),'source_code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    atomic_write(output/'protocol.json',(json.dumps(protocol,indent=2)+'\n').encode())

    def get_audio(track):
        if track not in data:
            tr=dataset.load_track(track);audio=load_audio(tr.audio_path,config);data[track]=(tr,audio)
            features[track]=extract_features(audio,.35)
        return data[track]

    def get_acoustic(track,backend):
        key=(track,backend)
        if key not in acoustics:
            tr,audio=get_audio(track);row=rows_index.get(key)
            settings=EstimatorConfig(estimator_id=backend,crepe_model='tiny')
            if row:
                if historical_sources.get(track)!=tr.audio_sha256:raise ValueError('Historical prediction refers to different audio.')
                if row['estimator_configuration']!=asdict(settings):raise ValueError('Historical estimator configuration differs.')
                cached=cache.load(row['cache_key']) if cache else None
                if cached is None:raise ValueError(f'Missing historical prediction cache for {track}/{backend}.')
                predicted,timing=cached
                a=to_analysis_result(audio,config,settings,predicted)
                timing={**timing,'prediction_cache_key':row['cache_key'],'reused_stage2':True}
            else:
                start=perf_counter();a=analyze_audio(audio,config,settings)
                timing={'total_processing_seconds':perf_counter()-start,'reused_stage2':False}
            acoustics[key]=a
            timings.append({'track_id':track,'backend':backend,**timing})
        return acoustics[key]

    def get_ref(track,annotator):
        key=(track,annotator)
        if key not in references:references[key]=load_notes(dataset,track,annotator)
        return references[key]

    def project(track,backend,c):
        tr,audio=get_audio(track)
        # Threshold changes affect candidate picking, not the extracted waveform.
        f=features[track]
        if c.onset_threshold!=.35:
            f=replace(f,candidates=tuple(b for b in f.candidates if b.strength>=c.onset_threshold))
        return transcribe_analysis(audio,get_acoustic(track,backend),c,features=f,source_sha256=tr.audio_sha256)

    # Failure is explicit and prevents a misleading common-set leaderboard.
    for backend in estimators:
        try:
            def score(track,c):
                p=project(track,backend,c)
                return np.mean([evaluate(get_ref(track,a),p.notes)['pitch']['f1'] for a in ('A1','A2')])
            chosen,trials=choose_configuration(development,score)
            selection[backend]={'configuration':asdict(chosen),'trials':trials,'track_ids_used':development,'heldout_ids_used':[]}
        except Exception as exc:failures.append({'backend':backend,'phase':'development','error':f'{type(exc).__name__}: {exc}'})
    atomic_write(output/'selection.json',(json.dumps(selection,indent=2,allow_nan=False)+'\n').encode())
    # Selection is now frozen. Held-out annotations may be accessed below.
    for track in development+heldout:
        tr,audio=get_audio(track)
        refs={a:get_ref(track,a) for a in ('A1','A2')}
        manifest.append({'track_id':track,'singer_id':tr.singer_id,'audio_sha256':tr.audio_sha256,'duration_seconds':tr.duration_seconds,
            'notes':{a:{'sha256':r.sha256,'count':len(r.frequencies),'max_release_beyond_audio_seconds':max(0.,float(r.intervals[:,1].max()-tr.duration_seconds))} for a,r in refs.items()}})
        for backend in estimators:
            if backend not in selection:continue
            for method in ('naive','pitch-only','combined'):
                try:
                    c=replace(TranscriptionConfig(**selection[backend]['configuration']),method=method)
                    p=project(track,backend,c);projects[(track,backend,method)]=p
                    for annotator in ('A1','A2'):
                        result=evaluate(refs[annotator],p.notes,p.acoustic.config.a4_hz)
                        all_rows.append({'track_id':track,'singer_id':tr.singer_id,'split':'test' if track in heldout else 'development',
                            'backend':backend,'method':method,'annotator':annotator,'metrics':result,'timings':p.timings,
                            'upstream_voiced_frames':int(p.acoustic.voiced.sum()),'note_frames_from_upstream_voicing':True})
                except Exception as exc:failures.append({'track_id':track,'backend':backend,'method':method,'phase':'evaluation','error':f'{type(exc).__name__}: {exc}'})
    aggregates=[]
    for partition in ('development','test'):
        for backend in estimators:
            for method in ('naive','pitch-only','combined'):
                for annotator in ('A1','A2'):
                    rows=[r for r in all_rows if (r['split'],r['backend'],r['method'],r['annotator'])==(partition,backend,method,annotator)]
                    aggregates.append({'split':partition,'backend':backend,'method':method,'annotator':annotator,'tracks':len(rows),'summary':summarize(rows)})
    comparisons=[]
    for backend in estimators:
        baseline={method:{} for method in ('naive','pitch-only','combined')}
        for r in all_rows:
            if r['split']=='test' and r['backend']==backend:
                baseline[r['method']].setdefault(r['singer_id'],[]).append(r['metrics']['pitch']['f1'])
        singers=sorted(set.intersection(*(set(x) for x in baseline.values())))
        rng=np.random.default_rng(seed)
        for method in ('naive','pitch-only'):
            differences=np.array([np.mean(baseline['combined'][s])-np.mean(baseline[method][s]) for s in singers])
            if len(differences):
                boot=differences[rng.integers(0,len(differences),size=(2000,len(differences)))].mean(axis=1)
                comparisons.append({'backend':backend,'comparison':'combined minus '+method,'singers':singers,'singer_macro_difference':float(differences.mean()),'ci95':np.percentile(boot,[2.5,97.5]).tolist(),'resamples':2000})
    agreement=[]
    for track in development+heldout:
        for ra,ea in [('A1','A2'),('A2','A1')]:
            r=get_ref(track,ra);e=get_ref(track,ea)
            # Preserve annotators' fractional frequencies for agreement; custom
            # duck-typed event fields avoid quantizing reference pitch to keys.
            from types import SimpleNamespace
            notes=[SimpleNamespace(start_seconds=float(iv[0]),end_seconds=float(iv[1]),midi_note=float(69+12*np.log2(f/440))) for iv,f in zip(e.intervals,e.frequencies)]
            agreement.append({'track_id':track,'reference':ra,'estimate':ea,'metrics':evaluate(r,notes)})
    report={'schema_version':'1.0.0','status':'complete' if not failures else 'incomplete','protocol':protocol,'dataset':dataset.identity(),'manifest':manifest,
        'selection':selection,'per_track':all_rows,'aggregates':aggregates,'paired_singer_bootstrap':comparisons,'inter_annotator':agreement,'failures':failures,
        'prediction_timings':timings,'versions':library_versions(),'elapsed_seconds':perf_counter()-begin,'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'metric_conventions':'mir_eval one-to-one matching, onset 50ms, pitch 50c, offset max(20% ref duration,50ms); final discrete piano key evaluated; null undefined denominators',
        'diagnostics':'Fragmentation/merging: pitch-matched temporal intersections >= min(50ms,25% reference duration). Repeated failures: adjacent references within 50c sharing one prediction. Rest notes: zero overlap with either voiced note interval, per annotator; upstream voicing is retained separately.'}
    atomic_write(output/'results.json',(json.dumps(report,indent=2,allow_nan=False)+'\n').encode())
    write_reports(report,output)
    for track in heldout[:3]:
        for backend in estimators:
            p=projects.get((track,backend,'combined'))
            if p:export_bundle(p,output/'examples'/f'{track}-{backend}')
    return report


def write_reports(report,output):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    rows=[]
    for r in report['per_track']:
        row={k:r[k] for k in ('track_id','singer_id','split','backend','method','annotator')}
        for name in ('onset','pitch','offset'):
            row.update({name+'_'+k:v for k,v in r['metrics'][name].items()})
        row.update(r['metrics']['diagnostics']);rows.append(row)
    def csv_file(path,rows):
        if not rows:return
        with path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    csv_file(output/'per-track.csv',rows)
    agg=[];lines=['# Stage 3 measured note benchmark','',f"Status: {report['status']}. Both annotators scored separately; primary policy averages them equally.",'',
        '| Backend | Method | Annotator | Tracks | Onset F1 | Pitch+onset F1 | Pitch+onset+offset F1 |','|---|---|---|---:|---:|---:|---:|']
    if report['protocol'].get('smoke_test'):lines.insert(2,'**SMOKE TEST: limited tracks per split; not a full-corpus experiment.**')
    if report['failures']:lines.insert(2,'**INCOMPLETE: '+str(len(report['failures']))+' failures; inspect results.json before comparing scores.**')
    for r in report['aggregates']:
        row={k:r[k] for k in ('split','backend','method','annotator','tracks')}
        row.update({name+'_macro_f1':r['summary'][name]['macro']['f1'] for name in ('onset','pitch','offset')});agg.append(row)
        if r['split']=='test':lines.append('| '+ ' | '.join(str(row[k]) if k.endswith('f1') is False else f'{100*row[k]:.2f}%' if row[k] is not None else 'undefined' for k in ('backend','method','annotator','tracks','onset_macro_f1','pitch_macro_f1','offset_macro_f1'))+' |')
    csv_file(output/'aggregate.csv',agg)
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n\nFull metric counts, failures, timings and singer bootstrap intervals: results.json.\n')
    selected=[r for r in agg if r['split']=='test']
    fig=Figure(figsize=(14,5));ax=fig.subplots();x=np.arange(len(selected))
    ax.bar(x,[r['pitch_macro_f1'] or 0 for r in selected]);ax.set_xticks(x,[f"{r['backend']}\n{r['method']}\n{r['annotator']}" for r in selected],rotation=45,ha='right');ax.set_ylabel('Track-macro onset + pitch F1');fig.tight_layout();FigureCanvasAgg(fig).print_png(output/'accuracy.png')
