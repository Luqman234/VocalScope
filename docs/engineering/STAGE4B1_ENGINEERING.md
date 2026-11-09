> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 4B.1 — Workstation stabilization

Executed on Arch Linux / Hyprland, Intel Core i5-1235U. Local patch build **0.5.1**. No push, tag, publication or shared audio-service restart occurred. All earlier reports and measurements remain historical evidence. This report distinguishes measured software behavior from pending human/device acceptance.

## A. Implementation summary

Changed GTK canvas/lifecycle, transcription workspace and interactive plotting, playback timeline/workspace, waveform cache, Gst bus wakeups/transport/watchdog, render coordination, optional configuration validation, packaging/docs and local version. Added `ui_metrics.py`, three stabilization test modules plus revision-race cases, profiling/loop/CPU/replacement/soak/listening scripts and a human acceptance procedure.

Corrections: persistent axes/note geometry; cached static grid/F0/waveform/notes; dynamic active/selected overlays; real GTK invalidation after Agg updates; four-source immutable waveform cache; no redraw on sub-sample render-duration differences; safe cursor/session reset; explicit signal/timer cleanup; event-driven Gst-owner wakeups; nanosecond-correct 50 ms loop validation; sink-progress watchdog; retained Pause/Stop intent in ERROR; coalesced recovery and idempotent close acknowledgement; cancellation-token activation and immediate retry; obsolete queued renders skip process creation; zero-count file leases are removed.

These are backward-compatible workstation fixes, warranting a **patch** rather than a new feature milestone. Version stayed 0.5.0 during reproduction and initial verification, then moved to 0.5.1 after real improvements and native/core tests passed. Final 208 tests and installed-wheel checks followed. Transcription and synthesis algorithms/schemas were not changed.

## B. Baseline reproduction

Protected 0.5.0 wheel was installed into `/tmp/vocalscope-stage4b1-baseline`, selected explicitly by PYTHONPATH. It is independent of the modified source. The probe loads the same 65-note human project, WAV vocal, rendered piano and SoundFont, requests 1100×800, and executes identical map/open/load/expand/start/seek/edit/undo/mix/render/loop/close actions. All scenario actions and polling use GLib callbacks, without sleep or blocking Future.result on GTK. Quantitative runs have no cProfile; a separate profile supplies call-path evidence.

Historical 710 ms gaps were not treated as steady-playback latency. Initial reproduction measured many-edit median delay 180.48 ms, p99 214.25 ms, undo/redo maximum 291.72 ms, and startup/import maximum 1858.52 ms. The later paired native baseline was faster on this shared host; results below use that matched pair, not the worst earlier run as a cherry-picked comparator.

Artifacts: `gui-baseline.json`, `gui-baseline-2.json`, `gui-baseline-profile.json/.prof`, `gui-baseline-native.json`, `gui-after-native.json`. CPU governor, thermal state, compositor scheduling, font/page caches and unrelated desktop activity were not controlled. No population confidence interval or independent-subject interpretation is assigned to correlated callbacks.

## C. Root-cause analysis

1. Each edit rebuilt the figure, two axes, tick formatters, legend, note rectangles and waveform axis. Main-thread operation probes measured roughly 200 ms typical reconstruction in the first baseline, rather than a DSP/worker wait. 27 interactive draws and 30 Figure.clear calls occurred in that scenario. Reusing stable artists removes that repeated work.

2. Every cursor tick redrew every note rectangle. The separate function profile recorded 57,181 rectangle draws; the first baseline TimelineView.update median was 12.91 ms. The patch bakes normal notes and redraws only the cursor and active/selected overlays. Main-thread operation timings, not overlapping profiler thread totals, are the authoritative durations.

3. Installed Matplotlib 3.11.2 GTK4Agg inherits the empty FigureCanvasBase.blit method. Old internal-position tests did not prove presentation. Explicit queue_draw now schedules the GTK canvas to paint its existing Agg buffer; the small canvas subclass counts actual on_draw_event delivery. This fixes missing frame presentation without rebuilding the renderer.

4. Rebuilding a 48 kHz render at 44.1 kHz changed container duration by about 4.5 µs; exact float inequality unnecessarily rebuilt the layout after replacement. The visual viewport now ignores differences below half a canonical sample. Actual audio duration/seek coordinates are unchanged.

5. Gst bus messages previously waited for a 10 ms command-poll timeout. A coalesced bus sync notification wakes the owner queue, retaining bus/command serialization. This removes avoidable seek/restart acknowledgement delay without changing the media clock.

Cold Python/scientific/Matplotlib imports and first GTK realization are separate from visible steady playback. Full first plots and out-of-range pitch-axis changes still require Agg rendering. Waveform decoding stays in an off-main worker; SoundFont/native rendering remains in Stage 4A subprocesses. No evidence pointed to neural inference during playback.

## D. GUI performance and methodology

Heartbeat interval 10 ms, monotonic nanoseconds. Scheduled deadline=previous callback finish+interval, matching a non-catching-up GLib timeout approximately; GLib millisecond quantization applies. Records scheduled/start/finish, positive scheduling delay, callback gap, missed intervals and heartbeat execution. Heartbeat execution measures its own overhead; named operation traces separately measure handler/draw work. Median/p95/p99/max plus counts over 16.7/50/100/250 ms are retained for both delays and gaps. All samples, including imports/startup/range changes, remain in JSON; phase classification is explicit.

Paired **native Wayland + PipeWire** scheduling delays, milliseconds (0.5.0 →0.5.1):

| Phase | Before median / p95 / p99 / max | After median / p95 / p99 / max |
|---|---|---|
| mapping | 0.04 / 46.97 / 88.41 / 88.86 | 0.08 / 32.69 / 77.07 / 77.81 |
| load_project | 0.24 / 132.86 / 149.69 / 153.90 | 0.07 / 109.68 / 129.84 / 134.88 |
| load_waveform | 0.05 / 68.70 / 87.75 / 92.52 | 0.07 / 71.30 / 80.64 / 82.98 |
| steady_playback | 0.11 / 7.89 / 11.81 / 16.03 | 0.12 / 6.02 / 8.75 / 11.29 |
| single_edit | 0.13 / 81.15 / 82.45 / 82.77 | 0.08 / 5.53 / 53.24 / 72.37 |
| many_edits | 81.88 / 93.98 / 105.39 / 110.57 | 0.14 / 9.63 / 15.12 / 61.58 |
| undo_redo | 70.65 / 89.55 / 124.99 / 139.81 | 0.12 / 9.19 / 15.99 / 26.32 |
| mix_switches | 0.15 / 5.61 / 19.29 / 72.29 | 0.12 / 5.23 / 7.75 / 8.66 |
| render_replace | 0.07 / 11.99 / 12.40 / 12.43 | 0.12 / 10.41 / 11.46 / 11.58 |
| steady_after_edit | 0.14 / 8.39 / 13.10 / 55.61 | 0.09 / 6.78 / 9.64 / 12.47 |
| loop | 0.14 / 5.98 / 10.29 / 13.14 | 0.09 / 6.39 / 9.43 / 11.15 |
| shutdown | 0.05 / 1.40 / 2.25 / 2.46 | 0.03 / 0.13 / 0.15 / 0.15 |

Steady goals achieved in this run: p99 8.75 ms, after-edit steady p99 9.64 ms, both below 50 ms; no steady scheduling delays above 100 ms. Cold initialize/import maximum 894.77 ms, mapping maximum 77.81 ms and first project plot maximum 134.88 ms are retained and classified separately. Pitch-range expansion still incurs a full redraw; no universal 30/60 fps claim.

Interactive plot-update median 85.89→5.84 ms; cursor-update median 9.02→2.60 ms. GTK paint callbacks 13→809; steady native paint rates 0.00→30.10 frames/s. The new run paints real continuous frames, so CPU comparisons do not describe identical presentation work.

GUI process steady CPU median 41.95→47.10% of one core; sampled peak RSS 262.78→258.29 MiB. This includes GTK/Matplotlib/scientific imports, unlike the historical 74.35 MiB audio-only process. More real frame delivery costs CPU despite reduced plot work. Paint callback completion is not compositor scanout or physical audio latency.

![Measured comparison](stage4b1/comparison.png)

## E. Loop reliability

Production policy remains an exact hard cut and bounded flushing seek, without crossfade or hidden sample smoothing. Sources keep one pipeline/clock. Tests cover periodic/nonperiodic sine, impulses, smooth zero-boundary waveform, silence-separated phrases, human vocal/piano, release and near-end material; 50 ms, 160 ms, 300 ms, 600 ms, 900 ms, 1 s, 1.5 s and 3 s regions.

| Matched case | Region s | Median extra loop period before / after ms | Complete cycles after | Incomplete internal cycles |
|---|---:|---:|---:|
| sine | 0.00–0.05 | 11.77 / 6.34 | 6 | 0 |
| sine | 0.21–0.37 | 9.70 / 6.14 | 6 | 0 |
| smooth | 1.00–2.00 | 10.61 / 7.63 | 6 | 0 |
| phrases | 1.00–4.00 | 11.35 / 6.55 | 6 | 0 |
| impulses | 0.60–0.90 | 10.82 / 5.97 | 6 | 0 |
| impulses | 5.00–5.90 | 11.61 / 6.94 | 6 | 0 |
| human | 2.00–3.00 | 8.49 / 6.57 | 6 | 0 |
| human_release | 31.40–32.00 | 8.60 / 6.84 | 6 | 0 |
| human_end | 33.00–34.50 | 8.14 / 7.01 | 6 | 0 |

Three-minute impulse loop: 180.01 s, 178 complete cycles, no incomplete internal cycles; max ground-truth impulse error 1 sample and relative source error 1 sample. Last intentionally interrupted partial cycles are explicitly recorded, never silently counted as full. Captured callback-period excess is software sink-clock delivery, not a speaker measurement. Additional loop time accumulates against an external metronome; shared source alignment is a different property.

Nonperiodic boundaries still jump; the prior 220 Hz hard-cut sample step≈0.0272 remains representative. First/subsequent resampling edge waveforms can differ by a sample while impulse alignment stays within one sample. An isolated documented non-flushing SEGMENT trial requested 8 repeats at 48/48 kHz and3 at 44.1/48 kHz but captured only 14,400 frames in each case despite repeated completion messages. It was rejected for production (`segment-experiment.json`). This does not prove seamless Gst looping impossible; integrated segment/running-time behavior needs further work.

## F. Transport and source mixing

Bus notifications wake the single owner thread; no independent player/timer was added. Rapid state/seek commands, 100 immediate mode switches, mixed sample rates/channels, shorter-source EOS, exact 50 ms repeats, loaded-session cursor reuse and paused stability pass. A/B/mix does not rebuild the pipeline or reset position. 20 ms stream-time gain ramps and the established mix attenuation are retained; DC 10–90% fade stays 16 ms and adjacent sample step≈8.33e-5. No limiter or automatic vocal normalization was added.

Final synchronization capture re-executed the established 17-case suite. Maximum relative/known-impulse error remains one 48 kHz sample, below the pre-existing two-sample tolerance; no tolerance relaxation. Source files and stored F0 values are unchanged.

## G. Edit audition and replacement

Current project revision, cancellation epoch and file leases are separate. A validated result preparing for activation receives an epoch token; cancellation invalidates it even if the same project revision is retried. Rejected activation restores the old source/position. Retry requested while a cancelled worker exits is queued for that current revision, and obsolete queued jobs skip native process creation. Zero-count pins are removed.

Historical native replacement 68 ms is retained in Stage 4B. Paired native API observations: 64.76→26.17 ms. Real human-project edited render+validation 0.553→0.273 s; not a universal guarantee. Preparation happens while old playback remains valid, then a controlled pause/rebuild/preroll/seek/resume follows.

Clock-paced appsink delivery interruption (four playing swaps each):

| Measurement | 0.5.0 | 0.5.1 |
|---|---:|---:|
| Median PCM-delivery gap ms | 36.11 | 20.94 |
| Maximum PCM-delivery gap ms | 43.87 | 21.64 |

Arrival gap subtracts the preceding block duration. It measures software PCM delivery, not electrical/acoustic interruption. New history records preparation seconds, pause start, acknowledgement and fresh pause-target position. Playback may advance while preparation runs; pre-call position error includes that legitimate advance. Paused restoration is separately tested within 20 ms. Source replacement remains a brief interruption, not seamless swapping or live pad replacement.

Real human-project stress: 12 edit/undo/redo/render/swap cycles, 24 obsolete revisions discarded, one retained render directory per completed cycle, no child after cleanup, root removed=True. Forced stale completion, cancelled activation after retry, cancellation during GUI replacement, close during preview, and immediate cancel/retry pass. No note/F0 regeneration or original-file mutation was used to improve sound.

## H. Audio-device / server recovery

Actual safe failure testing opens an additional client Unix socket and supplies it through the installed native sink fd property. The plugin duplicates the fd; shutting down that socket interrupts only the test client. No default device, other stream or server configuration is modified. The plugin left PLAYING without ERROR, reproducing a genuine blind spot.

Watchdog checks successful sink-render counts every 100 ms, while settled PLAYING, and enters ERROR after default 2 s without progress plus scheduling delay. It does not use media-time advancement as proof of delivery. Pause/seek/loading reset monitoring. This is sink-flow detection, not a proof of audible sound or hardware delivery. Timeout is configurable programmatically.

Final native private-client loss detected in 2.141 s, recovered in 0.032 s. Recovery produced exactly one RUNNING native node and advancing position. An absent private Pulse endpoint failed in 0.014 s; restoring the actual compatibility endpoint then played successfully. Pause/Stop in ERROR preserve user intent through recovery; concurrent Recover commands do not endlessly rebuild. Close acknowledgement is idempotent and resolves after actual cleanup.

Recovery is one explicit user request, not an uncontrolled retry loop. Actual physical unplug/replug, default-output migration and daemon restart remain pending. Routing may continue according to existing server policy; the application does not claim to identify or force hardware automatically. The manual procedure documents how to test safely. Native-library hangs outside measured cases cannot be forcibly interrupted by a Python Future timeout.

## I. Audio latency / CPU

Native initial-load API 143.87→86.52 ms; ready Play acknowledgement 1.30→3.99 ms. These encompass discovery/preroll/software state, not speaker onset. Source seek and sink-clock arrivals remain separately logged. Pipeline latency queries reported their own minimum (often 0); zero does not establish zero Bluetooth buffering.

Repeated audio-only 4 s windows: baseline CPU 10.2–12.5% (median 11.2), final 8.2–14.2% (median 14.0); 100%=one logical core. Owner poll counts/thread CPU are retained. Earlier short paired windows showed 7.5→14.9%, motivating repetition rather than a claimed twofold regression/improvement. Host load, frequency/caches and instrumentation matter; no controlled statistical equivalence is asserted.

Configured failure checks were reduced from every position query to 10 Hz after the owner-poll CPU probe. This changes only failure detection sampling, not UI rate, media position or audio data. Electrical loopback and acoustic latency were not measured; Stage 4A’s 6–8 ms SoundFont attack remains a separate historical property. Physical human listening is not claimed.

## J. Soak and resource lifetime

Final 0.5.1 transport soak ran **600.003 s** at real-time speed with 1703 mode switches, 568 seeks, 852 pause/resume pairs, 24 constructed/disposed sessions and 567 loop restarts. This is command stress, not uninterrupted physical listening. Transport source SHA256 at start matches the final source. Two earlier 600 s candidates also completed, and the separate 180 s loop captured PCM continuously.

After warm session teardown→final teardown: RSS 66.00→65.07 MiB; fd count 4→4; children after cleanup 0; surviving pipeline wrappers 0. Full 2 s resource samples include CPU/threads/RSS/fds/children. RSS growth alone is not labeled a leak or proof of no leaks; allocator, decoder/font/GTK caches remain possible explanations.

Fifteen unit lifecycle repetitions and four native windows verified disposed pipeline wrappers, stable post-warm fd counts, removed GLib timer sources, disconnected canvas handlers and cleaned preview roots. Native output tests verify stream removal. GUI endurance is bounded by the profiling/native scenarios; a 10-minute animated GUI plus device-listening soak was not performed. No claim of zero leaks on arbitrary codecs/fonts or unlimited duration is made.

## K. Native Wayland / PipeWire

Actual mapped GdkWaylandDisplay tests exercised historic analysis/CREPE/export/chooser guards, editable projects/MIDI, real synthesis, active playback frames, cursor/highlight/selection independence, waveform, cached edits, repeated session loads, seeks, loops, A/B/mix, preview cancellation/retry, repeated windows, private-client failure/recovery and shutdown. Both test sinks and real PipeWire output are used. Native paint callbacks prove GTK rendering, not human visual or acoustic acceptance.

Broad subjective/manual acceptance, physical output failure and end-to-end latency remain pending. Follow [PLAYBACK_ACCEPTANCE.md](../docs/PLAYBACK_ACCEPTANCE.md), which includes original/piano/mix, channel tones, clipping, seeking/looping, edit audition, shutdown, device migration/reconnect and measurement distinctions.

## L. Automated tests

| Run | Passed | Failed | Errors | Skipped | Elapsed |
|---|---:|---:|---:|---:|---:|
| Final headless incl. local neural + real SoundFont | 198 | 0 | 0 | 10 | 53.72 s |
| Final installed-wheel native Wayland/PipeWire | 10 | 0 | 0 | 0 | 39.01 s |

**208 distinct tests passed across complementary runs**, including all 196 historical cases and 12 added stabilization cases. Headless skips are the 10 native/display/explicit-output cases; they pass in the separate native run. Repeated runs/subset checks are not added to the distinct total. Two expected mir_eval empty-voicing warnings and 101 upstream PyGObject Python 3.14 event-loop-policy deprecations occurred; no final test failure. Counts are from `accepted-headless.xml` and `accepted-native.xml`.

Earlier failures remain retained: initial Agg test counted an explicit second draw as cache invalidation (corrected to measure no additional captures during 100 updates), exact 50 ms floating-point rejection, and real PipeWire disconnection without ERROR. Tests were not loosened to hide them. Deterministic latency unit tests use an injected clock; actual timing goals are measured in native scenarios rather than brittle CI wall-time assertions.

## M. Preservation and packaging

Verified **668 existing reports**, including the previously reported 581, plus 7 protected media/project/font/0.5.0 distribution artifacts. The inventory was enumerated before changes, not inferred from the prior count. All SHA256 values match. Acoustic/backends/segmentation/editable schema/MIDI/offline synthesis core source hashes remain unchanged. Modified old source files are recorded below.

`src/vocalscope/__init__.py`, `src/vocalscope/gui.py`, `src/vocalscope/transcription/workspace.py`, `src/vocalscope/transcription/plotting.py`, `src/vocalscope/playback/timeline_view.py`, `src/vocalscope/playback/workspace.py`, `src/vocalscope/playback/render_coordinator.py`, `src/vocalscope/playback/transport.py`, `src/vocalscope/playback/engine.py`, `src/vocalscope/playback/models.py`, `src/vocalscope/playback/waveform.py`

Final installed wheel 0.5.1 module `/tmp/vocalscope-stage4b1-final-wheel/vocalscope/__init__.py` completed YIN analysis, 65-note real SoundFont WAV rendering and headless playback without importing GTK/Torch (flags False/False). It also completed actual native PipeWire playback, pause, seek, source switching and cleanup (`wheel-native-final.json`). The candidate installation passed all 10 native tests; every Python module in the final wheel matches that tested source. Existing 0.5.0 distributions are preserved. Current wheel/source archive are local only; no audio, dataset, font or checkpoint asset is bundled. Arch GI/system-site-packages requirements and optional synthesis/neural behavior remain intact.

## N. Reproduction

```bash
# System installation, if needed, is performed by the user:
sudo pacman -S --needed python python-pip python-gobject python-cairo gtk4 libadwaita \
  libsndfile gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire pipewire-pulse fluidsynth
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e '.[synthesis,playback]'
GDK_BACKEND=wayland vocalscope gui

GDK_BACKEND=wayland python scripts/stage4b1_gui_profile.py --sink pipewiresink \
  --output results/gui-latency.json
GDK_BACKEND=wayland python scripts/stage4b1_gui_profile.py \
  --output results/gui-profile.json --profile results/gui.prof
python scripts/stage4b1_loop_validation.py --soak-seconds 180 --output results/loops.json
python scripts/stage4b1_soak.py --seconds 600 --output results/soak.json
python scripts/stage4b1_edit_soak.py --output results/edit-soak.json
python scripts/stage4b1_replacement.py --output results/replacement.json
python scripts/stage4b_validation.py --output results/synchronization.json
python -m pytest tests --run-neural --soundfont data/soundfonts/TimGM6mb.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests -m 'gui or audio_output' --run-output \
  --soundfont data/soundfonts/TimGM6mb.sf2 -v
python -m build --no-isolation --outdir dist
```

The GUI probe accepts --project/--vocal/--piano/--soundfont overrides. Default human probes require the existing Vocadito 1 project/audio and Stage 4A piano files; synthesis needs a verified licensed font. No downloads occur automatically. To reproduce the old baseline, install preserved `dist/vocalscope-0.5.0-py3-none-any.whl` with --no-deps --target to a separate directory, then set PYTHONPATH to it for the same scripts. Use fresh result paths where no-clobber publication applies. The diagnostic channel-tone script is explicitly not a production piano renderer.

API evidence: [Matplotlib blitting](https://matplotlib.org/stable/users/explain/animations/blitting.html), installed GTK4Agg/FigureCanvasBase source inspected; [Gst seeking](https://gstreamer.freedesktop.org/documentation/additional/design/seeking.html), [installed PipeWire core fd ownership](https://raw.githubusercontent.com/PipeWire/pipewire/1.6.10/src/gst/gstpipewirecore.c). Installed environment remains GStreamer 1.28.8, PipeWire 1.6.10, GTK 4.24.1, PyGObject 3.58.1, libadwaita 1.10.0, FluidSynth 2.6.2 and pyfluidsynth 1.4.0. No new dependency or system installation was needed.

## O. Remaining problems

Exact loops still gap and can click; replacement remains interrupted rather than seamless. First imports/mapping/plots and pitch-range changes remain slower than steady cursor work. Frame cadence depends on GTK/compositor/load; the measured goals are not a universal deadline guarantee. More actual GTK painting can increase GUI CPU. Correlated, short timing samples are descriptive, and other hardware/fonts/codecs need verification.

Physical human listening, electrical/acoustic latency, actual unplug/default-device changes and full daemon restart remain unverified. Watchdog observes sink flow rather than speaker audibility. Native-library deadlock recovery is limited by the C API. Four native reopen cycles and 10-minute audio stress do not prove unlimited GUI endurance or zero leaks. Python 3.14 GI deprecations should be tracked before 3.16. Original note-release/repeated-note/glissando and F0 weaknesses remain unchanged.

## P. Stage 4C readiness

Workstation engineering can proceed to separate expressive-performance experiments with reproducible acoustic truth, editable notes, real synthesis, one queried timeline, delivered native frames, bounded failure states, epoch-safe audition and improved loop/replacement behavior. Keep human listening/device acceptance as explicit gates before broader user claims. Do not promise gapless audio, seamless swaps or calibrated physical latency. No expressive interpretation was implemented in this milestone.
