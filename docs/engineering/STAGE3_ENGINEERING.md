> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 3 — Engineering report

Executed 9 November 2026, Asia/Kuala_Lumpur. Package release 0.3.0; transcription algorithm/schema 1.0.0. All numbers below come from retained artifacts, not estimates of unrun experiments.

## A. Implementation and files

Implemented acoustic onset features, naive/pitch-only/combined interpretation, robust note centers, validated monophonic notes, persistent non-destructive editing with undo/redo, MIDI/JSON/CSV/PNG exports, CLI transcription and singer-disjoint note benchmarking, and a native synchronized piano-roll workspace. No Stage 4 synthesis/playback, accompaniment, tempo-grid quantization or polyphony was added.

New package: `src/vocalscope/transcription/{models,onsets,segmentation,pitch_center,pipeline,midi_export,serialization,plotting,dataset,evaluation,benchmark,workspace}.py` plus `__init__.py`. Updated CLI, GUI, worker, package version, pyproject and README. Added `test_transcription.py`, `test_transcription_integration.py`, `test_transcription_gui.py` and Stage 3 experiment/report scripts. pretty_midi is a small mandatory MIDI dependency; Torch remains optional.

124 existing Stage 1/2 report artifacts were SHA256-verified unchanged against `stage3/preserved-stage12.json`. Historical experiments are preserved; new measurements are under stage3. Source audio, datasets and checkpoints were not modified or packaged. No Git repository initialization, publishing or system package changes occurred.

## B. Architecture and interpretation

Original AudioData -> immutable AnalysisResult -> centered audio features/candidate boundaries -> separate note interpretation -> generated baseline plus editable working notes. Original audio and continuous fractional F0 are never quantized, filled or overwritten. Backends remain pYIN/YIN/CPU CREPE; pYIN defaults remain unchanged.

Onsets use librosa centered 1024-sample STFTs and 256-sample hops, positive spectral changes, and energy dip/rise evidence. Scores are flux relative to positive-flux 95th percentile, not onset probabilities. Pitch-boundary strengths are plateau separations in MIDI semitones. Both retain source/type/timestamps, with shared config in the project. Voicing edges, stable pitch plateaus, brief pitch-compatible gaps, minimum duration, coverage and flatness drive segmentation. Pitch-only and combined share quality checks; the ablated difference is acoustic boundary evidence.

The interpretation copy uses median local pitch and a fixed 180 ms plateau context/IQR check to avoid vibrato peaks. A 70 ms window controls candidate separation. Short pitch-compatible gaps <=80 ms may join a note, but do not acquire invented F0. Long silence remains separated. Smooth slides are conservatively represented as broad gestures; wide centers and between-key centers are flagged. Very fast legato changes and ambiguous articulations remain weaknesses.

Note centers are medians in fractional MIDI, optionally trimming up to 30 ms/10% at each edge for center estimation only. Default velocity is 80, not an inferred piano intention. Source frames are half-open; output boundaries are frame midpoints clamped to source duration. Acoustic feature timing uses librosa onset-strength centering compensation without another half-window shift.

Note IDs survive editing/serialization. Validated operations include pitch/start/end, add, delete, split, adjacent same-key merge, undo/redo. A snapshot journal stores before/after states; replay chains and current notes are validated on load. Acoustic snapshots and generated baseline remain untouched. Manual key edits retain the measured pitch center and update cents relative to the chosen key. Manual splits retain parent source-frame provenance and flag it explicitly. Applied unsaved edits block replacement by new automatic results. Save a new project version before closing; automatic crash recovery is not implemented.

Projects are self-contained versioned JSON; editing/export can reopen without source audio. Regeneration needs unchanged source audio. Exports stage bytes, fsync and publish each file atomically; no-clobber publication protects existing files. A bundle is not a filesystem transaction against power loss. CSV and MIDI reflect current notes; acoustic schema 1.1.0 and old analysis commands/exports remain supported. GTK updates stay on the main loop; feature/DSP work runs in an owned subprocess with close-triggered cancellation.

## C. Corpus, annotations and leakage controls

Vocadito v3, [official record](https://zenodo.org/records/5578807), CC BY 4.0; Bittner, Pasalo, Bosch, Meseguer-Brocal and Rubinstein (2021). Original archive MD5 dea40fd18f14d899643c4ba221b33a46. All 40 audio/F0 tracks and both note sets were verified with the bundled official index. Total audio 817.128526 seconds; Stage 2's 140,782 frame annotations remain unchanged. A1 has 2237 notes, A2 has 1876 notes. Headerless note columns are onset seconds, frequency Hz, duration seconds, not MIDI/end-time. Frequencies remain fractional. Neither note set is substituted by estimator output.

Three releases exceed audio by 2.77–8.78 ms: track30/A1 and track31/both. They are preserved in evaluation; the loader allows at most 10 ms discrepancy and rejects larger misalignment. Predicted/editable notes cannot exceed the recording. Annotation overlaps are preserved if present; generated output is strictly monophonic.

Seed 20261109; 29 singer identities from the original metadata. New split: 24 development tracks/18 singers, 16 held-out tracks/11 different singers, 354.305805 held-out seconds. No shared singer identities. Five balanced singer-group folds are implemented and tested, but a complete five-fold experiment was not run.

Development IDs: `['2', '4', '6', '10', '11', '12', '13', '14', '15', '17', '20', '24', '25', '26', '27', '28', '30', '34', '35', '36', '37', '38', '39', '40']`. Test IDs: `['1', '3', '5', '7', '8', '9', '16', '18', '19', '21', '22', '23', '29', '31', '32', '33']`. Full singer lists/folds/hashes are in protocol.json and results.json. A prior one-track-per-partition smoke run validated execution; subsequent segmentation fixes were driven by controlled fixtures, not smoke reference scores. The final four-candidate protocol was recorded before held-out note evaluation.

Four prespecified configurations: base, onset threshold 0.6, pitch change 1.0, minimum duration 0.10 s. Objective: equal-A1/A2 track-macro onset+pitch F1 on development only, separately per backend; ties choose first. Held-out IDs never enter selection. pYIN selected pitch change 1.0, CREPE-tiny selected onset threshold 0.6. Other settings remain base: 60 ms minimum event, 80 ms bridge, 55% coverage, 0.45 flatness, velocity80. Shared settings stay identical across pitch-only/combined ablations. CLI/GUI universal defaults remain 0.8/0.35 unless explicitly overridden.

80 exact untuned Stage 2 baseline predictions (40 x 2 backends) were reused by recorded cache keys after checking source hashes and analysis/backend configurations. They do not use Stage 2 post-hoc calibrated thresholds. 240 final track/backend/method transcriptions and 480 annotator scores completed with zero failures. YIN works in transcription and performance tests; this primary note comparison evaluates pYIN and CREPE-tiny, not full CREPE or YIN on the corpus.

This is singer-disjoint segmentation validation within a corpus already examined in Stage 2 for F0 performance, not an external unseen corpus or a pretrained-model training-overlap audit. Existing Stage 2 development/test measurements are not recharacterized as singer-disjoint.

## D. Human-note scientific results

Standard [mir_eval.transcription](https://mir-eval.readthedocs.io/latest/api/transcription.html) bipartite one-to-one matching. Onset tolerance 50 ms; pitch 50 cents relative to the exported discrete key; offset max(20% reference duration,50 ms), inclusive tolerances. Undefined denominators use null. All methods use identical tracks/references. Primary aggregation gives both annotators equal weight, never best-of-two.

### Held-out track-macro scores (%)

| Backend | Method | Annotator | Onset F1 | Onset+pitch F1 | Onset+pitch+offset F1 |
|---|---|---|---:|---:|---:|
| pyin | naive | A1 | 51.95 | 43.19 | 29.68 |
| pyin | naive | A2 | 46.52 | 37.07 | 23.62 |
| pyin | pitch-only | A1 | 60.52 | 46.50 | 31.63 |
| pyin | pitch-only | A2 | 60.49 | 47.92 | 30.83 |
| pyin | combined | A1 | 73.80 | 61.62 | 43.65 |
| pyin | combined | A2 | 74.09 | 63.10 | 44.66 |
| crepe | naive | A1 | 37.11 | 32.50 | 16.63 |
| crepe | naive | A2 | 33.37 | 28.00 | 12.82 |
| crepe | pitch-only | A1 | 72.16 | 55.50 | 39.25 |
| crepe | pitch-only | A2 | 73.41 | 58.86 | 41.06 |
| crepe | combined | A1 | 75.98 | 61.57 | 43.00 |
| crepe | combined | A2 | 77.22 | 64.54 | 45.44 |

### Equal-annotator combined summary (%)

| Backend | Macro onset F1 | Macro onset+pitch F1 | Macro offset F1 | Micro onset+pitch F1 | Micro offset F1 | Matched overlap |
|---|---:|---:|---:|---:|---:|---:|
| pyin | 73.94 | 62.36 | 44.15 | 60.33 | 41.26 | 81.68 |
| crepe | 76.60 | 63.05 | 44.22 | 61.45 | 41.86 | 86.21 |

Micro scores pool matched/predicted/reference counts (annotator exposures counted equally); macro scores average track scores. Matched overlap describes matched offset-qualified pairs, not all notes. Per-track precision/recall/counts/overlap, micro/macro summaries and singer-macro scores are retained in results.json, supplement.json, per-track.csv and singer-scores.csv.

### Inter-annotator agreement and uncertainty

Symmetric all track-macro A1↔A2: onset F1 81.70%, onset+pitch 73.96%, offset-sensitive 64.32%. Original continuous reference frequencies are used, not rounded keys. Agreement is descriptive, not a strict ceiling on model scores.
Symmetric test track-macro A1↔A2: onset F1 83.84%, onset+pitch 77.10%, offset-sensitive 66.86%. Original continuous reference frequencies are used, not rounded keys. Agreement is descriptive, not a strict ceiling on model scores.

Paired 2000-resample singer-cluster bootstrap, seed 20261109, 11 held-out singers. Both annotators/tracks within a singer stay together; adjacent frames and correlated tracks are not treated as independent subjects. Differences are singer-macro, so they need not equal track-macro differences above.

- pyin combined minus naive: +21.08 percentage points; 95% interval [+15.91, +26.79].
- pyin combined minus pitch-only: +15.08 percentage points; 95% interval [+8.65, +20.22].
- crepe combined minus naive: +32.30 percentage points; 95% interval [+28.39, +36.90].
- crepe combined minus pitch-only: +6.00 percentage points; 95% interval [+2.67, +9.71].

CREPE-tiny minus pYIN combined: +1.99 pp, 95% [-0.54, +4.71]. This interval includes zero. These conditional small-corpus intervals are exploratory, not population guarantees or multiple-comparison-adjusted claims.

## E. Error analysis and controlled signals

Custom diagnostics are explicit temporal-intersection counts, not universal standards: pitch within50c and overlap >=min(50ms,25% reference duration); extra intersections per reference count fragmentation, per estimate count merging. An adjacent pair of same-pitch references sharing an estimate counts a repeated-note split failure. Misses/extras are unmatched onset+pitch events. False-rest events have zero temporal overlap with any annotated note, evaluated separately for each annotator.

| Backend | Annotator | Predicted/ref notes | Missed | Extra | Fragment intersections | Merge intersections | Repeated failures | Entirely in rest |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| pyin | A1 | 888/935 | 392 | 345 | 82 | 36 | 27 | 6 |
| pyin | A2 | 888/823 | 300 | 365 | 71 | 43 | 38 | 8 |
| crepe | A1 | 872/935 | 392 | 329 | 68 | 32 | 23 | 8 |
| crepe | A2 | 872/823 | 290 | 339 | 67 | 44 | 38 | 15 |

Rest attribution in rest-error-analysis.json: pYIN 6/6 A1 and6/8 A2 rest events have >50% unvoiced F0-reference support at emitted source frames; CREPE-tiny7/8 and10/15. This supports upstream false voicing in many events; the remainder expose note-vs-F0 annotation/boundary disagreement. Every automatic note requires upstream voiced pitch; the segmenter never creates an independent silent F0. Interpretation can nevertheless overextend or split these voiced regions. This diagnostic does not establish objective causal musical intent.

Independent pitch-track fixtures pass sustained notes, 3/5Hz vibrato, repeated articulations, ascending/descending legato, staccato, short-gap bridging, glissando, silence and flatness-based noise rejection. End-to-end controlled audio results are more limited:

| Backend | Case | Reference notes | Predicted notes | Onset+pitch F1 % |
|---|---|---:|---:|---:|
| pyin | sustain | 1 | 1 | 100.00 |
| pyin | repeated | 3 | 3 | 100.00 |
| pyin | ascending | 3 | 3 | 100.00 |
| pyin | descending | 3 | 3 | 100.00 |
| pyin | staccato | 3 | 3 | 100.00 |
| pyin | short_gap | 1 | 2 | 66.67 |
| pyin | vibrato3 | 1 | 1 | 100.00 |
| pyin | vibrato5 | 1 | 1 | 100.00 |
| pyin | glissando | 1 | 1 | 0.00 |
| pyin | silence | 0 | 0 | undefined (empty reference) |
| pyin | breath | 0 | 0 | undefined (empty reference) |
| crepe | sustain | 1 | 1 | 100.00 |
| crepe | repeated | 3 | 3 | 100.00 |
| crepe | ascending | 3 | 4 | 85.71 |
| crepe | descending | 3 | 4 | 85.71 |
| crepe | staccato | 3 | 3 | 100.00 |
| crepe | short_gap | 1 | 2 | 66.67 |
| crepe | vibrato3 | 1 | 1 | 100.00 |
| crepe | vibrato5 | 1 | 1 | 100.00 |
| crepe | glissando | 1 | 1 | 100.00 |
| crepe | silence | 0 | 0 | undefined (empty reference) |
| crepe | breath | 0 | 0 | undefined (empty reference) |

11 deterministic signals/backend, 22 full audio runs. Phase is integrated from known instantaneous frequency; seed 20261109 for breath-like noise. Clean silence/breath-like noise produce zero notes. A 30ms interruption still generates an acoustic articulation split (two notes), despite pitch-only gap bridging. CREPE creates an extra event around the middle note of the controlled melodies. These are retained failures, not hidden by changing references. The glissando reference is deliberately ambiguous (one70.5-MIDI gesture); pYIN and tiny choose opposite piano keys, explaining divergent tolerance scores. No unique intended notation is asserted.

The full inherited Stage 1/2 noise/octave/vibrato/glissando regressions remain passing. Stage 3 does not claim a newly measured multi-SNR note-transcription sweep; Stage 2 F0 noise results remain historical F0 evidence. Stable legato cases pass, but real onset/offset ambiguity, repeated-note merging and over-fragmentation persist. No algorithm was tuned on held-out note errors after these results. A threshold-candidate consistency fix makes standalone onset0.6 use the same fixed peak-prominence policy as the evaluated feature reuse; it changes neither the default0.35 candidates nor reported scores.

## F. Performance

Intel Core i5-1235U, CPU-only. Serial backend-specific runs on a shared desktop without affinity/governor/exclusivity guarantees. Audio-to-MIDI includes loading, estimator/model work, features, segmentation/centers, MIDI serialization and atomic fsynced publication. Cached pitch-to-notes separately recomputes features from loaded original audio and excludes audio decoding. RSS is cumulative process high-water including imported runtimes and earlier clips, not per-clip allocation or GUI+child sum. Interpreter startup is excluded.

| Backend | Clip s | Cold first call | Full audio→MIDI s | Cached pitch→notes s | Init s | Peak RSS MiB |
|---|---:|---|---:|---:|---:|---:|
| pyin | 1 | True | 1.1339 | 0.0090 | 0.0000 | 260.2 |
| pyin | 1 | False | 0.2044 | 0.0075 | 0.0000 | 269.3 |
| pyin | 5 | False | 0.8848 | 0.0324 | 0.0000 | 276.9 |
| pyin | 15 | False | 2.6049 | 0.1020 | 0.0000 | 303.8 |
| yin | 1 | True | 0.9242 | 0.0062 | 0.0000 | 236.4 |
| yin | 1 | False | 0.0208 | 0.0046 | 0.0000 | 237.7 |
| yin | 5 | False | 0.0766 | 0.0304 | 0.0000 | 256.1 |
| yin | 15 | False | 0.2265 | 0.1090 | 0.0000 | 301.9 |
| crepe-tiny | 1 | True | 3.5066 | 0.0141 | 2.4570 | 524.6 |
| crepe-tiny | 1 | False | 0.3474 | 0.0099 | 0.0003 | 562.9 |
| crepe-tiny | 5 | False | 1.6412 | 0.0691 | 0.0003 | 584.1 |
| crepe-tiny | 15 | False | 4.8925 | 0.2156 | 0.0002 | 597.2 |

Component feature extraction, onset candidate picking, segmentation, pitch-center time, MIDI export, estimator inference/init and runtime/audio ratio are retained in performance-*.json. Classical first calls include lazy/JIT work; the first neural call includes CPU model load. Full CREPE remains supported but is not rebenchmarked for Stage 3.

The human note experiment reused original Stage 2 estimator timing metadata, not cache lookup mislabeled as inference. Corpus note processing elapsed37.403 s, including development search/evaluation but excluding final visualization/bundle exports; this is not an audio-to-MIDI throughput number. Human per-track segmentation timings use cached audio features and retain original feature extraction times separately. Full CLI execution on 33.212 s Vocadito1 measured6.598s audio-to-notes for pYIN (65notes, inference6.391s) and13.293s tiny (64notes, inference10.506s, initialization2.395s). These cold CLI runs are separate from warmed cached corpus evaluation.

## G. MIDI and export validation

pretty_midi 0.2.11.post0 / mido 1.3.3. Format1 Standard MIDI, Acoustic Grand Piano/program0, constant velocity80, 120BPM, 9600ticks/quarter; note positions are preserved in seconds, with no beat-grid snapping. Valid empty output is tested. 8 actual human MIDI files / 503 note events were reopened; every pitch/count/velocity/timing validated. Maximum observed timing error 0.000025865s, below the27µs rounding tolerance. Details: midi-verification.json. This verifies playable symbolic files, not synthesis or audible piano playback.

## H. Tests and native GUI

Release headless suite including installed-model CPU tests: **140 passed, 0 failed, 0 errors, 2 skipped**, 64.56s. The two skips require a display; they pass separately below. The original 80 Stage 1 tests and Stage 2 regressions remain passing. Two expected mir_eval warnings concern empty voiced references/estimates.

Actual native Wayland release run: **2 passed, 0 failed, 0 errors, 0 skipped**, 37.16s; 2 GUI tests, 140 other tests deselected. Properties: `{"close_during_transcription": "passed", "close_while_chooser_pending": "passed", "crepe_gui_analysis": "passed", "gdk_display_type": "GdkWaylandDisplay", "gtk_heartbeat_count": "185", "native_window_mapped": "true", "note_edit_save_load_midi": "passed", "transcription_display": "GdkWaylandDisplay", "transcription_heartbeat": "360", "yin_gui_analysis": "passed"}`.

Real mapped windows exercised native chooser cancellation, pYIN/YIN/tiny analysis, GTK heartbeat/concurrent-job rejection, original exports, invalid input recovery, project generation in a subprocess, synchronized plots, selection and note pitch/time validation, split/merge/add/delete/undo/redo, save/load, MIDI read-back, duplicate-export failure, unsaved-edit replacement guard, repeated transcription, and closing during a transcription/chooser. Candidate overlays were inspected as exported plots. Broad manual visual/accessibility QA and other compositor/GTK versions remain unverified.

One nonfatal upstream GLib g_error_free cancellation warning remains in the release Wayland log. The known GTK4.24.1 immediate-chooser-cancellation segfault workaround is preserved: retain parent through async completion and defer close-triggered dismissal600ms. No immediate programmatic cancellation was reintroduced.

Preliminary failures are preserved: initial development integer serialization/path conversion and vibrato-boundary defects were corrected using fixtures; a worker hash precheck initially changed the established missing-file decoder diagnostic and was fixed; the first two-GUI-test run reused a D-Bus application identity and the second test now uses a distinct test identity. A piano-roll layout-engine warning was fixed. Do not interpret preliminary logs as release failures or rewrite them as successes.

## I. Dependencies, installation and limitations

Venv MIDI installation, editable installation, source archive and wheel builds succeeded without system-wide changes. A separate no-dependency wheel target installation transcribed Vocadito1 using YIN into 83 valid piano notes, without importing GTK or Torch. The wheel contains the transcription modules and no audio, archives, checkpoint or prediction-cache assets; see wheel-smoke.json. Direct VocalScope dependencies satisfy declared ranges. pip check also reports pre-existing unrelated inherited system-site-package conflicts (meowplayer-terminal/Pillow/watchdog, pipx/filelock, aiohttp/multidict); these packages were not changed. The requirement for system-site-packages remains necessary for system PyGObject/cairo.

Current release versions: `{"librosa": "0.11.0", "matplotlib": "3.11.2", "mido": "1.3.3", "mir_eval": "0.8.2", "numpy": "2.5.4", "pretty_midi": "0.2.11.post0", "psutil": "7.2.2", "pytest": "9.2.0", "scipy": "1.18.1", "soundfile": "0.13.1", "torch": "2.15.0+cpu", "torchaudio": "2.11.1+cpu", "torchcrepe": "0.0.24", "vocalscope": "0.3.0"}`. Scientific corpus artifacts retain their execution-time package tag 0.2.0 before the 0.3.0 packaging bump; transcription algorithm1.0.0 is explicit. Subsequent changes add source/project validation (including fingerprints on reopened CLI projects), provenance preservation and plotting/GUI fixes; numerical segmentation scores remain those of the frozen experiment. Raw confidence semantics are backend-specific and uncalibrated.

Remaining limitations: moderate note F1/release timing; missed fast legato and repeated notes; short articulation ambiguity; pitch-range/octave errors inherited from estimators; false voiced human rests; fixed flatness/duration constraints that can remove legitimate notes; ambiguous tuning/slides; no external corpus or full grouped-CV result; no pretrained training-overlap audit; full-file memory/resource safeguards rather than streaming; no autosave/crash recovery; no synthesized playback. No accuracy guarantee is inferred from clean synthetic success.

## J. Reproduction

```bash
cd <checkout>
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Optional CPU neural backends; no CUDA required:
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[crepe,benchmark,dev]'
vocalscope dataset verify --path data/vocadito
vocalscope analyze vocal.wav --estimator pyin --output results/pitch
vocalscope transcribe vocal.wav --estimator pyin --pitch-change 1.0 --output results/piano-pyin
vocalscope transcribe vocal.wav --estimator yin --output results/piano-yin
vocalscope transcribe vocal.wav --estimator crepe --crepe-model tiny --onset-threshold 0.6 --output results/piano-tiny
GDK_BACKEND=wayland vocalscope gui
vocalscope benchmark-notes --dataset-path data/vocadito --estimators pyin,crepe --prediction-report reports/stage2/vocadito-final/results.json --cache-dir reports/stage2/cache --output results/reproduced-notes
python scripts/stage3_reports.py --report results/reproduced-notes/results.json
python scripts/stage3_error_analysis.py --report results/reproduced-notes/results.json
# Without historical predictions/cache, omit both options to run estimators:
vocalscope benchmark-notes --dataset-path data/vocadito --output results/fresh-notes
python scripts/stage3_synthetic.py --estimator pyin --output results/synthetic-pyin.json
python scripts/stage3_synthetic.py --estimator crepe --output results/synthetic-tiny.json
python scripts/stage3_performance.py --estimator pyin --output results/performance-pyin.json
python scripts/stage3_performance.py --estimator crepe --output results/performance-tiny.json
python -m pytest --run-neural -ra
GDK_BACKEND=wayland python -m pytest -m gui -v
python -m build --no-isolation
```

Core editing/re-export is available without GTK: load_project(path), project.edit/add/delete/split/merge/undo/redo, save_project(project,new_path), export_bundle(project,new_directory). Use fresh experiment/export names; previous results are protected. Neither test execution nor normal inference downloads data/models. See README for Arch system packages, format/schema and GUI workflow.

## K. Recommendation and Stage 4 readiness

Keep pYIN as the compatibility/default backend. Combined segmentation improves on these naive and pitch-only baselines for both tested estimators; the singer-level CREPE-vs-pYIN note interval includes zero, so Stage 2 F0 superiority does not establish superior note transcription. CREPE-tiny remains an optional accuracy-oriented acoustic estimator, at increased runtime/memory cost.

Validated editable notes, immutable F0, onset provenance, versioned projects, MIDI timing, independent CLI/GUI engines, both-annotator matching, singer grouping and reproducible ablations are ready for future expressive rendering/playback and stronger musical interpretation. Stage 4 would need a licensed synthesizer/SoundFont path, audio rendering/playback lifecycle, explicit expressive timing/velocity decisions and independent listening/annotation evaluation. None is implemented here.
