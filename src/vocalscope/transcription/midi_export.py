# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Standard MIDI in real seconds, 120 BPM serialization only, no grid snapping."""
from io import BytesIO
import pretty_midi


def midi_bytes(notes):
    # 9600 ticks/quarter at 120 BPM: nearest-tick error <= 26.1 microseconds.
    midi=pretty_midi.PrettyMIDI(initial_tempo=120.,resolution=9600)
    piano=pretty_midi.Instrument(program=0,name='VocalScope melody')
    for n in notes:
        piano.notes.append(pretty_midi.Note(velocity=n.velocity,pitch=n.midi_note,start=n.start_seconds,end=n.end_seconds))
    midi.instruments.append(piano)
    out=BytesIO();midi.write(out);return out.getvalue()
