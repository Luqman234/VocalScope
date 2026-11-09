# VocalScope


VocalScope 0.5.1 is a free and open-source Linux workstation for analyzing
monophonic singing, transcribing it into editable MIDI notes, rendering piano
audio, and comparing vocals and piano on one playback timeline.

VocalScope is free software under the **GNU General Public License version 3.0
only (GPL-3.0-only)**. You may use, study, modify and redistribute it under the
[license](LICENSE). Copyright (C) 2026 Luqman234. There is no warranty.

## Features

- pYIN and YIN pitch tracking, with optional CPU CREPE inference.
- Continuous F0, genuine unvoiced gaps and estimator-specific voicing scores.
- Acoustic onset features and conservative note segmentation.
- Editable GTK4 piano roll, undo/redo and persistent non-destructive projects.
- MIDI, JSON, CSV and diagnostic PNG exports.
- Optional FluidSynth piano rendering to stereo WAV float32 and FLAC PCM24.
- Shared-clock GStreamer vocal/piano playback, A/B comparison, mixing, seeks,
  loops and asynchronous edit audition through PipeWire.
- Native GTK4/libadwaita interface and independent headless CLI.
- Deterministic synthetic tests and human-annotated Vocadito benchmarking.

## Current limitations

This is a monophonic-focused transcription baseline, not perfect transcription.
Note releases can be inaccurate; repeated notes can be missed or duplicated;
vibrato, octave errors and slides remain ambiguous. Full-song vocal separation,
polyphonic transcription and automatic expressive arrangement are not included.
External piano SoundFonts are required for synthesis. Loops can click/gap and
render replacement briefly interrupts playback. Physical listening, hardware
unplug acceptance and end-to-end acoustic latency remain incompletely verified.
Software synchronization tests do not establish physical listening quality.

## Installation on Arch Linux

Install system packages yourself; VocalScope never installs system components:

```bash
sudo pacman -S --needed python python-pip python-gobject python-cairo gtk4 libadwaita \
  libsndfile gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire pipewire-pulse
# For optional piano synthesis:
sudo pacman -S --needed fluidsynth

git clone https://github.com/Luqman234/VocalScope.git
cd VocalScope
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e '.[dev,benchmark,synthesis,playback]'
```

Python 3.11+ and GTK 4.10+ are required. System site packages expose Arch's
compiled PyGObject and pycairo; do not pip-install a second GI stack. Recreate
the venv after system Python ABI changes. Headless analysis/transcription needs
neither GTK, GStreamer nor FluidSynth. Playing an existing render does not need
FluidSynth or Torch. Rendering an existing project does not need Torch.

For optional neural CPU inference, install compatible CPU `torch`/`torchaudio`
from the official PyTorch distribution, then `python -m pip install -e '.[crepe]'`.
Tiny and full torchcrepe models are supported; full is expensive on the tested
CPU. Dependencies/model assets must be available locally before offline use.
Model periodicity is not calibrated probability of correct pitch.

## Quick start

```bash
GDK_BACKEND=wayland vocalscope gui --max-memory-mb 2048
vocalscope analyze vocal.wav --output results/pitch --estimator pyin
vocalscope transcribe vocal.wav --output results/notes --estimator pyin
# Notes export includes a playable MIDI file and editable .notes.json project.
vocalscope transcribe vocal.wav --output results/crepe --estimator crepe --crepe-model tiny
vocalscope render-piano results/notes/vocal.notes.json \
  --soundfont /path/to/piano.sf2 --sample-rate 48000 --output results/piano
vocalscope playback-test --vocal vocal.wav --piano results/piano/piano.wav \
  --sink pipewiresink --seconds 2 --output results/playback.json
```

In GTK, open a recording, Analyze, Generate notes, edit selected notes and save
projects or export MIDI. Select a licensed SoundFont in the offline render panel,
render/export WAV or FLAC, then load vocals/piano in Playback. Play/Pause/Stop,
source modes, gains, loop controls and shared cursor use queried media time.
Edited notes can be rerendered asynchronously; obsolete revisions cannot replace
newer edits. Save edits before replacing an analysis/project.

**Analysis parameters → Maximum DSP memory (MiB)** defaults to 1,024 MiB. The
GUI option sets its initial value; change it for loading, analysis and note
generation. For an estimated 1,522 MiB requirement, use 2,048 MiB if RAM permits.
This is an admission estimate, not reserved memory or an OS RSS limit; Python,
JIT and libraries require additional RAM. Errors explain how to raise it.
Default duration safeguard is 300 seconds; long recordings may exhaust the
working-array budget sooner. No aggressive normalization, smoothing or filling
of unvoiced F0 is applied by default.

WAV/FLAC and decoder-supported OGG are supported. Stereo is downmixed by arithmetic
mean; opposite-polarity channels may cancel and are diagnosed. Sources are never
modified. Pitch exports preserve fractional MIDI and Hz. MIDI uses original note
times without grid quantization. MIDI is event data; rendered WAV/FLAC is audio.
Piano releases add tails without changing note offsets. WAV float32 preserves
floating samples; FLAC PCM24 quantizes to integer PCM. Peak normalization is opt-in.

## SoundFonts and media rights

Provide your own SF2/SF3 compatible with installed FluidSynth. An explicit path
wins over application settings and verified system candidates. The requested
bank/preset must exist (default General MIDI piano, bank/program 0).
No SoundFont, dataset, commercial vocal or generated song performance is bundled.
TimGM6mb used locally has separate GPL-2 sample terms and is **not distributed**.
FluidSynth's software license does not license its samples or your recordings.
VocalScope's GPL does not automatically license music, recordings, datasets,
weights or SoundFonts. Respect their separate terms and permissions.

## Scientific evaluation and testing

```bash
python -m pytest -ra
python -m build
# Optional integrations use existing local assets; never downloaded by pytest:
python -m pytest tests --run-neural --soundfont /path/to/piano.sf2 -ra
GDK_BACKEND=wayland python -m pytest tests -m 'gui or audio_output' \
  --run-output --soundfont /path/to/piano.sf2 -ra
# Explicit dataset acquisition, under its own CC BY 4.0 terms:
vocalscope dataset download --path data/vocadito
vocalscope benchmark --dataset-path data/vocadito --estimators pyin,yin,crepe \
  --crepe-model tiny --output results/pitch-benchmark
vocalscope benchmark-notes --dataset-path data/vocadito --output results/note-benchmark
```

The bundled file is only a checksum index, not audio or annotations. Vocadito v3
contains 40 recordings and human F0 plus two note-annotation sets. Stage 2 used
20 development and 20 held-out tracks but shared four singer identities; Stage 3
uses singer-disjoint grouping and both annotators. Historical held-out macro
RPA50 was 92.88% pYIN, 92.56% YIN and 95.58% CREPE-tiny; these are **F0 scores,
not note F1**. CREPE-tiny also had 21.18% voicing false alarms. See detailed
[engineering summaries](docs/engineering/) for denominators, note-event scores,
ablations, accuracy limitations and measured environments. These are historical
measurements, not guarantees for a new recording or fresh publication test runs.

Public summaries redact local paths. Original raw evidence remains local rather
than bundling recordings, annotations and sensitive logs. Some historical report
links target these intentionally unbundled artifacts; reproduction requires the
explicit local dataset/assets. [Listening/device acceptance](docs/PLAYBACK_ACCEPTANCE.md)
distinguishes automated PCM/stream evidence from human acceptance.
[Publication verification](reports/OPEN_SOURCE_PUBLICATION.md) records fresh checks.

CI runs headless tests and package checks; skipped native/model/SoundFont tests
are not physical validation. See [CONTRIBUTING](CONTRIBUTING.md),
[SECURITY](SECURITY.md), and [third-party notices](THIRD_PARTY_NOTICES.md).
