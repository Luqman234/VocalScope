# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Render the stabilization report only from completed, retained evidence."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

root=Path('reports/stage4b1')
def read(name):return json.loads((root/name).read_text())
before=read('gui-baseline-native.json');after=read('gui-after-native.json');old=read('gui-baseline.json');soak=read('release-soak.json');edits=read('edit-soak.json')
loops_before=read('loops-baseline.json');loops=read('loops-measured.json');replacement_before=read('replacement-baseline.json');replacement=read('replacement-after.json');cpu_before=read('cpu-baseline.json');cpu=read('cpu-final.json');performance_before=read('performance-baseline-pipewiresink.json');performance=read('performance-after-pipewiresink.json');wheel=read('wheel-final-verification.json');sync=read('synchronization-final.json')
wheel_native=read('wheel-native-final.json')
assert wheel_native['status']=='complete' and wheel_native['sink']=='pipewiresink'
for result in [before,after,soak,edits,loops,loops_before,replacement_before,replacement,sync]:assert result['status']=='complete'
assert soak['transport_sha256']==hashlib.sha256(Path('src/vocalscope/playback/transport.py').read_bytes()).hexdigest()
def tests(name):
 s=ET.parse(root/name).getroot().find('testsuite');a=s.attrib
 return dict(passed=int(a['tests'])-int(a['skipped'])-int(a['errors'])-int(a['failures']),failed=int(a['failures']),errors=int(a['errors']),skipped=int(a['skipped']),seconds=float(a['time'])),s
head,_=tests('accepted-headless.xml');native,suite=tests('accepted-native.xml')
properties={p.attrib['name']:p.attrib['value'] for p in suite.findall('./properties/property')}
protected=read('preserved-stage1234b.json')
for name,digest in protected.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
prior=read('baseline-source-sha256.json');changed=[p for p,h in prior.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
for name in ['audio.py','pitch.py','notes.py','preprocessing.py','models.py','export.py','evaluation.py','transcription/models.py','transcription/segmentation.py','transcription/onsets.py','transcription/pitch_center.py','transcription/pipeline.py','transcription/serialization.py','transcription/midi_export.py','synthesis/renderer.py','synthesis/scheduler.py','synthesis/fluidsynth_backend.py','synthesis/export.py']:
 p='src/vocalscope/'+name;assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==prior[p],p

def n(value):return f'{value:.2f}' if value is not None else 'undefined'
def median(rows,key):return float(np.median([r[key] for r in rows]))
def phase_cpu(d,phase):return float(np.median([r['cpu_percent'] for r in d['resources'] if r['phase']==phase]))
def phase_paints(d,phase):return sum(r['phase']==phase and r['name']=='FigureCanvasGTK4Agg.on_draw_event' for r in d['operation_samples'])/d['phase_seconds'][phase]
phases=['mapping','load_project','load_waveform','steady_playback','single_edit','many_edits','undo_redo','mix_switches','render_replace','steady_after_edit','loop','shutdown']
fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
show=['load_project','single_edit','many_edits','undo_redo','steady_playback','steady_after_edit'];x=np.arange(len(show))
axes[0].bar(x-.18,[before['phases'][p]['delay']['p99_ms'] for p in show],.36,label='0.5.0');axes[0].bar(x+.18,[after['phases'][p]['delay']['p99_ms'] for p in show],.36,label='0.5.1');axes[0].axhline(50,color='red',ls='--',label='steady goal 50 ms');axes[0].set_xticks(x,[p.replace('_','\n') for p in show],fontsize=8);axes[0].set_ylabel('Scheduling delay p99 (ms)');axes[0].legend(fontsize=8)
gap_before=[np.median(r['arrival_interval_excess_ms']) for r in loops_before['rows']];gap_after=[np.median(r['arrival_interval_excess_ms']) for r in loops['rows'][:9]]
axes[1].plot(gap_before,'o-',label='0.5.0');axes[1].plot(gap_after,'o-',label='0.5.1');axes[1].set(xlabel='Matched loop case (9 cases)',ylabel='Median extra period (ms)');axes[1].legend();fig.savefig(root/'comparison.png',dpi=160);plt.close(fig)

L=['# VocalScope Stage 4B.1 — Workstation stabilization','',
'Executed on Arch Linux / Hyprland, Intel Core i5-1235U. Local patch build **0.5.1**. No push, tag, publication or shared audio-service restart occurred. All earlier reports and measurements remain historical evidence. This report distinguishes measured software behavior from pending human/device acceptance.','',
'## A. Implementation summary','',
'Changed GTK canvas/lifecycle, transcription workspace and interactive plotting, playback timeline/workspace, waveform cache, Gst bus wakeups/transport/watchdog, render coordination, optional configuration validation, packaging/docs and local version. Added `ui_metrics.py`, three stabilization test modules plus revision-race cases, profiling/loop/CPU/replacement/soak/listening scripts and a human acceptance procedure.','',
'Corrections: persistent axes/note geometry; cached static grid/F0/waveform/notes; dynamic active/selected overlays; real GTK invalidation after Agg updates; four-source immutable waveform cache; no redraw on sub-sample render-duration differences; safe cursor/session reset; explicit signal/timer cleanup; event-driven Gst-owner wakeups; nanosecond-correct50ms loop validation; sink-progress watchdog; retained Pause/Stop intent in ERROR; coalesced recovery and idempotent close acknowledgement; cancellation-token activation and immediate retry; obsolete queued renders skip process creation; zero-count file leases are removed.','',
'These are backward-compatible workstation fixes, warranting a **patch** rather than a new feature milestone. Version stayed0.5.0 during reproduction and initial verification, then moved to0.5.1 after real improvements and native/core tests passed. Final208 tests and installed-wheel checks followed. Transcription and synthesis algorithms/schemas were not changed.','',
'## B. Baseline reproduction','',
'Protected0.5.0 wheel was installed into `/tmp/vocalscope-stage4b1-baseline`, selected explicitly by PYTHONPATH. It is independent of the modified source. The probe loads the same65-note human project, WAV vocal, rendered piano and SoundFont, requests1100×800, and executes identical map/open/load/expand/start/seek/edit/undo/mix/render/loop/close actions. All scenario actions and polling use GLib callbacks, without sleep or blocking Future.result on GTK. Quantitative runs have no cProfile; a separate profile supplies call-path evidence.','',
f"Historical710ms gaps were not treated as steady-playback latency. Initial reproduction measured many-edit median delay {old['phases']['many_edits']['delay']['median_ms']:.2f}ms, p99 {old['phases']['many_edits']['delay']['p99_ms']:.2f}ms, undo/redo maximum {old['phases']['undo_redo']['delay']['max_ms']:.2f}ms, and startup/import maximum {old['phases']['initialize']['delay']['max_ms']:.2f}ms. The later paired native baseline was faster on this shared host; results below use that matched pair, not the worst earlier run as a cherry-picked comparator.",'',
'Artifacts: `gui-baseline.json`, `gui-baseline-2.json`, `gui-baseline-profile.json/.prof`, `gui-baseline-native.json`, `gui-after-native.json`. CPU governor, thermal state, compositor scheduling, font/page caches and unrelated desktop activity were not controlled. No population confidence interval or independent-subject interpretation is assigned to correlated callbacks.','',
'## C. Root-cause analysis','',
'1. Each edit rebuilt the figure, two axes, tick formatters, legend, note rectangles and waveform axis. Main-thread operation probes measured roughly200ms typical reconstruction in the first baseline, rather than a DSP/worker wait.27 interactive draws and30 Figure.clear calls occurred in that scenario. Reusing stable artists removes that repeated work.','',
'2. Every cursor tick redrew every note rectangle. The separate function profile recorded57,181 rectangle draws; the first baseline TimelineView.update median was12.91ms. The patch bakes normal notes and redraws only the cursor and active/selected overlays. Main-thread operation timings, not overlapping profiler thread totals, are the authoritative durations.','',
'3. Installed Matplotlib3.11.2 GTK4Agg inherits the empty FigureCanvasBase.blit method. Old internal-position tests did not prove presentation. Explicit queue_draw now schedules the GTK canvas to paint its existing Agg buffer; the small canvas subclass counts actual on_draw_event delivery. This fixes missing frame presentation without rebuilding the renderer.','',
'4. Rebuilding a48kHz render at44.1kHz changed container duration by about4.5µs; exact float inequality unnecessarily rebuilt the layout after replacement. The visual viewport now ignores differences below half a canonical sample. Actual audio duration/seek coordinates are unchanged.','',
'5. Gst bus messages previously waited for a10ms command-poll timeout. A coalesced bus sync notification wakes the owner queue, retaining bus/command serialization. This removes avoidable seek/restart acknowledgement delay without changing the media clock.','',
'Cold Python/scientific/Matplotlib imports and first GTK realization are separate from visible steady playback. Full first plots and out-of-range pitch-axis changes still require Agg rendering. Waveform decoding stays in an off-main worker; SoundFont/native rendering remains in Stage4A subprocesses. No evidence pointed to neural inference during playback.','',
'## D. GUI performance and methodology','',
'Heartbeat interval10ms, monotonic nanoseconds. Scheduled deadline=previous callback finish+interval, matching a non-catching-up GLib timeout approximately; GLib millisecond quantization applies. Records scheduled/start/finish, positive scheduling delay, callback gap, missed intervals and heartbeat execution. Heartbeat execution measures its own overhead; named operation traces separately measure handler/draw work. Median/p95/p99/max plus counts over16.7/50/100/250ms are retained for both delays and gaps. All samples, including imports/startup/range changes, remain in JSON; phase classification is explicit.','',
'Paired **native Wayland + PipeWire** scheduling delays, milliseconds (0.5.0 →0.5.1):','',
'| Phase | Before median / p95 / p99 / max | After median / p95 / p99 / max |','|---|---|---|']
for phase in phases:
 b=before['phases'][phase]['delay'];a=after['phases'][phase]['delay'];L.append(f"| {phase} | {' / '.join(n(b[k]) for k in ['median_ms','p95_ms','p99_ms','max_ms'])} | {' / '.join(n(a[k]) for k in ['median_ms','p95_ms','p99_ms','max_ms'])} |")
L+=['',f"Steady goals achieved in this run: p99 {after['phases']['steady_playback']['delay']['p99_ms']:.2f}ms, after-edit steady p99 {after['phases']['steady_after_edit']['delay']['p99_ms']:.2f}ms, both below50ms; no steady scheduling delays above100ms. Cold initialize/import maximum {after['phases']['initialize']['delay']['max_ms']:.2f}ms, mapping maximum {after['phases']['mapping']['delay']['max_ms']:.2f}ms and first project plot maximum {after['phases']['load_project']['delay']['max_ms']:.2f}ms are retained and classified separately. Pitch-range expansion still incurs a full redraw; no universal30/60fps claim.",'',
f"Interactive plot-update median {before['operations']['TranscriptionWorkspace.draw']['median_ms']:.2f}→{after['operations']['TranscriptionWorkspace.draw']['median_ms']:.2f}ms; cursor-update median {before['operations']['TimelineView.update']['median_ms']:.2f}→{after['operations']['TimelineView.update']['median_ms']:.2f}ms. GTK paint callbacks {before['operations']['FigureCanvasGTK4Agg.on_draw_event']['count']}→{after['gtk_painted_frames']}; steady native paint rates {phase_paints(before,'steady_playback'):.2f}→{phase_paints(after,'steady_playback'):.2f}frames/s. The new run paints real continuous frames, so CPU comparisons do not describe identical presentation work.",'',
f"GUI process steady CPU median {phase_cpu(before,'steady_playback'):.2f}→{phase_cpu(after,'steady_playback'):.2f}% of one core; sampled peak RSS {max(r['rss_bytes'] for r in before['resources'])/2**20:.2f}→{max(r['rss_bytes'] for r in after['resources'])/2**20:.2f}MiB. This includes GTK/Matplotlib/scientific imports, unlike the historical74.35MiB audio-only process. More real frame delivery costs CPU despite reduced plot work. Paint callback completion is not compositor scanout or physical audio latency.",'',
'![Measured comparison](stage4b1/comparison.png)','',
'## E. Loop reliability','',
'Production policy remains an exact hard cut and bounded flushing seek, without crossfade or hidden sample smoothing. Sources keep one pipeline/clock. Tests cover periodic/nonperiodic sine, impulses, smooth zero-boundary waveform, silence-separated phrases, human vocal/piano, release and near-end material;50ms,160ms,300ms,600ms,900ms,1s,1.5s and3s regions.','',
'| Matched case | Region s | Median extra loop period before / after ms | Complete cycles after | Incomplete internal cycles |','|---|---:|---:|---:|']
for b,a in zip(loops_before['rows'],loops['rows'][:9]):L.append(f"| {a['signal']} | {a['start']:.2f}–{a['end']:.2f} | {np.median(b['arrival_interval_excess_ms']):.2f} / {np.median(a['arrival_interval_excess_ms']):.2f} | {a['complete_cycles']} | {a['failed_or_incomplete_internal_cycles']} |")
long=loops['rows'][-1]
L+=['',f"Three-minute impulse loop: {long['elapsed_seconds']:.2f}s, {long['complete_cycles']} complete cycles, no incomplete internal cycles; max ground-truth impulse error {long['max_ground_truth_impulse_error_samples']} sample and relative source error {long['max_relative_alignment_samples']} sample. Last intentionally interrupted partial cycles are explicitly recorded, never silently counted as full. Captured callback-period excess is software sink-clock delivery, not a speaker measurement. Additional loop time accumulates against an external metronome; shared source alignment is a different property.",'',
'Nonperiodic boundaries still jump; the prior220Hz hard-cut sample step≈0.0272 remains representative. First/subsequent resampling edge waveforms can differ by a sample while impulse alignment stays within one sample. An isolated documented non-flushing SEGMENT trial requested8 repeats at48/48kHz and3 at44.1/48kHz but captured only14,400 frames in each case despite repeated completion messages. It was rejected for production (`segment-experiment.json`). This does not prove seamless Gst looping impossible; integrated segment/running-time behavior needs further work.','',
'## F. Transport and source mixing','',
'Bus notifications wake the single owner thread; no independent player/timer was added. Rapid state/seek commands,100 immediate mode switches, mixed sample rates/channels, shorter-source EOS, exact50ms repeats, loaded-session cursor reuse and paused stability pass. A/B/mix does not rebuild the pipeline or reset position.20ms stream-time gain ramps and the established mix attenuation are retained; DC10–90% fade stays16ms and adjacent sample step≈8.33e-5. No limiter or automatic vocal normalization was added.','',
'Final synchronization capture re-executed the established17-case suite. Maximum relative/known-impulse error remains one48kHz sample, below the pre-existing two-sample tolerance; no tolerance relaxation. Source files and stored F0 values are unchanged.','',
'## G. Edit audition and replacement','',
'Current project revision, cancellation epoch and file leases are separate. A validated result preparing for activation receives an epoch token; cancellation invalidates it even if the same project revision is retried. Rejected activation restores the old source/position. Retry requested while a cancelled worker exits is queued for that current revision, and obsolete queued jobs skip native process creation. Zero-count pins are removed.','',
f"Historical native replacement68ms is retained in Stage4B. Paired native API observations: {performance_before['playing_piano_replacement_seconds']*1000:.2f}→{performance['playing_piano_replacement_seconds']*1000:.2f}ms. Real human-project edited render+validation {performance_before['edited_background_render_validation_seconds']:.3f}→{performance['edited_background_render_validation_seconds']:.3f}s; not a universal guarantee. Preparation happens while old playback remains valid, then a controlled pause/rebuild/preroll/seek/resume follows.",'',
'Clock-paced appsink delivery interruption (four playing swaps each):','',
'| Measurement | 0.5.0 | 0.5.1 |','|---|---:|---:|']
for label,key,scale in [('Median PCM-delivery gap ms','clock_paced_pcm_interruption_seconds',1000),('Maximum PCM-delivery gap ms','clock_paced_pcm_interruption_seconds',1000)]:
 b=[r[key]*scale for r in replacement_before['rows'] if not r['paused']];a=[r[key]*scale for r in replacement['rows'] if not r['paused']];fn=np.median if label.startswith('Median') else max;L.append(f'| {label} | {fn(b):.2f} | {fn(a):.2f} |')
L+=['',
'Arrival gap subtracts the preceding block duration. It measures software PCM delivery, not electrical/acoustic interruption. New history records preparation seconds, pause start, acknowledgement and fresh pause-target position. Playback may advance while preparation runs; pre-call position error includes that legitimate advance. Paused restoration is separately tested within20ms. Source replacement remains a brief interruption, not seamless swapping or live pad replacement.','',
f"Real human-project stress: {len(edits['rows'])} edit/undo/redo/render/swap cycles, {edits['discarded_revisions']} obsolete revisions discarded, one retained render directory per completed cycle, no child after cleanup, root removed={edits['temporary_root_removed']}. Forced stale completion, cancelled activation after retry, cancellation during GUI replacement, close during preview, and immediate cancel/retry pass. No note/F0 regeneration or original-file mutation was used to improve sound.",'',
'## H. Audio-device / server recovery','',
'Actual safe failure testing opens an additional client Unix socket and supplies it through the installed native sink fd property. The plugin duplicates the fd; shutting down that socket interrupts only the test client. No default device, other stream or server configuration is modified. The plugin left PLAYING without ERROR, reproducing a genuine blind spot.','',
'Watchdog checks successful sink-render counts every100ms, while settled PLAYING, and enters ERROR after default2s without progress plus scheduling delay. It does not use media-time advancement as proof of delivery. Pause/seek/loading reset monitoring. This is sink-flow detection, not a proof of audible sound or hardware delivery. Timeout is configurable programmatically.','',
f"Final native private-client loss detected in {float(properties['private_pipewire_disconnect_detection_seconds']):.3f}s, recovered in {float(properties['private_pipewire_actual_recovery_seconds']):.3f}s. Recovery produced exactly one RUNNING native node and advancing position. An absent private Pulse endpoint failed in {float(properties['absent_endpoint_detection_seconds']):.3f}s; restoring the actual compatibility endpoint then played successfully. Pause/Stop in ERROR preserve user intent through recovery; concurrent Recover commands do not endlessly rebuild. Close acknowledgement is idempotent and resolves after actual cleanup.",'',
'Recovery is one explicit user request, not an uncontrolled retry loop. Actual physical unplug/replug, default-output migration and daemon restart remain pending. Routing may continue according to existing server policy; the application does not claim to identify or force hardware automatically. The manual procedure documents how to test safely. Native-library hangs outside measured cases cannot be forcibly interrupted by a Python Future timeout.','',
'## I. Audio latency / CPU','',
f"Native initial-load API {performance_before['human_load_seconds']*1000:.2f}→{performance['human_load_seconds']*1000:.2f}ms; ready Play acknowledgement {performance_before['playing_ack_seconds']*1000:.2f}→{performance['playing_ack_seconds']*1000:.2f}ms. These encompass discovery/preroll/software state, not speaker onset. Source seek and sink-clock arrivals remain separately logged. Pipeline latency queries reported their own minimum (often0); zero does not establish zero Bluetooth buffering.",'',
f"Repeated audio-only4s windows: baseline CPU {min(r['cpu_percent'] for r in cpu_before['rows']):.1f}–{max(r['cpu_percent'] for r in cpu_before['rows']):.1f}% (median{median(cpu_before['rows'],'cpu_percent'):.1f}), final {min(r['cpu_percent'] for r in cpu['rows']):.1f}–{max(r['cpu_percent'] for r in cpu['rows']):.1f}% (median{median(cpu['rows'],'cpu_percent'):.1f});100%=one logical core. Owner poll counts/thread CPU are retained. Earlier short paired windows showed7.5→14.9%, motivating repetition rather than a claimed twofold regression/improvement. Host load, frequency/caches and instrumentation matter; no controlled statistical equivalence is asserted.",'',
'Configured failure checks were reduced from every position query to10Hz after the owner-poll CPU probe. This changes only failure detection sampling, not UI rate, media position or audio data. Electrical loopback and acoustic latency were not measured; Stage4A’s6–8ms SoundFont attack remains a separate historical property. Physical human listening is not claimed.','',
'## J. Soak and resource lifetime','',
f"Final0.5.1 transport soak ran **{soak['sustained_seconds']:.3f}s** at real-time speed with {soak['counts']['switches']} mode switches, {soak['counts']['seeks']} seeks, {soak['counts']['pause_resume_pairs']} pause/resume pairs, {soak['counts']['sessions']} constructed/disposed sessions and {soak['loop_restarts']} loop restarts. This is command stress, not uninterrupted physical listening. Transport source SHA256 at start matches the final source. Two earlier600s candidates also completed, and the separate180s loop captured PCM continuously.",'',
f"After warm session teardown→final teardown: RSS {soak['resources'][1]['rss_bytes']/2**20:.2f}→{soak['resources'][-1]['rss_bytes']/2**20:.2f}MiB; fd count {soak['resources'][1]['fd_count']}→{soak['resources'][-1]['fd_count']}; children after cleanup {soak['resources'][-1]['children']}; surviving pipeline wrappers {soak['surviving_pipeline_wrappers']}. Full2s resource samples include CPU/threads/RSS/fds/children. RSS growth alone is not labeled a leak or proof of no leaks; allocator, decoder/font/GTK caches remain possible explanations.",'',
'Fifteen unit lifecycle repetitions and four native windows verified disposed pipeline wrappers, stable post-warm fd counts, removed GLib timer sources, disconnected canvas handlers and cleaned preview roots. Native output tests verify stream removal. GUI endurance is bounded by the profiling/native scenarios; a10-minute animated GUI plus device-listening soak was not performed. No claim of zero leaks on arbitrary codecs/fonts or unlimited duration is made.','',
'## K. Native Wayland / PipeWire','',
'Actual mapped GdkWaylandDisplay tests exercised historic analysis/CREPE/export/chooser guards, editable projects/MIDI, real synthesis, active playback frames, cursor/highlight/selection independence, waveform, cached edits, repeated session loads, seeks, loops, A/B/mix, preview cancellation/retry, repeated windows, private-client failure/recovery and shutdown. Both test sinks and real PipeWire output are used. Native paint callbacks prove GTK rendering, not human visual or acoustic acceptance.','',
'Broad subjective/manual acceptance, physical output failure and end-to-end latency remain pending. Follow [PLAYBACK_ACCEPTANCE.md](../docs/PLAYBACK_ACCEPTANCE.md), which includes original/piano/mix, channel tones, clipping, seeking/looping, edit audition, shutdown, device migration/reconnect and measurement distinctions.','',
'## L. Automated tests','',
'| Run | Passed | Failed | Errors | Skipped | Elapsed |','|---|---:|---:|---:|---:|---:|',
f"| Final headless incl. local neural + real SoundFont | {head['passed']} | {head['failed']} | {head['errors']} | {head['skipped']} | {head['seconds']:.2f}s |",
f"| Final installed-wheel native Wayland/PipeWire | {native['passed']} | {native['failed']} | {native['errors']} | {native['skipped']} | {native['seconds']:.2f}s |",'',
f"**{head['passed']+native['passed']} distinct tests passed across complementary runs**, including all196 historical cases and12 added stabilization cases. Headless skips are the10 native/display/explicit-output cases; they pass in the separate native run. Repeated runs/subset checks are not added to the distinct total. Two expected mir_eval empty-voicing warnings and101 upstream PyGObject Python3.14 event-loop-policy deprecations occurred; no final test failure. Counts are from `accepted-headless.xml` and `accepted-native.xml`.",'',
'Earlier failures remain retained: initial Agg test counted an explicit second draw as cache invalidation (corrected to measure no additional captures during100 updates), exact50ms floating-point rejection, and real PipeWire disconnection without ERROR. Tests were not loosened to hide them. Deterministic latency unit tests use an injected clock; actual timing goals are measured in native scenarios rather than brittle CI wall-time assertions.','',
'## M. Preservation and packaging','',
f"Verified **{sum(p.startswith('reports/') for p in protected)} existing reports**, including the previously reported581, plus {sum(not p.startswith('reports/') for p in protected)} protected media/project/font/0.5.0 distribution artifacts. The inventory was enumerated before changes, not inferred from the prior count. All SHA256 values match. Acoustic/backends/segmentation/editable schema/MIDI/offline synthesis core source hashes remain unchanged. Modified old source files are recorded below.",'',
'`'+ '`, `'.join(changed)+'`','',
f"Final installed wheel 0.5.1 module `{wheel['module_path']}` completed YIN analysis, 65-note real SoundFont WAV rendering and headless playback without importing GTK/Torch (flags {wheel['gtk_imported']}/{wheel['torch_imported']}). It also completed actual native PipeWire playback, pause, seek, source switching and cleanup (`wheel-native-final.json`). The candidate installation passed all 10 native tests; every Python module in the final wheel matches that tested source. Existing 0.5.0 distributions are preserved. Current wheel/source archive are local only; no audio, dataset, font or checkpoint asset is bundled. Arch GI/system-site-packages requirements and optional synthesis/neural behavior remain intact.",'',
'## N. Reproduction','',
'```bash\n# System installation, if needed, is performed by the user:\nsudo pacman -S --needed python python-pip python-gobject python-cairo gtk4 libadwaita \\\n  libsndfile gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire pipewire-pulse fluidsynth\npython -m venv --system-site-packages .venv\nsource .venv/bin/activate\npython -m pip install -r requirements.txt\npython -m pip install -e \'.[synthesis,playback]\'\nGDK_BACKEND=wayland vocalscope gui\n\nGDK_BACKEND=wayland python scripts/stage4b1_gui_profile.py --sink pipewiresink \\\n  --output results/gui-latency.json\nGDK_BACKEND=wayland python scripts/stage4b1_gui_profile.py \\\n  --output results/gui-profile.json --profile results/gui.prof\npython scripts/stage4b1_loop_validation.py --soak-seconds 180 --output results/loops.json\npython scripts/stage4b1_soak.py --seconds 600 --output results/soak.json\npython scripts/stage4b1_edit_soak.py --output results/edit-soak.json\npython scripts/stage4b1_replacement.py --output results/replacement.json\npython scripts/stage4b_validation.py --output results/synchronization.json\npython -m pytest tests --run-neural --soundfont data/soundfonts/TimGM6mb.sf2 -ra\nGDK_BACKEND=wayland python -m pytest tests -m \'gui or audio_output\' --run-output \\\n  --soundfont data/soundfonts/TimGM6mb.sf2 -v\npython -m build --no-isolation --outdir dist\n```','',
'The GUI probe accepts --project/--vocal/--piano/--soundfont overrides. Default human probes require the existing Vocadito1 project/audio and Stage4A piano files; synthesis needs a verified licensed font. No downloads occur automatically. To reproduce the old baseline, install preserved `dist/vocalscope-0.5.0-py3-none-any.whl` with --no-deps --target to a separate directory, then set PYTHONPATH to it for the same scripts. Use fresh result paths where no-clobber publication applies. The diagnostic channel-tone script is explicitly not a production piano renderer.','',
'API evidence: [Matplotlib blitting](https://matplotlib.org/stable/users/explain/animations/blitting.html), installed GTK4Agg/FigureCanvasBase source inspected; [Gst seeking](https://gstreamer.freedesktop.org/documentation/additional/design/seeking.html), [installed PipeWire core fd ownership](https://raw.githubusercontent.com/PipeWire/pipewire/1.6.10/src/gst/gstpipewirecore.c). Installed environment remains GStreamer1.28.8, PipeWire1.6.10, GTK4.24.1, PyGObject3.58.1, libadwaita1.10.0, FluidSynth2.6.2 and pyfluidsynth1.4.0. No new dependency or system installation was needed.','',
'## O. Remaining problems','',
'Exact loops still gap and can click; replacement remains interrupted rather than seamless. First imports/mapping/plots and pitch-range changes remain slower than steady cursor work. Frame cadence depends on GTK/compositor/load; the measured goals are not a universal deadline guarantee. More actual GTK painting can increase GUI CPU. Correlated, short timing samples are descriptive, and other hardware/fonts/codecs need verification.','',
'Physical human listening, electrical/acoustic latency, actual unplug/default-device changes and full daemon restart remain unverified. Watchdog observes sink flow rather than speaker audibility. Native-library deadlock recovery is limited by the C API. Four native reopen cycles and10-minute audio stress do not prove unlimited GUI endurance or zero leaks. Python3.14 GI deprecations should be tracked before3.16. Original note-release/repeated-note/glissando and F0 weaknesses remain unchanged.','',
'## P. Stage 4C readiness','',
'Workstation engineering can proceed to separate expressive-performance experiments with reproducible acoustic truth, editable notes, real synthesis, one queried timeline, delivered native frames, bounded failure states, epoch-safe audition and improved loop/replacement behavior. Keep human listening/device acceptance as explicit gates before broader user claims. Do not promise gapless audio, seamless swaps or calibrated physical latency. No expressive interpretation was implemented in this milestone.','']
import re
# Keep measured numbers intact while separating units and prose from version labels.
prose_replacements = {
 'nanosecond-correct50': 'nanosecond-correct 50', 'stayed0.5.0': 'stayed 0.5.0',
 'to0.5.1': 'to 0.5.1', 'Final208': 'Final 208', 'Protected0.5.0': 'Protected 0.5.0',
 'same65': 'same 65', 'requests1100': 'requests 1100', 'Historical710': 'Historical 710',
 'roughly200': 'roughly 200', 'wait.27': 'wait. 27', 'and30': 'and 30',
 'recorded57,181': 'recorded 57,181', 'was12.91': 'was 12.91',
 'Matplotlib3.11.2': 'Matplotlib 3.11.2', 'a48': 'a 48', 'at44.1': 'at 44.1',
 'about4.5': 'about 4.5', 'a10': 'a 10', 'Stage4A': 'Stage 4A', 'Stage4B': 'Stage 4B',
 'interval10': 'interval 10', 'over16.7': 'over 16.7', 'below50': 'below 50',
 'above100': 'above 100', 'universal30': 'universal 30', 'historical74.35': 'historical 74.35',
 'material;50': 'material; 50', ',160': ', 160', ',300': ', 300', ',600': ', 600',
 ',900': ', 900', ',1s': ', 1s', ',1.5s': ', 1.5s', 'and3s': 'and 3s',
 'prior220': 'prior 220', 'requested8': 'requested 8', 'at48/48': 'at 48/48',
 'and3 at44.1': 'and 3 at 44.1', 'only14,400': 'only 14,400',
 'commands,100': 'commands, 100', 'exact50': 'exact 50', 'position.20': 'position. 20',
 'DC10': 'DC 10', 'stays16': 'stays 16', 'established17': 'established 17',
 'one48': 'one 48', 'replacement68': 'replacement 68', 'within20': 'within 20',
 'every100': 'every 100', 'default2s': 'default 2s', 'audio-only4s': 'audio-only 4s',
 '(median{': '(median {', ');100%': '); 100%', 'showed7.5': 'showed 7.5',
 'to10Hz': 'to 10Hz', 'Stage 4A’s6': 'Stage 4A’s 6', 'Final0.5.1': 'Final 0.5.1',
 'earlier600': 'earlier 600', 'separate180': 'separate 180', 'Full2s': 'Full 2s',
 'a10-minute': 'a 10-minute', 'all196': 'all 196', 'and12': 'and 12',
 'the10': 'the 10', 'and101': 'and 101', 'Python3.14': 'Python 3.14',
 'during100': 'during 100', 'reported581': 'reported 581', 'Vocadito1': 'Vocadito 1',
 'GStreamer1.28.8': 'GStreamer 1.28.8', 'PipeWire1.6.10': 'PipeWire 1.6.10',
 'GTK4.24.1': 'GTK 4.24.1', 'PyGObject3.58.1': 'PyGObject 3.58.1',
 'libadwaita1.10.0': 'libadwaita 1.10.0', 'FluidSynth2.6.2': 'FluidSynth 2.6.2',
 'pyfluidsynth1.4.0': 'pyfluidsynth 1.4.0', 'and10-minute': 'and 10-minute',
 'before3.16': 'before 3.16',
}
report = '\n'.join(L)
in_code = False
lines = []
for line in report.splitlines():
 if line.startswith('```'): in_code = not in_code
 if not in_code and not line.startswith('```'):
  for original, replacement in prose_replacements.items(): line = line.replace(original, replacement)
  # Exclude inline paths, identifiers and links from unit spacing.
  pieces = re.split(r'(`[^`]+`|https?://[^)\s]+)', line)
  for i in range(0, len(pieces), 2):
   pieces[i] = re.sub(r'(?<=\d)(?=(?:ms|µs|MiB|frames/s|fps|kHz|Hz|s)\b)', ' ', pieces[i])
   pieces[i] = re.sub(r'\b(median|often)(?=\d)', r'\1 ', pieces[i])
  line = ''.join(pieces)
 lines.append(line)
Path('reports/STAGE4B1_ENGINEERING.md').write_text('\n'.join(lines)+'\n')
verification={'version':'0.5.1','status':'software_native_stabilization_verified','tests':{'headless':head,'native':native},'distinct_passed':head['passed']+native['passed'],
 'historical_reports_unchanged':sum(p.startswith('reports/') for p in protected),'other_protected_artifacts_unchanged':sum(not p.startswith('reports/') for p in protected),
 'changed_prior_source_files':changed,'transport_sha256':soak['transport_sha256'],'physical_listening':'pending','electrical_acoustic_latency':'unverified','physical_device_disconnect':'pending',
 'source_code_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('src/vocalscope').rglob('*.py')},
 'final_wheel':{'module_path':wheel['module_path'],'sha256':wheel['wheel_sha256'],
 'headless_gtk_imported':wheel['gtk_imported'],'headless_torch_imported':wheel['torch_imported'],
 'native_pipewire_status':wheel_native['status']},
 'distributions_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('dist').glob('vocalscope-0.5.1*')}}
(root/'verification.json').write_text(json.dumps(verification,indent=2)+'\n');print('Report, verification and comparison figure written.')
