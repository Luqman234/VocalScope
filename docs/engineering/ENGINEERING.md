> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 1 — Engineering report

Implementation and validation performed on 9 November 2026 (Asia/Kuala_Lumpur).
The core and CLI are verified. Native GUI import is verified; physical Wayland
window behavior is pending the separate desktop test. No human-vocal accuracy
claim is made.

## A. Files changed

The workspace had no application code and no applicable AGENTS.md. Existing
virtual-environment and protected workspace directories were preserved; Git was
not initialized and no system packages were installed.

- `pyproject.toml`, `requirements.txt`, `MANIFEST.in`, `.gitignore`: package,
  entry point, one-command installation, source distribution and generated files.
- `src/vocalscope/`: audio ingestion, resampling, models, conversions, pYIN,
  export/import, backend-neutral plotting, CLI, native GUI and isolated worker.
- `tests/`: audio/configuration, note conversion, scientific accuracy, metrics,
  serialization/CLI, real-display GUI and subprocess lifecycle tests.
- `scripts/`: accuracy/runtime benchmark, voicing-prior comparison and timer test.
- `README.md`: Arch setup, usage, schema, timing, defaults and limitations.
- `reports/`: actual JSON measurements, test logs/XML, dependency snapshot and
  this report. `results/example/` contains a genuine CLI export of synthetic
  5 Hz vibrato; it is not a human recording or a GUI screenshot.

## B. Architecture

Audio is decoded read-only by soundfile, checked in blocks, downmixed by channel
mean, and optionally resampled by SciPy. AnalysisConfig validates bounds and
preflights duration/memory. The pYIN adapter returns an AnalysisResult with
unvoiced NaNs, original metadata, continuous MIDI, note/cents measurements,
versions, diagnostics and frame-center timestamps. Exports retain every frame.
The core and CLI import no GTK; PNG uses the Agg canvas directly. Plotting
retains NaN discontinuities and shows voicing separately.

The GTK application owns only presentation and orchestration. One background
coordinator handles a job at a time; pYIN runs in an owned headless child process
with JSON IPC. This isolates compiled code that retains the GIL. GLib.idle_add
is the only worker-to-widget update path. Closing the window signals process
termination and cleanup; parameter changes are clearly marked when the graph
still displays a previous analysis. File chooser behavior and rendering require
an accessible desktop to verify.

## C. Scientific results

Defaults selected after measured comparisons: 22,050 Hz, C2–D6, 2048-sample
frames, 512-sample hops, 0.1-semitone bins, no-trough prior 0.001, voicing switch
prior 0.01. No gate, gain normalization or pitch smoothing is applied.

All values below come from `benchmark.json`. Synthetic clips are 2 seconds,
except the silence-gap case (3 seconds). Interior scoring excludes 250 ms at
file edges and known discontinuities to avoid padded/mixed windows. Each typical
case has 65 interior frames; the gap case has 44 voiced and 22 silent interior
frames. Full-clip metrics and frame counts are retained in JSON. Errors are
measured only on mutually voiced frames; recall and RPA include missed voicing.
Undefined metrics are shown as —. Rates in this table are percentages.

| Synthetic signal | Median abs cents | Mean abs cents | Gross octave error % | Voiced recall % | False voicing % | RPA ≤50 cents % |
|---|---:|---:|---:|---:|---:|---:|
| A3 sine | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| A4 sine | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| C5 sine | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| 220 Hz, stronger 2nd/3rd harmonics | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Weak fundamental | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Missing fundamental (2nd + 3rd) | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Voiced / silence / voiced | 0.000 | 0.000 | 0.00 | 100.00 | 0.00 | 100.00 |
| Digital silence | — | — | — | — | 0.00 | — |
| 440 Hz, ±50 cents, 3 Hz vibrato | 5.090 | 5.086 | 0.00 | 100.00 | — | 100.00 |
| 440 Hz, ±50 cents, 5 Hz vibrato | 9.277 | 9.829 | 0.00 | 100.00 | — | 100.00 |
| 220→440 Hz integrated-phase glissando | 2.626 | 2.941 | 0.00 | 100.00 | — | 100.00 |
| Abrupt A3→A4, interiors | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Harmonic signal + noise, 30 dB SNR | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Harmonic signal + noise, 20 dB SNR | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| Harmonic signal + noise, 10 dB SNR | 0.000 | 0.154 | 0.00 | 100.00 | — | 100.00 |
| Harmonic signal + noise, 0 dB SNR | — | — | — | 0.00 | — | 0.00 |
| Noise only (seed 20261109) | — | — | — | — | 0.00 | — |
| A4, −100 dBFS peak | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| C2 sine | 10.000 | 8.000 | 0.00 | 100.00 | — | 100.00 |
| C6 sine (D6 upper bound) | 0.000 | 0.000 | 0.00 | 100.00 | — | 100.00 |
| A4 +23.5 cents, off-bin | 3.500 | 4.654 | 0.00 | 100.00 | — | 100.00 |

Apparent zero error for A3/A4/C5 and several 220 Hz tests reflects signals
exactly aligned with pYIN's 10-cent grid. The off-bin test is included to avoid
interpreting those special cases as universal precision. A low median can hide
outliers; the mean, gross pitch-error rate, octave-error rate and voicing counts
are available separately. Gross octave error means within 50 cents of a nonzero
integer-octave displacement. RPA uses available F0 within 50 cents divided by
all reference voiced frames; no estimate is emitted for unvoiced predictions,
so missed voicing counts as an error. It is not conditioned on correct voicing.

At 5 Hz vibrato, selected defaults yield correlation 0.99353 and a cents-standard-
deviation ratio of 0.70962: variation is tracked but still attenuated by the
window. At 3 Hz these are 0.99551 and 0.86357. A 1024-sample comparison improves
5 Hz vibrato but increases low-C2 bias; default 2048 is a provisional compromise.
No human dataset was used to tune or independently confirm it.

### Verified defects and resulting parameter choices

The original 4096/C2–C6/0.01-prior run is preserved in `baseline.json`. It found:

- 43.08% false voicing on the interior of the seeded noise-only clip.
- 5 Hz vibrato median/mean error 29.158/28.823 cents, correlation 0.80197 and
  retained variation ratio 0.13011. Controlled 2048-sample frames reduced the
  median error to 9.277 cents and retained ratio to 0.70962.
- C6 at the exact upper bound was detected as C5: 100% gross octave error.
  Adding D6 search headroom removed this error on the tested C6 sine.

The separately reproduced `voicing_comparison.json` includes three noise seeds
(7, 91, 20261109), both 2048/4096 frames and both 0.01/0.001 no-trough priors.
For 2048 frames, the original prior had false-voicing rates 16.92%, 30.77% and
53.85%; the selected prior had 0% for all three. Soft-tone recall remained 100%.
The conservative prior also rejected the 0 dB SNR tone completely. This loss is
reported rather than counted as zero pitch error. No probability threshold,
amplitude gate, calibrated pitch-confidence number or replacement F0 was added.

These are deterministic synthetic experiments, not population-level robustness
claims. Annotated human vocal accuracy has **not been independently established**.

## D. Test results

Final sandbox suite: **80 passed, 0 failed, 0 errors, 1 skipped**, 11.43 s recorded by JUnit.

The skipped test requires an accessible graphical display. Earlier execution
had 71 passed, 1 failed and 1 skipped; the noise-only failure led to the measured
prior comparison above. Subsequent added tests cover C2/C6, off-bin pitch,
fast vibrato, subprocess result equivalence/cancellation/errors, and pathological
resampling ratios. `pytest.xml` and `pytest.log` preserve the final run.
Headless CLI integration generated CSV, JSON and PNG with DISPLAY and
WAYLAND_DISPLAY empty and MPLBACKEND set to GTK4Agg, while asserting GTK was
never imported. JSON re-import preserves the numeric arrays exactly.

Wheel and sdist build, editable install, CLI help/version, actual CLI analysis
and all three export formats were exercised. Installed decoder tests passed for
WAV/FLOAT, FLAC/PCM_16 and OGG/Vorbis. Non-finite, empty, corrupt, short, clipped,
anti-phase stereo, memory-limited and unusual-rate inputs were exercised.
An independently installed wheel in `/tmp/vocalscope-wheel-smoke` also performed
real headless analysis; its import path was asserted to use the installed wheel,
not the editable source checkout. The sdist includes conftest, tests, scripts,
requirements and this report; the wheel includes the isolated worker module.

`pip check` reports unrelated conflicts from inherited system packages
(meowplayer-terminal/Pillow/watchdog, pipx/filelock, aiohttp/multidict). These
were preserved; no VocalScope dependency conflict was reported. The venv must
inherit PyGObject for the GUI, so unrelated system distributions are visible.
`requirements-tested.txt` records local scientific packages; system packages
are described in `environment.json` and README rather than hidden by that list.

## E. Performance

CPU: **12th Gen Intel(R) Core(TM) i5-1235U**, 12 logical CPUs, 16 GB target RAM.
Measured OS: `Linux-7.2.14-zen1-1-zen-x86_64-with-glibc2.44`; Python 3.14.9. No GPU was used.

Serial warmed runs, whole-file harmonic signal. Wall time includes loading
and result construction, excludes export and interpreter/module startup.
Peak RSS is Linux process high water, including imports/JIT and prior cases;
it is not per-clip incremental DSP allocation or total GUI+child memory.

| Audio duration (s) | pYIN time (s) | Load + analysis wall (s) | Wall / audio | Process peak RSS (MiB) |
|---:|---:|---:|---:|---:|
| 1 | 0.126 | 0.129 | 0.129 | 273.4 |
| 5 | 0.558 | 0.562 | 0.112 | 277.4 |
| 15 | 1.614 | 1.621 | 0.108 | 298.3 |

The first 2-second case in this benchmark process took 0.785 s; on-disk JIT caches already existed.
No speed on other hardware, uncached initial installation, or long human
recordings is implied. pYIN is whole-file, with a 300-second duration safeguard
and a separate conservative 1024 MiB DSP-array estimate that can reject shorter
files. Interpreter/JIT overhead is excluded from that estimate. Source buffer
and polyphase filter estimates are also checked. These are preflight checks,
not hard OS allocation limits. Child-process startup adds latency and its
interpreter/library memory is additional to the parent GUI.

### Responsiveness investigation

A thread-only warm 15-second pYIN test initially blocked a 10 ms main-thread
timer for 1.513 seconds, showing that a worker thread alone did not meet the
responsiveness requirement. The reproducible comparison is
`scripts/check_responsiveness.py` → `responsiveness.json`:

| Computation mode | Wall time (s) | Main-thread ticks | Maximum tick gap (ms) |
|---|---:|---:|---:|
| thread_only | 1.710 | 15 | 1567.15 |
| thread_with_child_process | 2.953 | 294 | 11.55 |

This is an indirect interpreter-lock/IPC measurement. It demonstrates removal
of the measured GIL stall; it is **not a physical GUI or Wayland test**. GTK
rendering, compositor behavior and interactive zoom still require the separate
real-display test/manual inspection.

## F. GUI verification

Imported GTK 4.24.1, libadwaita 1.10.0, PyGObject 3.58.1, pycairo 1.29.2 and Matplotlib's GTK4Agg canvas successfully.

The task environment advertises Wayland/Hyprland but `Gdk.Display.get_default()`
is None inside the sandbox. An actual `vocalscope gui` launch attempt returned
exit 2 with a clear no-display diagnostic; no window was displayed by the
agent. The automatic GUI test skipped for that exact reason. The user has been
given the real Wayland integration command and its result will be recorded
separately if available. Until then acceptance criteria for a visible window,
working native choosers and interactive desktop responsiveness remain unverified.
An exported graph was visually inspected; it cannot substitute for GTK testing.

## G. Reproduction commands

```bash
# System installation is performed by the user, not by the application:
sudo pacman -Syu --needed python python-pip python-gobject python-cairo gtk4 libadwaita libsndfile
cd <checkout>
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

vocalscope --help
vocalscope analyze --help
GDK_BACKEND=wayland vocalscope gui
vocalscope analyze vocal.wav --output results/voice --fmin C2 --fmax D6 --frame-length 2048 --hop-length 512 --formats csv json png
python -m pytest -ra --junitxml=reports/pytest.xml
GDK_BACKEND=wayland python -m pytest -m gui -v --junitxml=reports/gtk-wayland.xml
python scripts/benchmark.py --output reports/benchmark.json --durations 1 5 15
python scripts/benchmark.py --output results/original.json --frame-length 4096 --fmax C6 --no-trough-prob 0.01
python scripts/compare_voicing.py
python scripts/check_responsiveness.py
python -m build --no-isolation
```

CLI output CSV/JSON/PNG are generated together by default. See README for schema,
frame-centering, missing values, overwrite behavior and disconnected installation.
`results/synthetic_vibrato.wav` is a generated sample that can be analyzed locally
with the same command; it is not a human vocal recording.

## H. Limitations and acceptance status

- On the measured synthetic cases, pYIN tracking, silence handling, conversions,
  structured exports, plotting, headless execution and resource/input handling
  are verified. The visible native GUI remains unverified until desktop testing.
- No annotated human singing dataset or real human recording was supplied.
  Human-vocal accuracy, breath/consonant discrimination, room acoustics and
  accompaniment performance remain unverified. This algorithm also voices
  suitable instruments; it does not identify vocal sources.
- At 0 dB SNR the selected default lost all voiced recall in the tested clip.
  At fast vibrato the retained variation is about 71%, despite no smoothing.
  At C2 the selected window shows a 10-cent median bias. Other waveforms and
  seeds may behave differently. Pitch bins impose 10-cent nominal granularity.
- Search boundaries can cause octave errors. Headroom fixes the tested C6
  boundary case, not all octave errors; explicit C6 bounds retain the limitation.
- Clipping detection is heuristic; arithmetic-mean downmix can cancel opposite
  channels. Neither clipping nor phase cancellation is silently repaired.
- Long files are not streamed through pYIN, and the conservative memory estimate
  is not a strict cap. GUI child processes duplicate runtime/library overhead.
- CSV/JSON use standard missing values; per-file publication is atomic but a
  three-file bundle is not one transaction. Explicit overwrite can replace a
  subset if filesystem failure occurs mid-publication.
- Native file chooser opening/cancellation, GUI dark theme, toolbar interactions
  and physical Wayland responsiveness require real desktop/manual inspection.

## I. Next milestone

Stage 2 should compare independent pitch estimators on the same synthetic
signals plus a licensed, manually annotated human-vocal corpus, using aligned
frame centers, explicit voicing conventions, error distributions, octave-error
review, CPU/runtime/RSS measurements and reproducible versions. No alternative
estimator or transcription feature was added in Stage 1.
