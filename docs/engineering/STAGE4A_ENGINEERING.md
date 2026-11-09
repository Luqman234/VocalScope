> Historical engineering evidence. Local paths were redacted for public distribution.
> Raw logs, datasets and media are retained locally and are not bundled.

# VocalScope Stage 4A — Engineering report

Executed on 9 November 2026, Asia/Kuala_Lumpur. Release 0.4.0, renderer/sidecar schema 1.0.0. Real SoundFont synthesis, decoded output, native GUI operation and CPU measurements were executed; no mocked renderer is presented as synthesis evidence.

## A. Implementation

Added `synthesis/models.py`, `soundfont.py`, `scheduler.py`, `fluidsynth_backend.py`, `renderer.py`, `diagnostics.py`, `export.py`, `project.py`, `process.py` and `workspace.py`. Extended CLI, existing worker dispatch, transcription workspace and optional packaging. Added synthesis/core and native GUI tests, explicit validation-font fetch, acoustic/performance/plot/report scripts, README instructions and new Stage 4A evidence. No Stage 4B playback or Stage 4C expressive interpretation was implemented.

The package version stayed 0.3.0 during implementation. It moved to 0.4.0 only after actual synthesis, initial regression tests, all three native Wayland tests and a separately installed candidate wheel passed. Final release wheel verification is retained separately. No pushes, tags, publishing or system-wide installations occurred.

## B. Synthesis architecture

Stage 3 validated CURRENT NoteEvents -> sample schedule -> owned FluidSynth synth -> stereo float32 blocks -> disk float spool -> WAV/FLAC encoding -> independent decoder checks -> no-clobber publication, JSON last. No MIDI-file tick round-trip is inserted, so original note timestamps are rounded directly to the requested PCM grid. Note pitches, velocities, offsets and edits are not regenerated or altered.

`render_notes` returns a bounded read-only PCM array plus structured report; `stream_notes` and production export use fixed-size blocks. RenderConfig validates rate/gain/effects/preset/resource bounds. Schedule supports simultaneous/overlapping different notes and isolates overlapping instances of the same key on different melodic channels (channel9 excluded). More than15 concurrent instances of one key fail explicitly. Note-offs precede note-ons at a shared sample; ties otherwise follow stable note IDs. Notes collapsing to zero samples fail rather than shift or leave an active note.

pyfluidsynth provides settings, synth/font/preset/event/lifecycle bindings. Its convenience get_samples is int16, so a small isolated ctypes extension uses documented fluid_synth_write_float against the same native library, plus interpolation/buffer/version/driver registration functions. No audio driver, MIDI driver, player, wall-clock timer or sleep is used. Live driver registration is disabled once before this offline backend creates settings, avoiding unnecessary ALSA/SDL device probing. The backend owns FluidSynth instances in its process and serializes access; it is not designed to share its registry with an unrelated live FluidSynth application in the same process.

Production CLI/GTK uses an owned worker subprocess for native parsing/rendering. Parent-owned staging survives child crashes long enough for the coordinator to clean it after wait/termination. Native handles close in success/error/cooperative-cancellation paths; process teardown reclaims terminated-child resources. All sounding voices are stopped on cooperative cleanup. GTK changes remain on its main loop. The child returns metadata and staged paths, not a whole PCM array over JSON. The parent validates response paths and publishes only complete verified output.

## C. Environment, SoundFont and licenses

Installed native FluidSynth **2.6.2** (Arch package fluidsynth2.6.2-1); Python pyfluidsynth **1.4.0** was installed only into the existing venv. Python/package/library environment is retained in environment.json. CPU-only; no GPU requirement. FluidSynth was already installed; no system package manager mutation was performed.

Validation SoundFont: **TimGM6mb 1.3**, 5,969,788 bytes, bank0/preset0, actual name **Piano 1**. SHA256 `c5378b62028c920cb11e4803327983fee2f2cdff5dc89c708e39da417e51c854`. Local path `data/soundfonts/TimGM6mb.sf2` is ignored data, not bundled with the application. [Debian source archive](https://deb.debian.org/debian/pool/main/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3.orig.tar.gz), archive SHA256 `af8f3a00e416dfb262bcaa904a1c84df04a51b72bbc1313aed012bc754bdf99b`. [Debian copyright metadata](https://metadata.ftp-master.debian.org/changelogs/main/t/timgm6mb-soundfont/timgm6mb-soundfont_1.3-5_copyright) identifies Tim Brechbill (2004), David Bolton (2010), and GPL-2 for the samples. Archive checksum and license were checked before acquisition; independent uploader OpenPGP signature validation is not claimed.

[FluidSynth software](https://archlinux.org/packages/extra/x86_64/fluidsynth/) is LGPL-2.1-or-later, independently of sample licensing. [Arch soundfont-fluid](https://archlinux.org/packages/extra/any/soundfont-fluid/) is a larger FluidR3 font under custom MIT, with `/usr/share/soundfonts/FluidR3_GM.sf2`. It is documented for user installation, but was not installed or benchmarked here. Output/redistribution permissions depend on the selected font; no universal royalty-free claim is made.

Font search order: explicit argument, small XDG application settings JSON, then known system fonts. Invalid explicit/configured choices do not silently fall back. RIFF/sfbk structure, file type/size/hash and native preset availability are validated; post-load hash checking detects ordinary font replacement during initialization. Missing presets fail, never substitute another instrument. Actual preset and full identity are recorded. SF3 uses the installed decoder, but a genuine compressed SF3 asset was not available and remains unverified.

## D. Audio configuration and quality

Defaults: stereo 44.1kHz, gain0.2, bank/preset0/0, polyphony256, interpolation4, reverb/chorus disabled, fresh synth and fixed1.5s tail. 48kHz was also measured;22.05/88.2/96kHz are allowed but not included in the main measured matrix. Single synth CPU core, min-note-length0 and dynamic-sample-loading0 are explicit. Enabled reverb/chorus parameters and all selected settings are recorded in render.json. Default repeated renders were bit-identical on this library/font combination; cross-version or enabled-effect bit identity is not guaranteed.

WAV is RIFF/WAVE IEEE FLOAT32: finite values above full scale remain represented, with an explicit raw clipping-risk warning. FLAC is lossless of the chosen quantized signed PCM24, not lossless retention of float32. Out-of-range integer export fails before publication; optional peak normalization must be explicitly requested and targets0.98. It uses bounded float64 intermediate scaling, retaining float32 PCM at output. Raw and decoded per-file diagnostics are distinguished. Quiet velocity1 and loud velocity127 were tested; high-gain chords exercise clipping refusal.

Every output is reopened with libsndfile/soundfile to verify rate, two channels, exact frame count, finite PCM, expected silence/nonzero audio and actual codec/subtype. Valid empty projects preserve source duration plus tail. Bare empty note arrays default to tail-only silence; zero duration/tail yields one silent frame.

Fixed tails follow content end (the original project duration for project rendering), at least as late as the last note-off. They never modify MIDI offsets. Residual final50ms RMS above-60dBFS is reported, not hidden by fading. A finite tail can truncate a long release/reverb; the user may increase it up to30s. Released native voices are distinguished from unreleased MIDI notes.

## E. Scheduling and measured acoustic behavior

For each event, sample_index=round(time*sample_rate), ties to even. Mathematical rounding bound is0.5sample per event. Deterministic ordering preserves repeated-key retriggers. The native API synthesizes internally in64-sample blocks: messages dispatched after the exact returned PCM count can take effect after up to63 already-generated samples. SoundFont sample/envelope attack adds a separate delay. No compensation shifts are applied and audible attacks are not claimed sample accurate.

Pure scheduler measurement:10,000 independent explicit note intervals /20,000 events per rate, seed20261109:

| Rate Hz | Events | Max error samples | Max error microseconds | Half-sample bound microseconds |
|---:|---:|---:|---:|---:|
| 44100 | 20000 | 0.49999594 | 11.33778 | 11.33787 |
| 48000 | 20000 | 0.49992886 | 10.41518 | 10.41667 |

Fourteen real A4 onset-phase experiments vary native buffer phase at both rates. Acoustic onset is first stereo magnitude>1e-7; this threshold is explicit and not a perceptual guarantee. F0 measurement uses YIN against independent fixed440Hz note truth, not its own output as reference. Sampled piano harmonics are not assumed to have their largest FFT peak at the fundamental.

| Rate Hz | Onset phase runs | Attack delay samples | Attack delay ms | Measured F0 error cents |
|---:|---:|---:|---:|---:|
| 44100 | 7 | 272–335 | 6.168–7.596 | +3.730–+4.277 |
| 48000 | 7 | 296–359 | 6.167–7.479 | +3.901–+4.270 |

The observed phase-dependent addition matches the pending native-block samples; the baseline acoustic delay is272samples at44.1kHz /296samples at48kHz (about6.17ms). These are measured for this font/velocity/threshold, not general piano latency constants. The scheduler itself does not drift or sleep.

Exported controlled cases:

| Case | Notes / note-ons | Frames at48kHz | Peak absolute | Max WAV–FLAC difference |
|---|---:|---:|---:|---:|
| a4 | 1 / 1 | 110400 | 0.01522744 | 0.0000000596 |
| repeated | 3 / 3 | 136800 | 0.01524751 | 0.0000000596 |
| melody | 4 / 4 | 160800 | 0.01733153 | 0.0000000596 |
| silence | 0 / 0 | 72000 | 0.00000000 | 0.0000000000 |

Repeated A4 contains three scheduled onsets and observable attacks; second/third attack RMS are 32.24x / 32.22x the preceding window. The first attack follows exact silence, so its ratio is not treated as a meaningful finite loudness comparison.
C4–D4–E4–G4 measured fractional MIDI centers: `[60.03146830682664, 62.026575521618085, 64.0198212771566, 67.06214981888226]`. Expected keys60/62/64/67 are defined independently. These small sampled-piano/measurement offsets do not change the notes.

Controlled float WAV and FLAC differ by at most5.96046448e-8 (0.5PCM24 LSB in these signals). Empty output is exactly zero. Release PCM remains nonzero after MIDI note-off and reaches zero in the measured final50ms with the default tail. Detailed rows: acoustic-validation.json. ![Measured attack and release](stage4a/render-diagnostics.png)

## F. Automated tests

Complete headless suite including installed CPU neural and real synthesis tests: **168 passed, 0 failed, 0 errors, 3 skipped**, 33.22s. All three skipped display tests pass separately below. Existing Stage 1–3 tests remain passing. Two expected mir_eval warnings concern zero-voiced reference/estimate fixtures.

The28 synthesis/core cases cover sample error/order, simultaneous/repeated same-pitch allocation, sub-sample rejection, limits/invalid config, font resolution/missing presets, optional dependency absence, real pitch/melody/attacks, silence/initial rest, overlap/short events/tails, fresh-instance default determinism, quiet/loud/effects, float and integer quantization, clipping/normalization, safe publication rollback, cancellation/native cleanup/non-finite rejection, no source-audio access, current manual edits and genuine project headless CLI compatibility. Ordinary tests never download a font/model; optional real tests require configured local assets.

Initial core runs25/27 passed as coverage grew; final targeted28 passed after input-iterator handling was normalized. The first GUI command stopped at pytest argument parsing because the custom option needs an explicit tests path in that invocation. It launched no GUI and is retained as gui-initial.log; corrected and release commands passed. No application crash or unresolved failed release assertion was hidden.

## G. Real piano render verification

Genuine Stage 3 human project `results/stage3-human-pyin/vocadito_1.notes.json` rendered65 current notes. Input project SHA256 `e34e9c6eff1136db2e1ba463565c9934cdedf0532a8b5fb13b1c3101c2a30d72` remained unchanged. Source audio was not opened or reanalyzed; separate compatibility tests successfully render an edited project with a deliberately unavailable source-audio path. Editing flags and journal cursor survive into render provenance.

The directly usable example is `results/stage4a-release-piano/piano.wav` and `.flac`, with `render.json`. It uses explicit peak normalization,48kHz stereo and a1.5s tail. Actual decoded files:

| File | Frames | Duration s | Subtype | Bytes | Decoded peak |
|---|---:|---:|---|---:|---:|
| piano.wav | 1666188 | 34.712250 | FLOAT | 13329592 | 0.980000019 |
| piano.flac | 1666188 | 34.712250 | PCM_24 | 2715361 | 0.980000019 |

Explicit normalization factor: 37.86258848, target0.98. Unnormalized output is preserved separately in results/stage4a-first. This is actual SoundFont-sample synthesis, not a sine-wave substitute or MIDI mislabeled as audio. Verification is decoded waveform/pitch/file evidence; speaker listening quality is not claimed as an automated measurement.

## H. CPU and memory performance

Measured CPU: **12th Gen Intel(R) Core(TM) i5-1235U**. Linux-7.2.14-zen1-1-zen-x86_64-with-glibc2.44. Stereo48kHz, TimGM6mb, effects disabled, polyphony256,4096-frame blocks. Serial measurements, shared desktop; no CPU governor/affinity/exclusivity lock. First-call initialization includes lazy binding/native initialization; warm rows use a fresh synth AND fresh font load in an already warm Python/native process. Filesystem caches were not flushed. No pitch estimation is included.

| Content s | First call | Synth init s | Font load s | Render/spool s | WAV encode s | FLAC encode s | Total s | Peak RSS MiB |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | True | 0.01849 | 0.02130 | 0.00264 | 0.00146 | 0.00386 | 0.06202 | 63.59 |
| 1 | False | 0.00437 | 0.01425 | 0.00254 | 0.00114 | 0.00383 | 0.03136 | 65.75 |
| 5 | False | 0.00397 | 0.01384 | 0.00853 | 0.00270 | 0.01184 | 0.05248 | 65.75 |
| 15 | False | 0.00389 | 0.01235 | 0.02553 | 0.00702 | 0.02799 | 0.10431 | 65.88 |
| 120 | False | 0.00414 | 0.01252 | 0.17479 | 0.05208 | 0.20846 | 0.64424 | 66.38 |

Saved33.212s human project -> WAV+FLAC: **0.34934s**, including project validation, owned-worker startup and publication; child peak RSS 70.45MiB. Native load/render/encoding/verification component times are retained in performance.json.

Ratios (content duration / total processing time, first call separate):

- 1s (first): 16.12x total throughput; render/spool-only ratio 379.46x.
- 1s (warm-process): 31.89x total throughput; render/spool-only ratio 393.00x.
- 5s (warm-process): 95.27x total throughput; render/spool-only ratio 585.84x.
- 15s (warm-process): 143.80x total throughput; render/spool-only ratio 587.47x.
- 120s (warm-process): 186.27x total throughput; render/spool-only ratio 686.53x.

Peak RSS is process high-water, including libraries/font and earlier clips, not per-clip allocation or total GUI+child RAM. Native font memory/event metadata are additional to the32KiB PCM chunk. The120s case reached66.38MiB versus63.59MiB first1s; output buffers do not grow with audio duration. A disk spool/codec passes trade disk I/O for bounded RAM. These measurements use a small font and are not a real-time callback/deadline guarantee. ![Measured performance](stage4a/performance.png)

## I. Native GTK / Wayland verification

Actual native run: **3 passed, 0 failed, 0 errors, 0 skipped**, 18.94s. Properties: `{"close_during_piano_render": "passed", "close_during_transcription": "passed", "close_while_chooser_pending": "passed", "crepe_gui_analysis": "passed", "gdk_display_type": "GdkWaylandDisplay", "gtk_heartbeat_count": "75", "native_render_edit_cancel_recovery": "passed", "native_window_mapped": "true", "note_edit_save_load_midi": "passed", "synthesis_display": "GdkWaylandDisplay", "synthesis_heartbeats": "50", "transcription_display": "GdkWaylandDisplay", "transcription_heartbeat": "174", "yin_gui_analysis": "passed"}`.

The mapped GdkWaylandDisplay windows exercise original analysis/estimator selection, Stage 3 editing/save/load/MIDI, and the new rendering panel. New checks load/identify the real preset, render CURRENT unsaved edited pitch to WAV/FLAC, verify source project immutability, reject concurrent jobs, preserve GTK heartbeat, recover from invalid fonts/duplicate exports/permission errors, cancel and retry, choose WAV-only output, cancel a native font chooser, and close during rendering. No fake playback controls were added. The established600ms pending-chooser shutdown workaround remains; no immediate cancellation-before-presentation path was introduced. Broad manual visual/accessibility/listening QA and other GTK/compositor versions remain unverified.

## J. Compatibility, reliability and packaging

544 historical report/data artifacts were checked unchanged against stage4a/preserved-stage123.json; original Stage1 preservation hashes also remain valid. Stage 1–3 DSP, segmentation, pitch centers and project schema were not modified. Existing stage reports remain historical evidence. Shared CLI/worker/UI entry points were extended, and package version changed after initial acceptance evidence.

Fresh wheel installation into a separate target directory rendered the genuine human project at48kHz, reopened WAV/FLAC, verified65 notes/1,666,188frames and ran the existing headless YIN analyze command. GTK and Torch were not imported. Optional-extra metadata and absence of bundled SF2/SF3/audio/model/cache assets were checked. See wheel-verification.json; no network was required for the no-dependency target installation using existing scientific dependencies.

Release versions: `{"librosa": "0.11.0", "matplotlib": "3.11.2", "numpy": "2.5.4", "pretty_midi": "0.2.11.post0", "pyfluidsynth": "1.4.0", "pytest": "9.2.0", "soundfile": "0.13.1", "torch": "2.15.0+cpu", "torchcrepe": "0.0.24", "vocalscope": "0.4.0"}`, libsndfile `1.2.2`. Native configuration and font SHA are in environment.json. Measurements made before the packaging bump retain their renderer1.0.0 identity; changing the package tag did not alter transcription or synthesis timings/settings.

Input projects are regular files limited to64MiB, parsed without executable deserialization; notes and journal remain validated by Stage 3. Source audio metadata paths are used only for output protection, never audio access. SoundFonts are regular SF2/SF3 files with RIFF length/type checks, default512MiB file limit and native preset validation. External native decoders are isolated in production jobs; file checks are not a guarantee against all malicious native-format exploits. Defaults limit total render to3600s including tail,100,000notes, fixed-size streaming chunks, and check free staging disk space. The convenience array API has a64MiB PCM budget. Cancellation removes parent-owned staging after waiting/terminating the child.

Publication uses no-clobber POSIX links with rollback of new links on failure and JSON last. Existing output paths are never replaced; choose a fresh folder. Each encoded file is fsynced. Power loss can leave partial files without a completed manifest; this is not a filesystem-wide transaction.

## K. Reproduction

```bash
cd <checkout>
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Run system changes yourself only if required:
sudo pacman -S --needed fluidsynth soundfont-fluid
python -m pip install -e '.[synthesis]'

# Or explicitly fetch the small checksum/license-checked validation asset:
python scripts/fetch_validation_soundfont.py

vocalscope render-piano results/notes/vocal.notes.json --soundfont /usr/share/soundfonts/FluidR3_GM.sf2 --sample-rate 48000 --output results/piano
vocalscope render-piano results/notes/vocal.notes.json --soundfont data/soundfonts/TimGM6mb.sf2 --normalize-peak --output results/piano-normalized
vocalscope render-piano vocal.notes.json --soundfont piano.sf2 --formats wav --output results/wav
vocalscope render-piano vocal.notes.json --soundfont piano.sf2 --formats flac --output results/flac
GDK_BACKEND=wayland vocalscope gui
python -m pytest tests --run-neural --soundfont data/soundfonts/TimGM6mb.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests -m gui --soundfont data/soundfonts/TimGM6mb.sf2 -v
python scripts/stage4a_validation.py --soundfont data/soundfonts/TimGM6mb.sf2 --output results/new-synthesis-validation
python scripts/stage4a_performance.py --soundfont data/soundfonts/TimGM6mb.sf2 --project results/notes/vocal.notes.json --output results/new-synthesis-performance.json
python -m build --no-isolation
```

CLI additionally exposes bank/preset, gain, polyphony, interpolation, effects, tail, normalization and format selection. Settings can provide soundfont_path through XDG synthesis.json or --settings. In GTK open/load a transcription, expand Offline piano rendering, choose/verify a font, set options and render current notes into a fresh folder. No synchronized Play/Pause/Seek controls belong to this milestone.

## L. Limitations / pending verification

- Real validation uses TimGM6mb SF2 only; genuine compressed SF3, large commercial/multilayer piano fonts, other platforms/rates and subjective piano realism remain unverified.
- Scheduled sample positions meet the rounding bound; native64-frame buffering and measured6–8ms attacks remain. No sample-accurate audible-attack guarantee is made.
- A bounded fixed tail can cut very long releases/effects. Note-off accuracy is inherited unchanged from transcription. Polyphony is a voice budget; complex layered fonts can steal voices if undersized.
- More than15 simultaneously overlapping instances of the same key and events rounding to zero samples are rejected. Filesystems without POSIX hard links cannot use this publication strategy.
- No automatic SoundFont download, universal sample/output license guarantee, synthesized quality correction, sustain-pedal/bend interpretation, latency compensation, live device playback or synchronized vocal comparison is implemented.
- CPU figures are single-run shared-host observations with warm filesystem caching, not latency percentiles or extrapolations to larger fonts. No exhaustive malformed-native-font security audit was performed.

## M. Stage 4B readiness

Available: validated current-note snapshots, sample event logs, deterministic default offline rendering, stereo PCM/WAV/FLAC artifacts with exact frame counts, source hashes/timeline provenance, bounded streaming, process ownership/cancellation and native render controls. Stage 4B can add an audio-device transport with frame-clock synchronization, cached seek/loop behavior, handling of native/effect state at seeks and original-vocal comparison. That transport must account separately for measured synthesis attack/latency. It is not implemented in Stage 4A.
