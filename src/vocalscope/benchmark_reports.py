# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Machine-readable evidence, comparison figures and honest coverage reporting."""

import csv
import json
from pathlib import Path
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator
from .notes import hz_to_midi, note_name


def _csv(path: Path,rows: list[dict]):
    if not rows:
        path.write_text('status\nno_measurements\n');return
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def _save(figure: Figure,path: Path):
    FigureCanvasAgg(figure).print_png(path);figure.clear()


def write_reports(report: dict,output: Path,tracks: dict,predictions: dict):
    output=Path(output)
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    failures=[{'track_id':r['track_id'],'estimator':r['estimator'],'status':'failed','error':r['error']}
              for r in report['predictions'] if r['status']!='ok']
    _csv(output/'per-track.csv',[{'status':'ok',**r} for r in report['per_track']]+failures)
    _csv(output/'performance.csv',[{'track_id':r['track_id'],'estimator':r['estimator'],'cached':r.get('cached'),
                                   **r['timing']} for r in report['predictions'] if r['status']=='ok'])
    aggregate_rows=[]
    md=['# VocalScope Stage 2 benchmark', '',
        f"Status: **{report['status']}**. Dataset: Vocadito v3, {report['dataset']['source']}, {report['dataset']['license']}.",
        report['dataset']['attribution'], '',
        f"Split counts: {report['dataset']['split_counts']}. Smoke/reduced-track run: {report['dataset']['smoke_test']}.",
        'No model training. Thresholds, when selected, use development tracks only. Each track stays in one partition.',
        '', 'Alignment: '+report['alignment']+'.', 'Metrics: '+report['metrics_convention']+'.', '',
        'Baseline pYIN settings remain available unchanged. YIN is a related classical baseline; CREPE is the independent neural family.',
        f"CREPE variant in this run: {report['settings']['crepe_model']}; CPU threads {report['settings']['threads']}; batch size {report['settings']['crepe_batch_size']}.",
        '', 'Frame-weighted metrics pool reference frames. Macro metrics average defined per-track scores; undefined denominators are null, not zero.',
        'Pitch error percentiles and octave error condition on mutually voiced frames. RPA/RCA and overall accuracy include voicing misses.',
        'No frames are treated as independent subjects in uncertainty estimates. Paired differences resample whole tracks.', '']
    def fmt(v,percent=False):return '—' if v is None else f'{v*100 if percent else v:.3f}'
    for key,comparison in report['comparisons'].items():
        md += [f'## {key}', '', '| Estimator | Status | Compared / requested tracks | Frame RPA50 % | Macro RPA50 % | Recall % | False alarm % | Overall % | Wall s | Peak RSS MiB |',
               '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for estimator,summary in comparison['estimators'].items():
            weighted=summary['frame_weighted'] or {};macro=summary['track_macro'] or {}
            aggregate_rows.append({'comparison':key,'estimator':estimator,'status':summary['status'],
                                   'tracks':summary['tracks'],'requested_tracks':summary['requested_tracks'],
                                   **{f'frame_{k}':v for k,v in weighted.items()},**{f'macro_{k}':v for k,v in macro.items()},
                                   'total_processing_seconds':summary['total_processing_seconds'],
                                   'peak_process_rss_mib':summary['peak_process_rss_mib']})
            md.append(f"| {estimator} | {summary['status']} | {summary['tracks']} / {summary['requested_tracks']} | {fmt(weighted.get('raw_pitch_accuracy_50c'),True)} | {fmt(macro.get('raw_pitch_accuracy_50c'),True)} | {fmt(weighted.get('voicing_recall'),True)} | {fmt(weighted.get('voicing_false_alarm_rate'),True)} | {fmt(weighted.get('overall_accuracy'),True)} | {fmt(summary['total_processing_seconds'])} | {fmt(summary['peak_process_rss_mib'])} |")
            if summary['excluded_track_ids']:md.append(f"\nExcluded from primary comparison for {estimator}: {summary['excluded_track_ids']} (see explicit prediction failures).\n")
        md+=['','Paired macro-RPA50 differences (b − a), 95% percentile track-bootstrap intervals:','']
        for pair in comparison['paired_rpa50']:
            md.append(f"- {pair['b']} − {pair['a']}: {pair['mean_difference']}; CI {pair['ci95_track_bootstrap']}; {pair['tracks']} paired tracks, {pair['resamples']} resamples.")
        md+=['']
    _csv(output/'aggregate.csv',aggregate_rows)
    md+=['## Failure and timing audit','',f"Prediction failures: {len(failures)}. Requested and effective IDs are recorded explicitly in results.json and dataset_manifest.json.",
         'Memory is each backend process high-water RSS, including imports, model and earlier tracks; it is not incremental per-track memory.',
         'Processing time includes audio loading and estimation, excluding worker startup. Initialization and inference are separate. Cached entries retain original timings and are labeled cached.',
         'The first classical inference includes lazy import/JIT costs; neural initialization includes imports/weights/hash on its first track. RSS includes neural runtime.',
         '', '## Calibration', '', 'Unmodified baselines are retained. Post-pYIN thresholds can only reject Viterbi-voiced frames, so they cannot recover misses from the conservative pYIN prior.']
    for estimator,calibration in report['calibration'].items():
        md.append(f"\n- {estimator}: selected threshold {calibration['selected_threshold']}; development IDs {calibration['development_track_ids']}; held-out IDs used in selection: none.")
    if failures:
        md+=['','## Explicit failures','']+[f"- {r['estimator']} / {r['track_id']}: {r['error']}" for r in failures]
    md+=['','## Limits','',
         'A small fixed track split is not a population-level claim. Shared singer identities, if present across track splits, limit conclusions about unseen singers.',
         'Scores have different semantics: pYIN voicing probability, YIN lag correlation and CREPE periodicity are not comparable calibrated pitch probabilities.',
         'No GUI or Wayland verification is implied by headless benchmark execution.',
         'See per-track.csv, performance.csv, aggregate.csv, results.json, calibration curves and unfilled pitch overlays for inspection.', '']
    (output/'REPORT.md').write_text('\n'.join(md))

    # One shared comparison set per split/condition. Missing algorithms are
    # labeled unavailable instead of rendering invented zero-height bars.
    for filename,metric,label in [('accuracy-comparison.png','raw_pitch_accuracy_50c','Track-macro RPA50'),
                                  ('runtime-comparison.png',None,'Mean runtime / audio duration'),
                                  ('voicing-errors.png','voicing_false_alarm_rate','Track-macro false voicing')]:
        figure=Figure(figsize=(10,4),layout='constrained');ax=figure.subplots()
        labels=[];values=[]
        for key,comparison in report['comparisons'].items():
            for estimator,s in comparison['estimators'].items():
                labels.append(f'{key}\n{estimator}')
                v=(s['track_macro'] or {}).get(metric) if metric else s['mean_runtime_over_audio_duration']
                values.append(np.nan if v is None else v)
        if metric=='voicing_false_alarm_rate':
            missed=[]
            for comparison in report['comparisons'].values():
                for s in comparison['estimators'].values():
                    recall=(s['track_macro'] or {}).get('voicing_recall')
                    missed.append(np.nan if recall is None else 1-recall)
            ax.bar(np.arange(len(labels))-0.18,values,width=0.36,color='#388dbd',label='False alarm')
            ax.bar(np.arange(len(labels))+0.18,missed,width=0.36,color='#cb7068',label='Missed voicing (1 − recall)')
            ax.legend(fontsize=8);ax.set_ylim(0,1)
        else:
            ax.bar(np.arange(len(labels)),values,color='#388dbd')
        for i,value in enumerate(values):
            if np.isnan(value):ax.text(i,0,'unavailable',rotation=90,fontsize=8)
        ax.set_xticks(np.arange(len(labels)),labels,rotation=35,ha='right',fontsize=8)
        ax.set_ylabel(label);ax.grid(axis='y',alpha=0.2)
        _save(figure,output/filename)
    if report['calibration']:
        figure=Figure(figsize=(7,5),layout='constrained');ax=figure.subplots()
        for estimator,c in report['calibration'].items():
            rows=[r for r in c['development_precision_recall'] if r['track_macro'] and r['track_macro']['voicing_precision'] is not None]
            if rows:
                ax.plot([r['track_macro']['voicing_recall'] for r in rows],[r['track_macro']['voicing_precision'] for r in rows],'.-',label=f"{estimator}: {c['confidence_type']}")
                for r in rows:ax.annotate(str(r['threshold']),(r['track_macro']['voicing_recall'],r['track_macro']['voicing_precision']),fontsize=7)
        ax.set(xlabel='Development track-macro recall',ylabel='Development track-macro precision',xlim=(0,1.02),ylim=(0,1.02));ax.legend(fontsize=8);ax.grid(alpha=0.2)
        _save(figure,output/'development-precision-recall.png')
    overlay_ids=[i for i in report['dataset']['selected']['test'] if i in tracks][:3]
    report['overlay_selection']='First three available test IDs, chosen before inspecting accuracy'
    report['overlay_track_ids']=overlay_ids
    for identifier in overlay_ids:
        track=tracks[identifier];figure=Figure(figsize=(11,5),layout='constrained');ax=figure.subplots()
        reference=np.where(track.reference_f0>0,track.reference_f0,np.nan)
        ax.plot(track.reference_times,hz_to_midi(reference),color='black',lw=1.5,label='Human F0 reference')
        for estimator in dict.fromkeys(r['estimator'] for r in report['predictions']):
            prediction=predictions.get((estimator,identifier))
            label=f"crepe ({report['settings']['crepe_model']})" if estimator=='crepe' else estimator
            if prediction is not None:ax.plot(prediction.times,hz_to_midi(prediction.f0_hz),lw=0.8,alpha=0.8,label=label)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True,nbins=12))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y,_:note_name(round(y))))
        ax.set(xlabel='Time (seconds)',ylabel='Continuous MIDI pitch',title=f'Vocadito {identifier} · baseline predictions · unvoiced gaps retained')
        ax.grid(alpha=0.2);ax.legend(fontsize=8)
        _save(figure,output/f'trajectory-{identifier}.png')
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')

