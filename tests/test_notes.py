# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import numpy as np
import pytest

from vocalscope.notes import hz_to_midi, midi_to_hz, note_measurements, note_name, parse_frequency


@pytest.mark.parametrize("note,hz,midi", [("A3", 220, 57), ("A4", 440, 69), ("C5", 523.2511306011972, 72), ("Bb3", 233.08188075904496, 58), ("C-1", 8.175798915643707, 0)])
def test_known_notes(note, hz, midi):
    assert parse_frequency(note) == pytest.approx(hz)
    assert float(hz_to_midi(hz)) == pytest.approx(midi)
    assert float(midi_to_hz(midi)) == pytest.approx(hz)


def test_fractional_pitch_and_tuning():
    midi = hz_to_midi(np.array([440 * 2 ** (23.5 / 1200), np.nan]))
    names, cents = note_measurements(midi)
    assert midi[0] == pytest.approx(69.235)
    assert names == ["A4", None]
    assert cents[0] == pytest.approx(23.5)
    assert np.isnan(cents[1])
    assert float(hz_to_midi(442, a4_hz=442)) == 69
    assert parse_frequency("A4", a4_hz=442) == 442


def test_nearest_note_ties_and_octaves():
    names, cents = note_measurements(np.array([69.5, 70.5, 59.9]))
    assert names == ["A#4", "A#4", "C4"]
    np.testing.assert_allclose(cents, [-50, 50, -10])
    assert note_name(-1) == "B-2"


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-440", "H3", "C#", "", "A999999"])
def test_bad_frequency_text(value):
    with pytest.raises(ValueError):
        parse_frequency(value)


@pytest.mark.parametrize("hz", [0, -1, np.inf])
def test_bad_frequency(hz):
    with pytest.raises(ValueError):
        hz_to_midi(hz)

