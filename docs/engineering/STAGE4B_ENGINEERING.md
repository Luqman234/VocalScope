> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 4B — Engineering report

Executed 9 November 2026 on Arch Linux / Hyprland. Local milestone build **0.5.0**; no release was published. This report separates actual decoded PCM, queried media time, native output-stream operation and unmeasured physical acoustics. Stages 1–4A measurements remain historical evidence; no transcription accuracy was recharacterized.

## A. Implementation summary

Added `playback/models.py`, `gst.py`, `sources.py`, `engine.py`, `transport.py`, `mixer.py`, `timeline.py`, `render_coordinator.py`, `diagnostics.py`, `waveform.py`, `timeline_view.py`, `workspace.py` and package initializer. Extended CLI, GTK window and transcription workspace, optional packaging/pytest markers and README. Added 25 playback test cases, timing/performance/wheel-validation scripts and this report.

Implemented Play/Pause/Resume/Stop, shared seeks, region loops, vocal/piano/mix, source gains, queried-time cursor, waveform navigation, active-note highlighting, edit-driven real synthesis, revision-safe activation, controlled source replacement, cancellation and explicit recovery. No Stage 4C interpretation, microphone processing or new pitch estimation during playback.

Following earlier minor-milestone conventions, the version remained0.4.0 through initial implementation, real pipeline tests and five native GTK checks. It moved to0.5.0 after those passed. The hardened release then passed the full regression and seven native checks and was installed from a fresh wheel. No push/tag/publication/system installation occurred.

## B. Actual architecture and ownership

One Gst.Pipeline owns both branches: `uridecodebin → queue(100 ms) → audioconvert → audioresample → F32LE/48 kHz/stereo caps → volume → audiomixer`. Common output: `audiomixer(10 ms output blocks) → master gain → audioconvert → F32LE caps → one sink`. Dynamic pads link only the first audio stream. The original files are read-only. Playback rate is fixed at1.0.

A single non-daemon Gst-owner thread serializes commands and polls its bus. Command Futures acknowledge actual state changes or confirmed source segments, rather than button presses. No private GLib loop is required by headless clients. Streaming callbacks link pads, translate seek coordinates, record segment acknowledgements and inspect/capture PCM; they never touch GTK. GTK polls immutable snapshots every33 ms and receives worker completion through queues. Synthesis stays in Stage4A owned subprocesses, coordinated off the GTK thread.

Position is Gst query_position(TIME), never accumulated GUI/wall time. GstClock running time and the actual GstSegment end provide a loop-end fallback when a coarse sink query stops just before the region end. Those clock calculations do not replace the canonical media position. Diagnostic wall clocks measure operation completion only.

Seeks flush the common pipeline with ACCURATE and an explicit stop. Source probes translate canonical time T to clamped local T−offset, preserve seek sequence numbers and update mixer pad offsets. Both source SEGMENT acknowledgements plus settled pipeline state are required before completion. A shorter EOS branch supplies silence while the longer branch continues. Session duration=max(source duration+offset,0), preserving piano tails. Offsets default0, are limited to±30s, and never assume a universal SoundFont attack correction.

[GStreamer seeking design](https://gstreamer.freedesktop.org/documentation/additional/design/seeking.html) and [audiomixer](https://gstreamer.freedesktop.org/documentation/audiomixer/audiomixer.html) informed the pipeline; the sample-rate restriction is addressed explicitly by each branch’s resampler/caps. Application behavior was then measured with actual pipelines.

## C. GStreamer / PipeWire environment

Python 3.14.9, GStreamer 1.28.8; installed Arch packages: `gstreamer 1.28.8-1`, `gst-plugins-base 1.28.8-1`, `gst-plugins-good 1.28.8-1`, `gst-plugin-pipewire 1:1.6.10-1`, `pipewire 1:1.6.10-1`, `pipewire-pulse 1:1.6.10-1`, `python-gobject 3.58.1-1`, `gtk4 1:4.24.1-1`, `libadwaita 1:1.10.0-1`, `fluidsynth 2.6.2-1`. Full plugin discovery is in [environment.json](stage4b/environment.json). Its package version entry0.4.0 records discovery before the release bump; the installed wheel and final tests use0.5.0.

All required factories were available, including uridecodebin, queue, audio conversion/resampling, audiomixer, volume, WAV/FLAC decoding, GstApp, GstController, GstPbutils, pipewiresink, pulsesink, fakesink and appsink. No gst-python Python plugin dependency was needed for GI usage. Arch system-site-packages supplies compiled PyGObject. The playback extra is deliberately empty; pip does not install these system libraries.

Real default output was `* media.class = "Audio/Sink"; * node.description = "UGREEN HiTune Max5c"; * node.name = "bluez_output.5B_DD_09_38_AD_EE.1"`. The native test selected `pipewireclock5` and verified a RUNNING PipeWire audio node, then its removal by persistent object.serial (numeric IDs are immediately reusable). Installed-wheel auto-selection chose **pipewiresink**. Explicit PulseAudio-compatible output also completed against the existing PipeWire compatibility server (GstPulseSinkClock). No server restart, default-device change or second daemon was used.

Auto mode tries native PipeWire first, then PulseAudio-compatible output on an initialization ERROR. Both paths were exercised separately; forced real native-server unavailability was not tested. No ALSA/other-device fallback is selected.

A reproduced PipeWire1.6.10 deadlock mattered: paused flushing seek waited for its loop lock while its format callback waited for an inactive audio buffer pool. Native backtraces and failed experiments are retained in `pipewire-native-stack.log`, `pipewire-pool.log` and related logs. A queued output branch and merely requesting its pool did not fix it. The release performs a **muted first-buffer PLAYING bootstrap**, waits for actual native rendered-buffer stats, pauses, then restores master gain before the final seek/preroll and READY. A real native DC-preroll test verifies that the first audible buffer is retained at the requested gain. Source commands and Close are deferred until that bootstrap is safe. This workaround is grounded in the [installed-version upstream sink implementation](https://raw.githubusercontent.com/PipeWire/pipewire/1.6.10/src/gst/gstpipewiresink.c); no system library was patched.

## D. State machine / recovery

EMPTY → LOADING → READY → PLAYING ↔ PAUSED; Stop → STOPPED at media0. Shared operations expose SEEKING or RECOVERING; failures expose ERROR and shutdown CLOSING/EMPTY. Wanted state is distinct from actual acknowledged state. Repeated state commands do not create streams. During seeking, newer seek requests coalesce; displaced Futures return Superseded. Stop interrupts queued seek intent safely. Early native Stop/Close and close during loading were executed.

EOS pauses at the end; Play after EOS seeks to0. Enabled loops start at their beginning if needed; Stop resets to0 even outside the region, and the next Play enters the loop. Loop bounds require0≤start<end≤duration and at least50ms. Seek outside an enabled loop is rejected with an actionable error.

Bus ERROR disposes the pipeline and resolves outstanding commands with failures. Recover rebuilds one pipeline, preserving intended position, mode, gains and playing/paused intent. CLOCK_LOST triggers framework clock reselection via pause/resume; LATENCY recalculates latency. Bus fault/clock-loss tests used genuine Gst messages with controlled faults, not an actual disconnected device. Device unplug, server loss and default-device switching are still manual acceptance items.

## E. Synchronization and timing

Prespecified tolerances before experiments: captured PCM error≤2 canonical samples (41.67µs at48kHz), settled seek query within20ms, paused drift≤2ms. Source switch DC10–90% fade14–25ms and adjacent sample step<0.002. These tolerances were not selected after seeing the results.

| Experiment | Observed | Measurement category |
|---|---|---|
| 12 initial/seek/offset/mono-stereo cases | max 1.000 samples | Captured PCM vs known impulse times |
| Loop source alignment | max 1.000 samples | Captured PCM between branches |
| 120s real-time capture | 120.102s elapsed; max 1.000 samples relative error | Selected software clock, not speaker output |
| Drift change from first to last impulse | 1.000 sample | Relative PCM timing |
| Pause | 0.000000000s drift | Gst media position |
| Loop restart excess over0.3s region | 5.52–17.40ms | Software acknowledgements / wall time |
| Nonperiodic220Hz loop boundary jump | 0.027218 float amplitude | Captured PCM; click risk |
| Physical speaker latency / human listening | Unmeasured / not performed | No acoustic claim |

Known ground truth used timestamped impulses, not pitch estimates. WAV44.1kHz and FLAC48kHz, mono/stereo, initial silence,±offsets, seeks at0.6/0.74/0.76 near an impulse, shorter sources, EOS and repeated loops were exercised. Complete0.6–0.9s loop cycles each contain14,400 frames. SEGMENT seeks initially stopped the mixed-rate branch early; bounded ordinary flushing seeks/EOS fixed the demonstrated truncation.

![PCM timing evidence](stage4b/synchronization.png)

Both fast and120s real-time experiments are retained: [fast capture](stage4b/synchronization-final.json), [real-time capture](stage4b/synchronization-realtime.json). The120s run used appsink with actual clock pacing, not two minutes of physical playback. Loop gaps and nonperiodic sample jumps mean **neither gapless nor clickless looping is claimed**. Gst sink latency queries are recorded but a reported0 is not zero device/Bluetooth latency. Stage4A’s6–8ms sampled attack behavior remains separate and unchanged.

## F. Mixer / switching

Vocal/Piano/Mix keep both decoded branches scheduled. Gains0–1, Mix applies half of each source gain, common master0.8. GstController absolute linear bindings apply nominal20ms stream-time ramps; a local envelope record computes interruption points without a Python audio timer. No normalization/limiter changes the source. Finite output is checked and the GUI displays current buffer peak plus clipping risk at≥1.

DC capture: first10% gain change 85.10ms after the queried switch position,10–90% fade 16.00ms, max adjacent step 0.00008333. Pipeline generation stayed 1; source switching did not reset position. Lookahead means the transition is not immediately audible on request. The DC test isolates gain shape; it is not a listening quality score. Paused switching flushes already-transformed preroll while preserving position.

## G. GTK workspace / responsiveness

Functional controls: source choosers and paths, Load session, Play/Resume, Pause, Stop, Recover output, Vocal/Piano/Mix, independent gains, piano offset, seek slider, loop bounds/apply/selected note, automatic edit audition, render/update and cancellation. The existing rendering and editing controls remain. The controls area scrolls to retain graph space. No decorative playback controls exist.

Waveform min/max overview is computed in an off-main worker with stale-generation rejection. All three axes share seconds/zoom. Waveform click or plot double click seeks; single piano clicks keep note selection. An80ms debounce and transport coalescing prevent pointer-event seek flooding. Navigation toolbar mode disables timeline clicks. Cursor positions come only from cached Gst queries. Green active notes use start≤t<end; orange selection is independent and overlapping activity is unit tested.

Actual GdkWaylandDisplay checks passed for both fakesink and real pipewiresink. Snapshot age: fakesink p95 **10.76 ms**, max **18.38 ms**; PipeWire p95 **10.21 ms**, max **12.89 ms**. This is age of the queried snapshot at the drawing callback, not physical playhead-to-speaker latency.

A 20 ms heartbeat continued through playback/render/editing; observed callback-gap p95 was 165.18 / 167.32 ms and max 706.67 / 479.20 ms (fakesink / PipeWire). These gaps include initial window mapping, full plot/layout rebuilds and test-driven edits, not only steady playback; a guaranteed30/60fps UI is **not** claimed. Audio continues independently. Normal cursor movement uses blitting. A demonstrated duplicate plot reconstruction per editor update was removed; remaining main-thread layout redraw remains an optimization opportunity.

The native test also plays original audio before any transcription, seeks/pauses, highlights without selection mutation, renders real piano, changes note pitch during playback, activates the new revision, loops, stops, cancels/retries the actual preview control, rejects invalid offsets, and closes during a pending edit rerender with all owned resources removed. The previously reproduced native chooser cancellation workaround remains; existing chooser/cancel/close tests passed. Broad manual visual/accessibility acceptance is not claimed.

## H. Editing / render revisions / source replacement

The Stage3 project and current edited notes are authoritative. Every relevant edit advances a monotonic session revision before150ms debounce. The coordinator tracks current/requested/in-progress/validated/active revisions separately. A two-worker coordinator reuses Stage4A isolated rendering and independent audio verification. Old valid audio is retained on error or cancellation and is labeled stale. SoundFont/render-setting changes invalidate previews; an unchanged current preview avoids rerendering.

Activation has a locked linearization point: the current revision is checked again after source preroll, before commit. A newer edit can invalidate even a result already preparing for replacement. Rejected activation rolls back to the prior session/position. A forced old real render delivered after a newer one was rejected. Cancellation/failure/retry preserve the previous real audio; negative revision IDs fail.

Explicit file leases keep an audition WAV until its decoder reaches NULL. Obsolete files are removed only when unleased; close shuts down playback before joining render jobs/deleting owned temporary directories. No permanent render/project/source is overwritten. Session revision IDs and transport settings are not persisted as a new note-project schema; save Stage3 edits normally.

Native human-project background render+validation: 0.488s; edited render+validation 0.523s. Paused replacement 76.62ms; playing replacement 67.97ms. The edit-render plus playing-swap measured sum is 0.591s, excluding GUI150ms debounce and poll delay.

Replacement captures fresh queried position, briefly pauses/rebuilds the common pipeline, prerolls/seeks and resumes if requested. The original vocal file is preserved, but its decoder is rebuilt too. This is safe controlled replacement, **not seamless replacement**. The old decoder is NULL before file disposal. No duplicate old/new playback pipelines run concurrently.

## I. Reliability / demonstrated defects

Executed: missing/corrupt audio, unavailable optional GI, non-finite float PCM, invalid config/loops/revisions, rapid Play/Pause/seeks, Stop during pending seeks, close during load and native bootstrap, actual EOS/short source, clock-loss/error bus messages, controlled recovery, obsolete activation rollback, old completion after new, real render failure/cancellation/retry, and native close during playback/render/transcription/chooser. Float PCM containers receive bounded finite-value preflight before opening a native sink; decoded/mixed PCM also has a finite-value guard. Diagnostics refuse to overwrite either input audio path or an existing report. Reusing the earlier wheel-report path produced the expected no-clobber error (`wheel-no-clobber.log`); final verification uses a fresh path (`verified-wheel-output.json`).

Earlier failures and corrections are retained rather than erased: EOS seqnum replacing a SEGMENT acknowledgement; paused Future completing before fresh position snapshot; optional-GI close trying to import GI again; Python GstController get_value virtual API failure; loop mixed-rate truncation; native PipeWire pool deadlock; reused PipeWire IDs causing a false cleanup failure; detached Matplotlib axes referenced after an edit. Final tests address these behaviors.

Not physically induced: server disconnection, unplugging Bluetooth, default-device rerouting, unsupported external codecs on another machine, or native plugin crashes/hangs outside the reproduced case. Native C calls cannot be forcibly interrupted by a Python Future timeout; if teardown remains unresolved the GUI retains leased files rather than deleting media still in use. Arbitrary native-library deadlock recovery is not guaranteed.

## J. Performance

CPU: 12th Gen Intel(R) Core(TM) i5-1235U; Linux-7.2.14-zen1-1-zen-x86_64-with-glibc2.44. Final fakesink and PipeWire harnesses ran sequentially after regression tests. One observation per state on a shared interactive host, not controlled repeated-run confidence intervals. Harness sampling overhead is included. CPU100%=one logical core, not entire machine. State windows1.2s idle/paused,2s vocal/mix. Muted branches continue decoding by design.

| State | fakesink CPU % | Native PipeWire CPU % | Native sampled RSS MiB |
|---|---:|---:|---:|
| Empty | 2.5 | 4.1 | 43.09 |
| Ready | 6.6 | 5.8 | 68.82 |
| Paused | 7.4 | 6.6 | 69.62 |
| Vocal playback | 16.4 | 15.4 | 69.56 |
| Combined mix | 16.4 | 16.5 | 69.59 |

Human33.212s vocal +34.712s piano (last stored note-off31.637s; Stage4A preserves full source duration before its1.5s tail): cold first-load 169.91ms; already-ready Play acknowledgement 2.74ms. Four playing seek acknowledgements 15.90–20.56ms. Query positions include playback advancing after target; these are software acknowledgements, not acoustic seek latency.

| Source duration | Warm-process native load ms | Seek ack ms | CPU % in measured interval |
|---|---:|---:|---:|
| 1s | 70.25 | 17.13 | 17.6 |
| 5s | 69.47 | 15.79 | 17.5 |
| 15s | 71.78 | 16.37 | 17.6 |
| 120s | 96.39 | 14.36 | 17.0 |

Native process kernel peak RSS 74.35MiB; largest render child peak 72.61MiB, separately measured (not simultaneous combined peak). Sampled /proc RSS can differ from kernel high-water accounting; raw figures are retained. Shutdown acknowledgement 8.83ms. Corresponding fakesink shutdown 8.68ms. SoundFont loading/inference belongs to background Stage4A rendering, not continuous playback. No Torch inference is used.

The1/5/15s sources played for0.5s each; the120s performance source played for3s and was then sought near its end. The separate synchronization experiment actually ran120s. Captured PCM ring, arrival log, bus history and waveform bins are bounded; normal playback retains no full decoded song. Two sources are limited to one hour each. Arbitrary-duration GUI memory endurance and many-hour device drift were not established.

![Playback performance](stage4b/performance.png)

Raw final observations: [fakesink](stage4b/release-performance-fakesink.json), [PipeWire](stage4b/release-performance-pipewiresink.json). Startup acknowledgement, buffer lookahead, output-server latency and SoundFont attack time are different quantities. Physical end-to-end latency remains unverified.

## K. Test results

| Category | Passed | Failed | Errors | Skipped | Elapsed |
|---|---:|---:|---:|---:|
| Full headless, installed neural + real synthesis | 189 | 0 | 0 | 7 | 76.47s |
| Native Wayland / PipeWire selection | 7 | 0 | 0 | 0 | 41.18s |

Headless skips are five display cases and two explicit-output cases (one display case also needs output). The seven native checks comprise five GTK cases (two new playback variants plus three existing GUI tests) and two non-GUI PipeWire cases. **All196 distinct collected tests passed across these complementary runs; no unresolved failed test.** Two expected headless mir_eval warnings concern zero-voiced metric fixtures. An earlier native run emitted one nonfatal GLib `g_error_free: assertion error != NULL failed` warning during the existing analysis/chooser test. The final native run emitted none; the intermittent framework-level cause is not established. Test XML/logs: `accepted-headless.*`, `accepted-native.*`.

Actual capture tests, real SoundFont renders and real server streams supplement deterministic unit tests. No mocks are presented as audio synchronization evidence. Optional assets are never downloaded by ordinary tests. Earlier failing development runs remain labeled in their logs and are not counted as final passing runs.

## L. Compatibility / packaging

All **581 pre-existing report artifacts** match the pre-edit SHA256 manifest. The original65-note human project, Stage4A release WAV/FLAC and original vocal identity also match earlier evidence. Existing Stage1–4A headless168 and native3 tests remain passing. Only prior source CLI, GUI, transcription workspace and package version were modified; acoustic estimation, segmentation, editable serialization, MIDI and synthesis modules retain their Stage4A hashes.

Fresh wheel module: `/tmp/vocalscope-stage4b-verified-wheel/vocalscope/__init__.py`; version0.5.0; SHA256 `5144be4e5df21c37238d0d60a1da80829a4e69abe3009edc0b8d8aaaee6d1066`. Installed-wheel YIN analyzed the human recording, its Stage4A renderer produced 65 current notes / 1,666,188 stereo frames at48000Hz, and shared-clock fakesink plus real auto/PipeWire diagnostics completed. GTK imported=False, Torch imported=False in headless verification. Package imports stay independent of optional playback/neural/synthesis runtimes.

Local wheel/sdist are in ignored `dist/`; no dataset, SoundFont, audio render or model checkpoint is bundled. The wheel was installed into a separate /tmp target and checked by its module path, using the existing tested scientific/system dependencies. It was not published. The note-project schema and permanent export semantics are unchanged. [Verification manifest](stage4b/verification.json) records hashes and scope.

## M. Reproduction

Run from the checkout, with existing locally licensed SoundFont/data; install system packages yourself:

```bash
sudo pacman -S --needed python python-pip python-gobject python-cairo gtk4 libadwaita libsndfile \
  gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire pipewire-pulse fluidsynth
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e '.[synthesis,playback]'
GDK_BACKEND=wayland vocalscope gui

vocalscope analyze vocal.wav --estimator pyin --output results/pitch
vocalscope transcribe vocal.wav --estimator pyin --output results/notes
vocalscope render-piano results/notes/vocal.notes.json --soundfont /path/to/piano.sf2 \
  --sample-rate 48000 --output results/piano
vocalscope playback-test --vocal vocal.wav --piano results/piano/piano.wav \
  --sink fakesink --seconds 1 --output results/playback.json
# Explicit short real output on the existing default device:
vocalscope playback-test --vocal vocal.wav --piano results/piano/piano.wav \
  --sink pipewiresink --seconds 1 --output results/output.json

python -m pytest tests --run-neural --soundfont data/soundfonts/TimGM6mb.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests -m 'gui or audio_output' --run-output \
  --soundfont data/soundfonts/TimGM6mb.sf2 -v
python scripts/stage4b_validation.py --long-real-time --output results/playback-sync.json
python scripts/stage4b_performance.py --sink fakesink --soundfont data/soundfonts/TimGM6mb.sf2 \
  --project results/stage3-human-pyin/vocadito_1.notes.json \
  --vocal data/vocadito/Audio/vocadito_1.wav \
  --piano results/stage4a-release-piano/piano.wav --output results/playback-performance.json
python -m build --no-isolation --outdir dist
```

Use `--sink pipewiresink` in the performance command for actual output. `playback-test --help` documents all diagnostic arguments; programmatic Transport exposes offsets/loops/revisions. Existing `benchmark` and `benchmark-notes` are preserved; their dataset reproduction remains in Stage2/3 reports. The validation font is TimGM6mb1.3 (5.97MB, GPL-2), bank0/preset0, as already verified in Stage4A. SoundFont and FluidSynth software licenses remain distinct; no download/install is implicit.

Upstream installation references: [Arch GStreamer](https://archlinux.org/packages/extra/x86_64/gstreamer/), [PipeWire plugin](https://archlinux.org/packages/extra/x86_64/gst-plugin-pipewire/), [good plugins / PulseAudio sink](https://archlinux.org/packages/extra/x86_64/gst-plugins-good/), [PyGObject](https://archlinux.org/packages/extra/x86_64/python-gobject/). Installed versions, not assumptions about newer repository versions, are recorded above.

## N. Limitations / acceptance scope

Functional Stage4B transport, comparison and edit audition have actual headless/native verification. Physical listening, hardware loopback/speaker latency, unplug/default-output recovery, broad manual accessibility QA, unsupported codecs/devices and many-hour endurance remain unverified. Native initialization workaround is measured on this plugin version, not guaranteed for every future version. Playback requires usable installed GStreamer elements; missing optional support produces actionable errors.

Loops can gap/click; swaps briefly pause and rebuild both decoders; muted-source lookahead delays gain changes. The instrumented GUI run observed event-loop gaps up to 0.71s in the observed test. Current peak is a buffer diagnostic, not a calibrated loudness meter; no limiter hides clipping. Preview revisions/transport preferences are session-only. Repeated-note/offset/glissando transcription errors remain the original Stage3 limitations. No synthesis/playback step repairs them.

## O. Stage 4C readiness

Available infrastructure: immutable acoustic truth, editable note projects/undo-redo, real offline synthesis, canonical source-aligned transport, audio comparison/mixing, bounded captured diagnostics, active-note/time views, race-safe revision/render/file ownership, measured switch/seek/loop/replacement behavior and packaging tests. Future work can evaluate explicit dynamics/articulation changes, compare performance against original vocals, improve gapless loops/seamless replacement and persist audition settings. No expressive reinterpretation was implemented here.
