> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope 0.5.1 — GUI DSP memory-budget fix

Implemented and verified on Arch Linux / Hyprland / native Wayland. Package
version remains **0.5.1**. No release was published, no dependency or system
configuration changed, and historical distributions were preserved.

## Behavior and implementation

The historical 0.5.1 wheel reproduces the reported failure: `gui
--max-memory-mb 2048` exits 2 with an unrecognized-argument error. The patched
CLI accepts the option, validates it before importing GTK, and passes it through
`run` → `VocalScopeApplication` → `VocalScopeWindow`.

**Analysis parameters → Maximum DSP memory (MiB)** is an editable setting.
The default remains **1,024 MiB**. Positive finite values, including 512.5,
2,048 and 4,096 MiB, are supported; invalid text, zero, negative values, NaN and
infinities are rejected. The current budget appears in the parameter summary.
The setting remains available for every estimator and is disabled with the
other analysis settings while an analysis/transcription job runs.

This is a **conservative admission estimate for DSP working arrays**, not
allocated or reserved RAM, an OS memory limit, or a guarantee about process RSS.
The estimate and its formula are unchanged. Python, libraries and JIT overhead
still require additional memory. Available physical RAM is not automatically
reserved or used to cap this explicit setting.

Audio loading and analysis receive the current `AnalysisConfig`, including the
budget. Analysis already serialized the full configuration into its child;
the missing GUI field was the original propagation gap. Note generation now
also sends the current budget explicitly to its existing isolated worker.
That worker overrides only the source-reload resource policy, retaining the
original acoustic configuration, frame times, F0, and estimator provenance.
It records the effective policy in `project.timings.dsp_resource_policy`.
The additive metadata survives project saving and reopening. Existing calls
to `transcribe_in_process(result, cancelled)` continue using the saved budget.

An exceeded DSP estimate now identifies the estimate and configured budget,
names **Maximum DSP memory (MiB)** in **Analysis parameters**, and gives the
equivalent `--max-memory-mb` option and other resource-reduction choices.
No transcription, onset, pitch-estimation, playback or synthesis algorithm
was modified.

Changed production files:

- `src/vocalscope/cli.py`: GUI option and initial validation/forwarding.
- `src/vocalscope/gui.py`: initial application/window budget, editable field,
  tooltip, current-budget reader and parameter summary.
- `src/vocalscope/worker.py`: backward-compatible transcription resource-policy
  override, child-side validation and effective-policy metadata.
- `src/vocalscope/transcription/workspace.py`: read/validate the current budget
  before starting note generation.
- `src/vocalscope/models.py`: actionable resource-admission error text only.

README instructions and two focused test modules were added/updated. No
packaging dependency, schema version or release version changed.

## Completed verification

| Final run | Passed | Failed | Errors | Skipped | Time |
|---|---:|---:|---:|---:|---:|
| Complete headless regression, local neural models and real SoundFont enabled | 216 | 0 | 0 | 12 | 71.48 s |
| Complete native Wayland/PipeWire category | 12 | 0 | 0 | 0 | 40.65 s |
| Focused cases repeated against fresh installed wheel, including native GTK | 20 | 0 | 0 | 0 | 19.77 s |

**228 distinct tests passed**, comprising all 208 previous cases and 20 new
cases. The 12 headless skips are the display/output cases passing separately
on the actual native session. The 20 installed-wheel repetitions are not added
again to the distinct total. Final runs had two expected `mir_eval` warnings,
129 upstream GI deprecations in the native regression run, and nine upstream
GTK/Matplotlib deprecations in the installed-wheel focused run.

New coverage includes CLI defaults/forwarding/help, rejection before GTK import,
shared numeric validation, the 1,522 MiB admission boundary, actual analysis
and transcription subprocesses, low-budget failures and retry, immutable F0,
persisted resource metadata, and CLI-driven mapped Wayland application runs.
The native tests exercise the real application main loop and workers; they do
not mock DSP results. In-process test IDs are isolated from earlier registered
test applications. Tests preserve the existing chooser-cancellation guards.

Initial verification logs are retained. Test-driver corrections addressed
argparse line wrapping, numeric JSON representations and existing source-hash
enrichment, GI vfunc registration, and retained test-application D-Bus IDs.
Final exact F0 and scientific tolerances were not relaxed.

### Real human-vocal check

The installed `.venv/bin/vocalscope` entry script was executed with `gui
--max-memory-mb 2048`, with user actions automated through GLib callbacks.
A real `GdkWaylandDisplay` window loaded `data/vocadito/Audio/vocadito_1.wav`,
ran pYIN in the actual DSP subprocess, generated notes in the transcription
subprocess, and saved new analysis/project files:

- Source duration: **33.212245 s**; **1,431** analyzed frames.
- Analysis budget: **2,048 MiB**; transcription budget: **2,048 MiB**.
- Working-array admission estimate: **233.947540 MiB**.
- Generated notes: **65**; F0 arrays were unchanged by note generation.
- Observed inference: **4.049 s**; cached-pitch-to-notes: **0.594 s**.
- Source SHA256 remained
  `b509768315efad8120183b48e01d6090f1649d5bcc691241940dc7a100274ab8`.

New outputs are in `results/gui-memory-budget-human/`; the machine-readable
result is [native-human.json](gui-memory-budget/native-human.json). This is
functional verification, not a new transcription-accuracy or speed benchmark.

The user's specific 1,522 MiB recording was not identified by path. Its reported
admission requirement was reproduced mathematically using the unchanged
estimator formula: a 1,522 MiB estimate fails at 1,024 MiB and succeeds at
2,048 MiB, without allocating a test-only 1.5 GiB array. The actual human clip
above has a lower estimate; it verifies both real worker workflows with the
increased setting, rather than claiming the unidentified recording was tested.

## Compatibility and preservation

All **1,284 inventoried historical files** remain byte-identical: 763 report
artifacts, 95 result artifacts, 12 distributions, and 414 local data files.
The inventory was captured before changes in
[historical-sha256.json](gui-memory-budget/historical-sha256.json).
Original recordings, saved projects, reports and benchmark results were not
overwritten. Core pitch, note-segmentation, MIDI, synthesis and playback source
hashes remain unchanged outside the five focused files listed above.

A fresh wheel built in `/tmp/vocalscope-memory-patch-dist/` was installed into
`/tmp/vocalscope-memory-patch-wheel/`, without replacing the historical 0.5.1
wheel in `dist/`. All packaged Python modules match the tested checkout.
The focused suite passed against this installation, including mapped GTK
analysis and transcription. See [wheel.json](gui-memory-budget/wheel.json).

## Reproduction

Use the existing project venv; no new dependencies are needed:

```bash
cd <checkout>
source .venv/bin/activate
GDK_BACKEND=wayland vocalscope gui --max-memory-mb 2048
```

Expand **Analysis parameters**, inspect/change **Maximum DSP memory (MiB)**,
open a recording, click **Analyze**, then **Generate notes**. A larger setting
can also be applied to note generation from an existing saved acoustic result;
pitch analysis does not need to be recomputed merely to change that policy.

```bash
python -m pytest tests --run-neural --soundfont data/soundfonts/TimGM6mb.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests -m 'gui or audio_output' \
  --run-output --soundfont data/soundfonts/TimGM6mb.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests/test_gui_memory_budget.py \
  tests/test_gui_memory_budget_native.py -v
```

The full output category runs short low-gain streams and interrupts only its
own private test connection; it does not restart shared audio services.
Optional neural/SoundFont cases require the already installed local assets.
The standalone human-check driver is retained in
`reports/gui-memory-budget/native-human-check.py`; it requires the local
Vocadito audio and a fresh `results/gui-memory-budget-human/` directory.
Final JUnit files and complete logs are retained under `reports/gui-memory-budget/`.

Actual process peak memory for the unidentified recording was not measured.
This patch changes admission configuration, not the existing resource estimator
or OS allocation behavior. Prior acoustic, loop, listening and hardware-device
limitations remain as documented in the earlier engineering reports.
