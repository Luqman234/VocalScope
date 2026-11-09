> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 2 — Engineering report

Completed measurements on 9 November 2026 (Asia/Kuala_Lumpur). All numerical results were measured by executed code; synthetic and human-reference experiments are labeled separately.

## A. Implementation summary

Added interchangeable pYIN, related classical YIN, and independent CPU CREPE backends; a pinned Vocadito loader; reference-grid alignment; mir_eval metrics; caching; development-only threshold selection; track-bootstrap comparisons; benchmark CLI/reporting; stress/performance scripts; and native estimator/model selection.
Changed pyproject.toml, README, core result/export/worker/plotting/CLI/GUI modules and tests. Added backends/, datasets.py, evaluation.py, prediction_cache.py, benchmark.py, benchmark_worker.py, benchmark_reports.py, stress.py, resources/vocadito_index_1.0.json and Stage 2 tests/scripts.
Optional dependency groups: benchmark and crepe; development requirements include mir_eval, but ordinary installation does not require Torch. CPU-only Torch/torchaudio were installed in the venv, without system package changes or CUDA.
Original Stage 1 engineering report, initial and final benchmark JSON, and pytest XML are unchanged; their SHA256 checks are in stage1-preserved.sha256. One legacy test assertion was updated for the explicitly versioned 1.1.0 export schema; original CSV columns and numeric meaning are retained.

## B. Backend architecture

PitchEstimator returns EstimatorOutput before note conversion: actual frame centers, candidates, emitted voicing, typed score, backend version, rate, initialization/inference timing and algorithm metadata. The existing pitch module converts only voiced F0 to MIDI/note/cents and builds AnalysisResult.
pYIN retains Stage 1 defaults: C2–D6, 22,050 Hz, 2048 samples, 512 hop, 0.1-semitone resolution, no_trough_prob 0.001, switch_prob 0.01. Three pre-refactor golden fixtures protect F0, time, flags and probabilities.
YIN uses librosa.yin and an explicit overlap-energy-normalized autocorrelation at its candidate period. The default threshold is 0.6. It is a related YIN-family baseline, not an independent algorithm family. Correlation is not a calibrated probability; exact-zero-energy frames score zero, without a dBFS gate.
CREPE uses installed torchcrepe 0.0.24 public preprocess/infer/postprocess functions. Audio is resampled by SciPy to 16 kHz, supplied as [1, samples] float32 CPU tensors, normalized by the upstream 1024-sample frame mean/std rule, evaluated in inference/eval mode, and decoded once over the whole track after batched inference. This avoids upstream predict restarting Viterbi at batch boundaries. Both NumPy and Torch RNGs are fixed/restored because upstream SciPy pitch dither uses NumPy. No post-smoothing is added.
CREPE periodicity threshold defaults to 0.5. Exact-zero-energy and out-of-range candidates are rejected. Bundled weights are checked and hashed; no runtime model download occurs. Model reuse requires a successfully verified checkpoint. A failed load clears upstream partially initialized model state, preventing accidental random-weight inference; an injected-failure recovery test covers this.
GTK keeps its coordinator thread and owned DSP subprocess. Model loading never happens on the GTK thread. Exports use schema 1.1.0 and read 1.0.0: the original seven CSV columns remain first, typed score/backend columns are appended, and voiced_probability remains pYIN-only (null for YIN/CREPE). JSON identifies the actual algorithm, configuration, native rate/hop, weight hash and initialization.

## C. Human-vocal dataset verification

Source: [Vocadito v3, Zenodo record 5578807](https://zenodo.org/records/5578807), DOI 10.5281/zenodo.5578807. CC BY 4.0. Attribution: Rachel M. Bittner, Katherine Pasalo, Juan José Bosch, Gabriel Meseguer-Brocal and David Rubinstein (2021).
The 58,492,257-byte archive matches MD5 dea40fd18f14d899643c4ba221b33a46. All 40 WAVs, original frame-F0 CSVs and metadata match the official mirdata 1.0 index checksums; the pinned index MD5 is ff83648dc2311c0c11fe8f304bbb62d4. SHA256s, IDs, singer IDs, annotation extents and counts are retained in dataset_manifest.json.
A small direct loader uses that official index and the original CSV semantics, avoiding the wider mirdata dependency tree. It does not substitute another algorithm for human F0 labels. Original seconds/Hz values and 0 Hz unvoiced labels are preserved. Corruption, missing files, unordered/non-finite annotations and incompatible annotation/audio extents are explicit errors.
Evaluated corpus: **40 recordings**, **817.129 seconds**, **140782 annotated frames**, **92966 reference-voiced frames**. The metadata contains 29 singer IDs.
Fixed seed 20261109: **0 training / 20 development / 20 held-out recordings**. No frame-level split, no model training. Every requested primary prediction succeeded (40 × 3 backends).
Development IDs: ['1', '11', '12', '17', '18', '19', '20', '21', '24', '26', '27', '3', '30', '33', '34', '35', '40', '6', '8', '9']. Held-out IDs: ['10', '13', '14', '15', '16', '2', '22', '23', '25', '28', '29', '31', '32', '36', '37', '38', '39', '4', '5', '7'].
Singer IDs S6, S12, S21 and S28 occur in both partitions. This is a held-out-recording experiment, not a singer-disjoint generalization claim. Track-level confidence intervals can be optimistic when tracks share a singer.
Alignment uses nearest actual predicted center, ties earlier. There is no pitch interpolation across gaps or extrapolation past prediction endpoints/audio duration. Uncovered reference frames count as predicted unvoiced; all reference pitches, including out-of-configured-range pitches, remain in the denominator.
Data, archives, generated audio and prediction caches stay in ignored local directories. No corpus audio/annotation files or model checkpoints are packaged. Attribution accompanies derived benchmark plots/reports.

## D. Scientific leaderboard

Primary neural model: **CREPE-tiny**, 2 CPU threads, batch 128, native hop 160 samples (10 ms). Classical hop: 512 at 22,050 Hz. Results below use the same 20 held-out recordings. Full-corpus predictions include all 40 tracks; development tracks select thresholds only.
RPA50 and RCA use mir_eval strict <50 cents and divide by all reference voiced frames; unvoiced predictions provide no F0 and count as misses. Overall accuracy includes correct unvoiced frames. Voicing precision/F1 treat a wrongly pitched but voiced estimate as voiced. Error percentiles and octave rate condition on mutually voiced frames; a low conditional error is never presented as overall accuracy. Undefined denominators are null.
Historical Stage 1 synthetic metrics retain their original inclusive-50/native-frame convention. Stage 2 uses a common reference grid and strict mir_eval convention; different synthetic numbers do not imply a pYIN regression.

### test/baseline

| Backend | Frame RPA50 % | Macro RPA50 % | RCA % | Recall % | False alarm % | Precision % | F1 % | Overall % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pyin | 93.63 | 92.88 | 93.63 | 98.81 | 31.24 | 86.60 | 92.31 | 85.46 |
| yin | 93.11 | 92.56 | 93.75 | 98.66 | 35.67 | 84.97 | 91.31 | 83.65 |
| crepe | 95.67 | 95.58 | 95.90 | 96.81 | 21.18 | 90.33 | 93.46 | 90.13 |

| Backend | Median cents | Mean cents | P90 cents | P95 cents | Mutual-voiced octave error % |
|---|---:|---:|---:|---:|---:|
| pyin | 7.864 | 14.511 | 34.078 | 51.120 | 0.00 |
| yin | 7.437 | 23.825 | 34.658 | 53.745 | 0.65 |
| crepe | 9.414 | 14.691 | 24.207 | 30.191 | 0.24 |

Paired track-macro RPA50 differences, 95% percentile bootstrap (2,000 whole-track resamples, seed 20261109):

- yin − pyin: -0.32 percentage points; CI [-0.82, +0.11], n=20 paired tracks.
- crepe − pyin: +2.70 percentage points; CI [+0.55, +4.43], n=20 paired tracks.
- crepe − yin: +3.02 percentage points; CI [+1.21, +4.54], n=20 paired tracks.
### test/calibrated

| Backend | Frame RPA50 % | Macro RPA50 % | RCA % | Recall % | False alarm % | Precision % | F1 % | Overall % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pyin | 92.43 | 91.49 | 92.43 | 96.78 | 24.20 | 89.10 | 92.78 | 86.96 |
| yin | 92.24 | 91.56 | 92.83 | 97.26 | 29.49 | 87.08 | 91.89 | 85.10 |
| crepe | 95.67 | 95.58 | 95.90 | 96.81 | 21.18 | 90.33 | 93.46 | 90.13 |

| Backend | Median cents | Mean cents | P90 cents | P95 cents | Mutual-voiced octave error % |
|---|---:|---:|---:|---:|---:|
| pyin | 7.707 | 13.619 | 31.982 | 47.318 | 0.00 |
| yin | 7.329 | 21.473 | 33.309 | 50.952 | 0.61 |
| crepe | 9.414 | 14.691 | 24.207 | 30.191 | 0.24 |

Paired track-macro RPA50 differences, 95% percentile bootstrap (2,000 whole-track resamples, seed 20261109):

- yin − pyin: +0.06 percentage points; CI [-0.47, +0.49], n=20 paired tracks.
- crepe − pyin: +4.09 percentage points; CI [+1.86, +6.05], n=20 paired tracks.
- crepe − yin: +4.02 percentage points; CI [+2.08, +5.77], n=20 paired tracks.

Frame-weighted pooling and track-macro averages are both retained; no long track dominates every summary. All per-track values and denominator counts are in per-track.csv/results.json. Uncertainty is conditional on this small fixed split, not a population guarantee or a multiple-comparison-adjusted superiority test.

### Threshold selection and prior trade-off

Threshold objective was prespecified development track-macro voicing F1; ties choose a lower threshold. No held-out reference enters selection. Unit tests spy on selection inputs to prove development/test disjointness. The implementation supports five-fold track CV; all five folds were not run and are not represented as completed evidence.
- pyin: selected 0.01 (pyin_voicing_probability); 20 development tracks; test IDs used for selection: [].
- yin: selected 0.7 (normalized_autocorrelation); 20 development tracks; test IDs used for selection: [].
- crepe: selected 0.5 (crepe_periodicity); 20 development tracks; test IDs used for selection: [].

The additional pYIN probability rejection threshold is distinct from no_trough_prob. The latter remains 0.001 in the reference baseline. A separate controlled human-vocal study changes only that prior to 0.01 (keeping 2048/C2–D6):

| No-trough prior | Condition | Held-out RPA50 % | Recall % | False alarm % | F1 % |
|---:|---|---:|---:|---:|---:|
| 0.001 | baseline | 93.63 | 98.81 | 31.24 | 92.31 |
| 0.001 | calibrated | 92.43 | 96.78 | 24.20 | 92.78 |
| 0.01 | baseline | 94.20 | 99.71 | 50.03 | 88.95 |
| 0.01 | calibrated | 89.17 | 92.46 | 16.84 | 92.14 |

Selecting for voicing F1 trades pitch recall against false alarms. It is not calibration of a probability of correct F0. Post-pYIN rejection cannot restore candidates the original Viterbi path rejected.

### Full-model check on the same five held-out tracks

Prespecified first five test IDs ['10', '13', '14', '15', '16']; 81.213 seconds. No full-model threshold tuning. This is **not** a 40-track full-model benchmark.

| Backend/model | Frame RPA50 % | Macro RPA50 % | Recall % | False alarm % | Processing seconds |
|---|---:|---:|---:|---:|---:|
| pyin | 89.57 | 89.75 | 97.73 | 36.04 | 19.904 |
| yin | 89.40 | 89.51 | 97.39 | 40.48 | 3.054 |
| crepe-tiny | 95.11 | 95.13 | 96.09 | 21.53 | 16.156 |
| crepe-full | 97.41 | 97.29 | 98.42 | 24.28 | 590.361 |

Full − tiny paired macro RPA50: +2.16 percentage points, CI [1.0783020449269398, 3.423306325005719]; only five paired tracks. Do not compare the full-model five-track score directly against tiny's twenty-track score.

## E. Noise, vibrato, octaves and robustness

44 deterministic signals per backend (132 completed backend/signal runs), plus a separate 44-run pYIN prior study. No execution failures. Accuracy failures remain visible. Signals include analytic integrated-phase trajectories, stronger harmonics, weak/missing fundamentals, white/pink/breath-like noise, transients and nominal-range boundaries. Random seeds: 7, 91, 20261109.
The common synthetic reference grid is 10 ms. Both full-clip and conservative interior scores are retained; reference truth is generated independently of estimator output. Numbers differ from Stage 1 native-grid scoring for that reason.

| SNR | Signals per backend | pYIN RPA50 % | YIN RPA50 % | CREPE-tiny RPA50 % |
|---|---:|---:|---:|---:|
| clean | 1 | 100.00 | 100.00 | 100.00 |
| 20 | 3 | 100.00 | 100.00 | 100.00 |
| 10 | 3 | 100.00 | 100.00 | 100.00 |
| 5 | 3 | 100.00 | 98.23 | 100.00 |
| 0 | 3 | 0.00 | 0.00 | 100.00 |

Each noisy SNR has three equally sized signals. These are synthetic harmonic-plus-Gaussian mixtures, not a claim that all real 0 dB singing is recoverable. Human-vocal false alarms remain substantial despite low synthetic false alarm rates.

| Backend | Pink-noise mean false alarm % (3 seeds) | White-noise mean false alarm % | Breath-like mean false alarm % | 3 Hz fitted vibrato amplitude ratio | 5 Hz fitted ratio |
|---|---:|---:|---:|---:|---:|
| pyin | 0.00 | 0.00 | 0.00 | 0.854 | 0.696 |
| yin | 2.21 | 0.00 | 0.00 | 0.876 | 0.682 |
| crepe | 0.00 | 0.00 | 0.00 | 0.874 | 0.881 |

Sinusoidal fits report amplitude/phase separately from random pitch jitter; no smoothing is applied. Both rising and falling glissandi retain their original timing for headline scores; best-fit lag is diagnostic only. No smoothing or lag optimization is applied to human evaluation.
pYIN still makes a full-octave error on the synthetic note 10 cents above the upper configured bound. YIN lag interpolation can exceed nominal bounds rather than clamping; CREPE rejects its out-of-range candidates and can lose some near-boundary voicing. These behaviors are reported honestly. Near-boundary RPA50 can still count an in-range estimate as correct for an out-of-range truth within 50 cents.

## F. CPU performance and resources

Measured CPU: **12th Gen Intel(R) Core(TM) i5-1235U**, 12 logical CPUs, MemTotal:       15991080 kB. Python 3.14.9; Linux-7.2.14-zen1-1-zen-x86_64-with-glibc2.44.
Final performance jobs ran serially after the final human comparison, without concurrent agent-started inference. This is a shared desktop host: no affinity/governor lock or exclusivity is claimed. Earlier exploratory measurements are preserved separately and can vary with host load/thermal state. Full-model throughput is too slow for an interactive default here.
Times include loading and result construction. Native model initialization is separate; first classical inference includes lazy imports/JIT. Disk JIT caches existed. Peak RSS is process high water including imported runtimes/model/earlier clips, not per-clip allocation or total GUI+child RAM.

| Backend/model | Clip s | Cold first call | Init s | Inference s | Load + processing s | Processing/audio | Peak RSS MiB |
|---|---:|---|---:|---:|---:|---:|---:|
| pyin | 1 | True | 0.000 | 1.147 | 1.159 | 1.159 | 257.559 |
| pyin | 1 | False | 0.000 | 0.209 | 0.214 | 0.214 | 266.156 |
| pyin | 5 | False | 0.000 | 0.888 | 0.896 | 0.179 | 273.906 |
| pyin | 15 | False | 0.000 | 2.622 | 2.635 | 0.176 | 304.223 |
| yin | 1 | True | 0.000 | 0.922 | 0.931 | 0.931 | 234.168 |
| yin | 1 | False | 0.000 | 0.009 | 0.016 | 0.016 | 235.227 |
| yin | 5 | False | 0.000 | 0.030 | 0.036 | 0.007 | 250.992 |
| yin | 15 | False | 0.000 | 0.091 | 0.104 | 0.007 | 290.746 |
| crepe/tiny | 1 | True | 2.566 | 0.895 | 3.467 | 3.467 | 523.031 |
| crepe/tiny | 1 | False | 0.000 | 0.325 | 0.336 | 0.336 | 572.629 |
| crepe/tiny | 5 | False | 0.000 | 1.812 | 1.819 | 0.364 | 600.359 |
| crepe/tiny | 15 | False | 0.000 | 4.790 | 4.805 | 0.320 | 600.359 |
| crepe/full | 1 | True | 2.833 | 7.383 | 10.223 | 10.223 | 792.926 |
| crepe/full | 1 | False | 0.000 | 6.940 | 6.950 | 6.950 | 858.887 |
| crepe/full | 5 | False | 0.000 | 33.834 | 33.845 | 6.769 | 943.023 |
| crepe/full | 15 | False | 0.000 | 99.231 | 99.246 | 6.616 | 971.395 |

Corpus timings/RSS are also available per track in each performance.csv. Primary held-out timings are warm: model/JIT startup was normally paid on an earlier development track in the persistent worker. Cached predictions preserve original timings and never relabel cache lookup as inference. GUI startup repeats in a fresh child per analysis.

## G. Tests

- Complete headless suite with optional CPU tests: **109 passed, 0 failed, 0 errors, 1 skipped**, 44.55 seconds. Evidence: final-tests.xml.
- Real Wayland GUI integration: **1 passed, 0 failed, 0 errors, 0 skipped**, 17.33 seconds. Evidence: wayland.xml.

The headless skip requires a display; the separate real Wayland run exercises it. Original Stage 1 tests remain passing, with the documented schema-assertion migration. New tests cover protocol conformance, pre-refactor golden pYIN equivalence, YIN voicing, lazy optional imports, full/tiny CPU inference, deterministic dither, batch independence, failed-initialization recovery, alignment, metric denominators/percentiles, official-reference fixture semantics, integrity checks, safe/resumable downloads, cache invalidation, CLI selection, failed-track disclosure, deterministic splits and held-out-label exclusion.
No test downloads a corpus or model. Ordinary tests skip neural integration unless --run-neural; model assets must already be installed. Pre-final logs and the initial GUI crash are preserved, not rewritten as successes.

## H. GUI verification

Actual host-session test properties: `{'gdk_display_type': 'GdkWaylandDisplay', 'native_window_mapped': 'true', 'gtk_heartbeat_count': '139', 'yin_gui_analysis': 'passed', 'crepe_gui_analysis': 'passed', 'close_while_chooser_pending': 'passed'}`.
GTK 4.24.1, libadwaita 1.10.0, PyGObject 3.58.1, pycairo 1.29.2. This was a real mapped **GdkWaylandDisplay** window, not an import-only or Xvfb claim. The test loaded a file, analyzed using pYIN/YIN/CREPE-tiny, checked GTK timer activity/concurrent-job rejection, exercised native chooser cancellation, exported CSV/JSON/PNG, checked invalid-input recovery, and closed while a chooser was pending.
The first real GUI attempt segfaulted inside GTK when programmatically cancelling a FileDialog before presentation. A minimal GTK-only program reproduced the same fault even with retained references. Delayed cancellation succeeded. The app now defers its own shutdown while a chooser is pending and retains the parent through async completion; the regression test covers that path. The underlying GTK 4.24.1 immediate-cancellation bug remains outside this workaround. Nonfatal upstream GLib cancellation warnings are retained. Known upstream GI/Matplotlib deprecation floods are filtered only in the GUI test.
This updates verification for Stage 2; the historical Stage 1 report remains unchanged. No claim of exhaustive manual visual/accessibility QA is made. Actual exported human-reference overlays were inspected separately.

## I. Limitations

- The primary full-corpus neural experiment uses tiny, not full. Full has only a prespecified five-track held-out check; no full-model forty-track or full-model development calibration is claimed.
- The fixed split has four shared singer identities; track-bootstrap intervals are exploratory and may understate singer correlation. Five-fold support exists, but five-fold results are not invented.
- Human references are official expert annotations, not incontrovertible acoustic truth; ambiguous voicing and annotation boundaries remain limitations. Generalization to external singers, languages, devices, accompaniment or polyphony is not established.
- Synthetic noise success does not imply human consonant/breath rejection. Held-out human false alarms remain substantial for all three backends; F1 tuning sacrifices recall/RPA in the classical backends.
- pYIN/YIN share a family; CREPE is independent but its original training corpus overlap is not independently audited here. Neither periodicity nor lag correlation is calibrated pitch correctness.
- pYIN upper-bound octave errors and YIN nominal-bound overshoot persist. Window averaging still attenuates vibrato. Neural dither adds seeded pitch noise by upstream design.
- Whole-file processing and conservative duration/memory preflight remain; neural runtime overhead is additional to the classical-array estimate. Batch size controls activation memory, not a strict OS RSS cap.
- The native GTK immediate-programmatic-cancellation issue is worked around in app shutdown, not repaired inside the system library. Other GTK/compositor versions and exhaustive manual GUI quality remain unverified.

## J. Reproduction commands

```bash
cd <checkout>
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[crepe,benchmark,dev]'
vocalscope dataset download --path data/vocadito
vocalscope dataset verify --path data/vocadito
vocalscope analyze vocal.wav --estimator pyin --output results/pyin
vocalscope analyze vocal.wav --estimator yin --output results/yin
vocalscope analyze vocal.wav --estimator crepe --crepe-model tiny --device cpu --output results/tiny
vocalscope analyze vocal.wav --estimator crepe --crepe-model full --device cpu --output results/full
vocalscope benchmark --dataset-path data/vocadito --estimators pyin,yin,crepe --crepe-model tiny --split all --calibrate --output results/reproduce --cache-dir reports/stage2/cache
vocalscope benchmark --dataset-path data/vocadito --estimators pyin,yin,crepe --crepe-model full --split test --max-tracks 5 --output results/full-five
python -m pytest --run-neural -ra
GDK_BACKEND=wayland python -m pytest -m gui -v
GDK_BACKEND=wayland vocalscope gui
python scripts/stage2_stress.py --estimator crepe --model tiny --output results/stress.json
python scripts/stage2_performance.py --estimator crepe --model full --output results/performance.json
python -m build --no-isolation
```

Library versions used: `{"librosa": "0.11.0", "llvmlite": "0.50.0", "matplotlib": "3.11.2", "mir_eval": "0.8.2", "numba": "0.68.1", "numpy": "2.5.4", "psutil": "7.2.2", "pytest": "9.2.0", "resampy": "0.4.3", "scipy": "1.18.1", "soundfile": "0.13.1", "torch": "2.15.0+cpu", "torchaudio": "2.11.1+cpu", "torchcrepe": "0.0.24", "vocalscope": "0.2.0"}`.
The local dependency snapshot is stage2/requirements-tested.txt; system bindings and benchmark controls are recorded in stage2/environment.json. Model SHA256s and per-backend settings are retained in prediction metadata. Ordinary inference is fully offline after installation.

## K. Evidence-based recommendation

Keep **pYIN as the compatibility/ordinary-install default**, as required, with its Stage 1 settings unchanged. Offer **CREPE-tiny for accuracy-focused use on recordings resembling Vocadito**: it leads the measured held-out RPA/voicing comparison while remaining CPU-compatible. Its scores remain imperfect and its higher optional dependency/memory cost matters. Full CREPE is not a suitable interactive default on this CPU given measured throughput and only five matched human tracks. YIN is a useful much faster diagnostic baseline, with weaker human voicing behavior.
This recommendation is conditional on the measured corpus/split and resources. It is not a universal neural-superiority claim or an automatic default switch. Further singer-disjoint and external-corpus validation should precede a broader default-policy change.

## L. Stage 3 readiness

Available foundations: backend-normalized continuous F0/voicing with typed scores and provenance; source/annotation integrity; tested time alignment; classical/neural CPU isolation; stable structured exports; per-track metrics; development-only tuning; reusable prediction caches; honest failure coverage; and native estimator selection. These support later note-boundary and MIDI work, but note segmentation, MIDI generation, musical quantization and arrangements are **not implemented**.
