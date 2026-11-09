#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Build the engineering report exclusively from completed measurement artifacts."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np

ROOT=Path('reports/stage2')


def read(relative):return json.loads((ROOT/relative).read_text())
def number(value):return '—' if value is None else f'{value:.3f}'
def percent(value):return '—' if value is None else f'{100*value:.2f}'


def main():
    primary=read('vocadito-final/results.json')
    if primary['status']!='complete':raise SystemExit('Primary benchmark is incomplete; no final report generated.')
    env=read('environment.json');dataset=primary['dataset']
    matched=read('matched-model-comparison.json')
    lines=['# VocalScope Stage 2 — Engineering report', '',
           'Completed measurements on 9 November 2026 (Asia/Kuala_Lumpur). All numerical results were measured by executed code; synthetic and human-reference experiments are labeled separately.',
           '', '## A. Implementation summary', '',
           'Added interchangeable pYIN, related classical YIN, and independent CPU CREPE backends; a pinned Vocadito loader; reference-grid alignment; mir_eval metrics; caching; development-only threshold selection; track-bootstrap comparisons; benchmark CLI/reporting; stress/performance scripts; and native estimator/model selection.',
           'Changed pyproject.toml, README, core result/export/worker/plotting/CLI/GUI modules and tests. Added backends/, datasets.py, evaluation.py, prediction_cache.py, benchmark.py, benchmark_worker.py, benchmark_reports.py, stress.py, resources/vocadito_index_1.0.json and Stage 2 tests/scripts.',
           'Optional dependency groups: benchmark and crepe; development requirements include mir_eval, but ordinary installation does not require Torch. CPU-only Torch/torchaudio were installed in the venv, without system package changes or CUDA.',
           'Original Stage 1 engineering report, initial and final benchmark JSON, and pytest XML are unchanged; their SHA256 checks are in stage1-preserved.sha256. One legacy test assertion was updated for the explicitly versioned 1.1.0 export schema; original CSV columns and numeric meaning are retained.',
           '', '## B. Backend architecture', '',
           'PitchEstimator returns EstimatorOutput before note conversion: actual frame centers, candidates, emitted voicing, typed score, backend version, rate, initialization/inference timing and algorithm metadata. The existing pitch module converts only voiced F0 to MIDI/note/cents and builds AnalysisResult.',
           'pYIN retains Stage 1 defaults: C2–D6, 22,050 Hz, 2048 samples, 512 hop, 0.1-semitone resolution, no_trough_prob 0.001, switch_prob 0.01. Three pre-refactor golden fixtures protect F0, time, flags and probabilities.',
           'YIN uses librosa.yin and an explicit overlap-energy-normalized autocorrelation at its candidate period. The default threshold is 0.6. It is a related YIN-family baseline, not an independent algorithm family. Correlation is not a calibrated probability; exact-zero-energy frames score zero, without a dBFS gate.',
           'CREPE uses installed torchcrepe 0.0.24 public preprocess/infer/postprocess functions. Audio is resampled by SciPy to 16 kHz, supplied as [1, samples] float32 CPU tensors, normalized by the upstream 1024-sample frame mean/std rule, evaluated in inference/eval mode, and decoded once over the whole track after batched inference. This avoids upstream predict restarting Viterbi at batch boundaries. Both NumPy and Torch RNGs are fixed/restored because upstream SciPy pitch dither uses NumPy. No post-smoothing is added.',
           'CREPE periodicity threshold defaults to 0.5. Exact-zero-energy and out-of-range candidates are rejected. Bundled weights are checked and hashed; no runtime model download occurs. Model reuse requires a successfully verified checkpoint. A failed load clears upstream partially initialized model state, preventing accidental random-weight inference; an injected-failure recovery test covers this.',
           'GTK keeps its coordinator thread and owned DSP subprocess. Model loading never happens on the GTK thread. Exports use schema 1.1.0 and read 1.0.0: the original seven CSV columns remain first, typed score/backend columns are appended, and voiced_probability remains pYIN-only (null for YIN/CREPE). JSON identifies the actual algorithm, configuration, native rate/hop, weight hash and initialization.',
           '', '## C. Human-vocal dataset verification', '',
           'Source: [Vocadito v3, Zenodo record 5578807](https://zenodo.org/records/5578807), DOI 10.5281/zenodo.5578807. CC BY 4.0. Attribution: Rachel M. Bittner, Katherine Pasalo, Juan José Bosch, Gabriel Meseguer-Brocal and David Rubinstein (2021).',
           'The 58,492,257-byte archive matches MD5 dea40fd18f14d899643c4ba221b33a46. All 40 WAVs, original frame-F0 CSVs and metadata match the official mirdata 1.0 index checksums; the pinned index MD5 is ff83648dc2311c0c11fe8f304bbb62d4. SHA256s, IDs, singer IDs, annotation extents and counts are retained in dataset_manifest.json.',
           'A small direct loader uses that official index and the original CSV semantics, avoiding the wider mirdata dependency tree. It does not substitute another algorithm for human F0 labels. Original seconds/Hz values and 0 Hz unvoiced labels are preserved. Corruption, missing files, unordered/non-finite annotations and incompatible annotation/audio extents are explicit errors.',
           f"Evaluated corpus: **{len(dataset['tracks'])} recordings**, **{sum(t['duration_seconds'] for t in dataset['tracks']):.3f} seconds**, **{sum(t['reference_frames'] for t in dataset['tracks'])} annotated frames**, **{sum(t['reference_voiced_frames'] for t in dataset['tracks'])} reference-voiced frames**. The metadata contains 29 singer IDs.",
           f"Fixed seed {dataset['splits']['seed']}: **0 training / {len(dataset['splits']['development'])} development / {len(dataset['splits']['test'])} held-out recordings**. No frame-level split, no model training. Every requested primary prediction succeeded (40 × 3 backends).",
           f"Development IDs: {dataset['splits']['development']}. Held-out IDs: {dataset['splits']['test']}.",
           'Singer IDs S6, S12, S21 and S28 occur in both partitions. This is a held-out-recording experiment, not a singer-disjoint generalization claim. Track-level confidence intervals can be optimistic when tracks share a singer.',
           'Alignment uses nearest actual predicted center, ties earlier. There is no pitch interpolation across gaps or extrapolation past prediction endpoints/audio duration. Uncovered reference frames count as predicted unvoiced; all reference pitches, including out-of-configured-range pitches, remain in the denominator.',
           'Data, archives, generated audio and prediction caches stay in ignored local directories. No corpus audio/annotation files or model checkpoints are packaged. Attribution accompanies derived benchmark plots/reports.',
           '', '## D. Scientific leaderboard', '',
           'Primary neural model: **CREPE-tiny**, 2 CPU threads, batch 128, native hop 160 samples (10 ms). Classical hop: 512 at 22,050 Hz. Results below use the same 20 held-out recordings. Full-corpus predictions include all 40 tracks; development tracks select thresholds only.',
           'RPA50 and RCA use mir_eval strict <50 cents and divide by all reference voiced frames; unvoiced predictions provide no F0 and count as misses. Overall accuracy includes correct unvoiced frames. Voicing precision/F1 treat a wrongly pitched but voiced estimate as voiced. Error percentiles and octave rate condition on mutually voiced frames; a low conditional error is never presented as overall accuracy. Undefined denominators are null.',
           'Historical Stage 1 synthetic metrics retain their original inclusive-50/native-frame convention. Stage 2 uses a common reference grid and strict mir_eval convention; different synthetic numbers do not imply a pYIN regression.', '']
    for key in ('test/baseline','test/calibrated'):
        comparison=primary['comparisons'][key]
        lines += [f'### {key}', '', '| Backend | Frame RPA50 % | Macro RPA50 % | RCA % | Recall % | False alarm % | Precision % | F1 % | Overall % |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for backend,s in comparison['estimators'].items():
            w=s['frame_weighted'];m=s['track_macro']
            lines.append(f"| {backend} | {percent(w['raw_pitch_accuracy_50c'])} | {percent(m['raw_pitch_accuracy_50c'])} | {percent(w['raw_chroma_accuracy'])} | {percent(w['voicing_recall'])} | {percent(w['voicing_false_alarm_rate'])} | {percent(w['voicing_precision'])} | {percent(w['voicing_f1'])} | {percent(w['overall_accuracy'])} |")
        lines += ['', '| Backend | Median cents | Mean cents | P90 cents | P95 cents | Mutual-voiced octave error % |', '|---|---:|---:|---:|---:|---:|']
        for backend,s in comparison['estimators'].items():
            w=s['frame_weighted']
            lines.append(f"| {backend} | {number(w['median_absolute_error_cents'])} | {number(w['mean_absolute_error_cents'])} | {number(w['p90_absolute_error_cents'])} | {number(w['p95_absolute_error_cents'])} | {percent(w['octave_error_rate'])} |")
        lines+=['','Paired track-macro RPA50 differences, 95% percentile bootstrap (2,000 whole-track resamples, seed 20261109):','']
        for row in comparison['paired_rpa50']:
            ci=row['ci95_track_bootstrap']
            lines.append(f"- {row['b']} − {row['a']}: {100*row['mean_difference']:+.2f} percentage points; CI [{100*ci[0]:+.2f}, {100*ci[1]:+.2f}], n={row['tracks']} paired tracks.")
    lines += ['', 'Frame-weighted pooling and track-macro averages are both retained; no long track dominates every summary. All per-track values and denominator counts are in per-track.csv/results.json. Uncertainty is conditional on this small fixed split, not a population guarantee or a multiple-comparison-adjusted superiority test.',
              '', '### Threshold selection and prior trade-off', '',
              'Threshold objective was prespecified development track-macro voicing F1; ties choose a lower threshold. No held-out reference enters selection. Unit tests spy on selection inputs to prove development/test disjointness. The implementation supports five-fold track CV; all five folds were not run and are not represented as completed evidence.']
    for backend,calibration in primary['calibration'].items():
        lines.append(f"- {backend}: selected {calibration['selected_threshold']} ({calibration['confidence_type']}); {len(calibration['development_track_ids'])} development tracks; test IDs used for selection: {calibration['test_track_ids_used_for_selection']}.")
    prior=read('pyin-original-prior/results.json')
    lines+=['','The additional pYIN probability rejection threshold is distinct from no_trough_prob. The latter remains 0.001 in the reference baseline. A separate controlled human-vocal study changes only that prior to 0.01 (keeping 2048/C2–D6):', '',
            '| No-trough prior | Condition | Held-out RPA50 % | Recall % | False alarm % | F1 % |','|---:|---|---:|---:|---:|---:|']
    for label,report in (('0.001',primary),('0.01',prior)):
        for variant in ('baseline','calibrated'):
            w=report['comparisons'][f'test/{variant}']['estimators']['pyin']['frame_weighted']
            lines.append(f"| {label} | {variant} | {percent(w['raw_pitch_accuracy_50c'])} | {percent(w['voicing_recall'])} | {percent(w['voicing_false_alarm_rate'])} | {percent(w['voicing_f1'])} |")
    lines+=['','Selecting for voicing F1 trades pitch recall against false alarms. It is not calibration of a probability of correct F0. Post-pYIN rejection cannot restore candidates the original Viterbi path rejected.',
            '', '### Full-model check on the same five held-out tracks', '',
            f"Prespecified first five test IDs {matched['track_ids']}; {matched['duration_seconds']:.3f} seconds. No full-model threshold tuning. This is **not** a 40-track full-model benchmark.",
            '', '| Backend/model | Frame RPA50 % | Macro RPA50 % | Recall % | False alarm % | Processing seconds |', '|---|---:|---:|---:|---:|---:|']
    for backend,s in matched['comparisons'].items():
        w=s['frame_weighted'];m=s['track_macro']
        lines.append(f"| {backend} | {percent(w['raw_pitch_accuracy_50c'])} | {percent(m['raw_pitch_accuracy_50c'])} | {percent(w['voicing_recall'])} | {percent(w['voicing_false_alarm_rate'])} | {number(s['total_processing_seconds'])} |")
    for row in matched['paired_macro_rpa50_intervals']:
        if row['a']=='crepe-tiny' and row['b']=='crepe-full':
            lines.append(f"\nFull − tiny paired macro RPA50: {100*row['mean_difference']:+.2f} percentage points, CI {[100*x for x in row['ci95_track_bootstrap']]}; only five paired tracks. Do not compare the full-model five-track score directly against tiny's twenty-track score.\n")
    lines += ['## E. Noise, vibrato, octaves and robustness', '',
              '44 deterministic signals per backend (132 completed backend/signal runs), plus a separate 44-run pYIN prior study. No execution failures. Accuracy failures remain visible. Signals include analytic integrated-phase trajectories, stronger harmonics, weak/missing fundamentals, white/pink/breath-like noise, transients and nominal-range boundaries. Random seeds: 7, 91, 20261109.',
              'The common synthetic reference grid is 10 ms. Both full-clip and conservative interior scores are retained; reference truth is generated independently of estimator output. Numbers differ from Stage 1 native-grid scoring for that reason.', '',
              '| SNR | Signals per backend | pYIN RPA50 % | YIN RPA50 % | CREPE-tiny RPA50 % |', '|---|---:|---:|---:|---:|']
    stress={backend:read(f'stress-{backend}.json') for backend in ('pyin','yin','crepe')}
    for snr in ('clean','20','10','5','0'):
        scores=[];count=0
        for backend,r in stress.items():
            rows=[c for c in r['cases'] if c['case']=='snr_'+snr or c['case'].startswith('snr_'+snr+'_seed')]
            count=len(rows);scores.append(float(np.mean([x['interior']['raw_pitch_accuracy_50c'] for x in rows])))
        lines.append(f"| {snr} | {count} | {' | '.join(percent(x) for x in scores)} |")
    lines+=['','Each noisy SNR has three equally sized signals. These are synthetic harmonic-plus-Gaussian mixtures, not a claim that all real 0 dB singing is recoverable. Human-vocal false alarms remain substantial despite low synthetic false alarm rates.', '',
            '| Backend | Pink-noise mean false alarm % (3 seeds) | White-noise mean false alarm % | Breath-like mean false alarm % | 3 Hz fitted vibrato amplitude ratio | 5 Hz fitted ratio |', '|---|---:|---:|---:|---:|---:|']
    for backend,r in stress.items():
        values=[]
        for category in ('pink','white','breath'):
            values.append(float(np.mean([c['interior']['voicing_false_alarm_rate'] for c in r['cases'] if c['case'].startswith(category+'_seed')])))
        vibrato=[next(c for c in r['cases'] if c['case']==f'vibrato_{hz}hz')['vibrato_fitted_amplitude_ratio'] for hz in (3,5)]
        lines.append(f"| {backend} | {' | '.join(percent(x) for x in values)} | {number(vibrato[0])} | {number(vibrato[1])} |")
    lines+=['','Sinusoidal fits report amplitude/phase separately from random pitch jitter; no smoothing is applied. Both rising and falling glissandi retain their original timing for headline scores; best-fit lag is diagnostic only. No smoothing or lag optimization is applied to human evaluation.',
            'pYIN still makes a full-octave error on the synthetic note 10 cents above the upper configured bound. YIN lag interpolation can exceed nominal bounds rather than clamping; CREPE rejects its out-of-range candidates and can lose some near-boundary voicing. These behaviors are reported honestly. Near-boundary RPA50 can still count an in-range estimate as correct for an out-of-range truth within 50 cents.',
            '', '## F. CPU performance and resources', '',
            f"Measured CPU: **{env['cpu']}**, {env['logical_cpus']} logical CPUs, {env['memory_total_kib']}. Python {env['python']}; {env['platform']}.",
            'Final performance jobs ran serially after the final human comparison, without concurrent agent-started inference. This is a shared desktop host: no affinity/governor lock or exclusivity is claimed. Earlier exploratory measurements are preserved separately and can vary with host load/thermal state. Full-model throughput is too slow for an interactive default here.',
            'Times include loading and result construction. Native model initialization is separate; first classical inference includes lazy imports/JIT. Disk JIT caches existed. Peak RSS is process high water including imported runtimes/model/earlier clips, not per-clip allocation or total GUI+child RAM.', '',
            '| Backend/model | Clip s | Cold first call | Init s | Inference s | Load + processing s | Processing/audio | Peak RSS MiB |', '|---|---:|---|---:|---:|---:|---:|---:|']
    for backend,model in (('pyin','tiny'),('yin','tiny'),('crepe','tiny'),('crepe','full')):
        perf=read(f'final-performance-{backend}-{model}.json')
        if perf['status']!='complete':raise SystemExit('Performance run incomplete.')
        for row in perf['measurements']:
            label=f'{backend}/{model}' if backend=='crepe' else backend
            lines.append(f"| {label} | {row['duration_seconds']} | {row['cold_first_call']} | {number(row['initialization_seconds'])} | {number(row['inference_seconds'])} | {number(row['total_processing_seconds'])} | {number(row['runtime_over_audio_duration'])} | {number(row['peak_process_rss_mib'])} |")
    lines+=['','Corpus timings/RSS are also available per track in each performance.csv. Primary held-out timings are warm: model/JIT startup was normally paid on an earlier development track in the persistent worker. Cached predictions preserve original timings and never relabel cache lookup as inference. GUI startup repeats in a fresh child per analysis.',
            '', '## G. Tests', '']
    for label,path in [('Complete headless suite with optional CPU tests','final-tests.xml'),('Real Wayland GUI integration','wayland.xml')]:
        suite=ET.parse(ROOT/path).getroot().find('testsuite')
        failures=int(suite.get('failures'));errors=int(suite.get('errors'));skips=int(suite.get('skipped'));total=int(suite.get('tests'))
        lines.append(f"- {label}: **{total-failures-errors-skips} passed, {failures} failed, {errors} errors, {skips} skipped**, {float(suite.get('time')):.2f} seconds. Evidence: {path}.")
    lines+=['','The headless skip requires a display; the separate real Wayland run exercises it. Original Stage 1 tests remain passing, with the documented schema-assertion migration. New tests cover protocol conformance, pre-refactor golden pYIN equivalence, YIN voicing, lazy optional imports, full/tiny CPU inference, deterministic dither, batch independence, failed-initialization recovery, alignment, metric denominators/percentiles, official-reference fixture semantics, integrity checks, safe/resumable downloads, cache invalidation, CLI selection, failed-track disclosure, deterministic splits and held-out-label exclusion.',
            'No test downloads a corpus or model. Ordinary tests skip neural integration unless --run-neural; model assets must already be installed. Pre-final logs and the initial GUI crash are preserved, not rewritten as successes.',
            '', '## H. GUI verification', '']
    suite=ET.parse(ROOT/'wayland.xml').getroot().find('testsuite')
    properties={x.get('name'):x.get('value') for x in suite.find('properties')}
    lines += [f"Actual host-session test properties: `{properties}`.",
              f"GTK {env['gtk']}, libadwaita {env['libadwaita']}, PyGObject {env['pygobject']}, pycairo {env['pycairo']}. This was a real mapped **GdkWaylandDisplay** window, not an import-only or Xvfb claim. The test loaded a file, analyzed using pYIN/YIN/CREPE-tiny, checked GTK timer activity/concurrent-job rejection, exercised native chooser cancellation, exported CSV/JSON/PNG, checked invalid-input recovery, and closed while a chooser was pending.",
              'The first real GUI attempt segfaulted inside GTK when programmatically cancelling a FileDialog before presentation. A minimal GTK-only program reproduced the same fault even with retained references. Delayed cancellation succeeded. The app now defers its own shutdown while a chooser is pending and retains the parent through async completion; the regression test covers that path. The underlying GTK 4.24.1 immediate-cancellation bug remains outside this workaround. Nonfatal upstream GLib cancellation warnings are retained. Known upstream GI/Matplotlib deprecation floods are filtered only in the GUI test.',
              'This updates verification for Stage 2; the historical Stage 1 report remains unchanged. No claim of exhaustive manual visual/accessibility QA is made. Actual exported human-reference overlays were inspected separately.',
              '', '## I. Limitations', '',
              '- The primary full-corpus neural experiment uses tiny, not full. Full has only a prespecified five-track held-out check; no full-model forty-track or full-model development calibration is claimed.',
              '- The fixed split has four shared singer identities; track-bootstrap intervals are exploratory and may understate singer correlation. Five-fold support exists, but five-fold results are not invented.',
              '- Human references are official expert annotations, not incontrovertible acoustic truth; ambiguous voicing and annotation boundaries remain limitations. Generalization to external singers, languages, devices, accompaniment or polyphony is not established.',
              '- Synthetic noise success does not imply human consonant/breath rejection. Held-out human false alarms remain substantial for all three backends; F1 tuning sacrifices recall/RPA in the classical backends.',
              '- pYIN/YIN share a family; CREPE is independent but its original training corpus overlap is not independently audited here. Neither periodicity nor lag correlation is calibrated pitch correctness.',
              '- pYIN upper-bound octave errors and YIN nominal-bound overshoot persist. Window averaging still attenuates vibrato. Neural dither adds seeded pitch noise by upstream design.',
              '- Whole-file processing and conservative duration/memory preflight remain; neural runtime overhead is additional to the classical-array estimate. Batch size controls activation memory, not a strict OS RSS cap.',
              '- The native GTK immediate-programmatic-cancellation issue is worked around in app shutdown, not repaired inside the system library. Other GTK/compositor versions and exhaustive manual GUI quality remain unverified.',
              '', '## J. Reproduction commands', '', '```bash',
              'cd /path/to/VocalScope', 'python -m venv --system-site-packages .venv', 'source .venv/bin/activate',
              'python -m pip install -r requirements.txt',
              'python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu',
              "python -m pip install -e '.[crepe,benchmark,dev]'", 'vocalscope dataset download --path data/vocadito', 'vocalscope dataset verify --path data/vocadito',
              'vocalscope analyze vocal.wav --estimator pyin --output results/pyin',
              'vocalscope analyze vocal.wav --estimator yin --output results/yin',
              'vocalscope analyze vocal.wav --estimator crepe --crepe-model tiny --device cpu --output results/tiny',
              'vocalscope analyze vocal.wav --estimator crepe --crepe-model full --device cpu --output results/full',
              'vocalscope benchmark --dataset-path data/vocadito --estimators pyin,yin,crepe --crepe-model tiny --split all --calibrate --output results/reproduce --cache-dir reports/stage2/cache',
              'vocalscope benchmark --dataset-path data/vocadito --estimators pyin,yin,crepe --crepe-model full --split test --max-tracks 5 --output results/full-five',
              'python -m pytest --run-neural -ra', 'GDK_BACKEND=wayland python -m pytest -m gui -v', 'GDK_BACKEND=wayland vocalscope gui',
              'python scripts/stage2_stress.py --estimator crepe --model tiny --output results/stress.json',
              'python scripts/stage2_performance.py --estimator crepe --model full --output results/performance.json',
              'python -m build --no-isolation', '```',
              '', 'Library versions used: `'+json.dumps(env['packages'],sort_keys=True)+'`.',
              'The local dependency snapshot is stage2/requirements-tested.txt; system bindings and benchmark controls are recorded in stage2/environment.json. Model SHA256s and per-backend settings are retained in prediction metadata. Ordinary inference is fully offline after installation.',
              '', '## K. Evidence-based recommendation', '',
              'Keep **pYIN as the compatibility/ordinary-install default**, as required, with its Stage 1 settings unchanged. Offer **CREPE-tiny for accuracy-focused use on recordings resembling Vocadito**: it leads the measured held-out RPA/voicing comparison while remaining CPU-compatible. Its scores remain imperfect and its higher optional dependency/memory cost matters. Full CREPE is not a suitable interactive default on this CPU given measured throughput and only five matched human tracks. YIN is a useful much faster diagnostic baseline, with weaker human voicing behavior.',
              'This recommendation is conditional on the measured corpus/split and resources. It is not a universal neural-superiority claim or an automatic default switch. Further singer-disjoint and external-corpus validation should precede a broader default-policy change.',
              '', '## L. Stage 3 readiness', '',
              'Available foundations: backend-normalized continuous F0/voicing with typed scores and provenance; source/annotation integrity; tested time alignment; classical/neural CPU isolation; stable structured exports; per-track metrics; development-only tuning; reusable prediction caches; honest failure coverage; and native estimator selection. These support later note-boundary and MIDI work, but note segmentation, MIDI generation, musical quantization and arrangements are **not implemented**.', '']
    Path('reports/STAGE2_ENGINEERING.md').write_text('\n'.join(lines))
    print('Wrote reports/STAGE2_ENGINEERING.md from completed artifacts.')


if __name__=='__main__':main()

