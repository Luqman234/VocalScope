# Contributing to VocalScope

Use Python 3.11 or newer. Arch Linux with system PyGObject, GTK4/libadwaita,
GStreamer and a `--system-site-packages` venv is the native development target.
See README for installation. Install `.[dev,benchmark]` for tests.

Run `python -m pytest -ra` and `python -m build`. The default suite does not
fetch datasets, model weights or SoundFonts. Native tests skip without a display;
real output additionally requires `--run-output`. Enable local optional assets
only deliberately. Report skips separately from successful hardware validation.

Preserve immutable F0, note-edit journals, source files, schema compatibility,
process isolation and queried playback time. Add deterministic regression tests
for demonstrated defects. Avoid unrelated formatting and algorithm changes.

File bugs with version, OS, backend, reproduction steps and sanitized diagnostics.
Never attach credentials or recordings you lack permission to share. Submit focused
pull requests describing behavior, validation and limitations. Contributions to
original project code are under GPL-3.0-only. Preserve third-party attribution;
do not copy incompatible code, samples or datasets into the repository.
