# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
import hashlib

import numpy as np
import pytest
import soundfile as sf

from vocalscope.audio import load_audio
from vocalscope.errors import AudioError, ConfigurationError
from vocalscope.models import AnalysisConfig
from vocalscope.pitch import analyze_file
from vocalscope.preprocessing import resample_audio


@pytest.mark.parametrize("format,subtype,suffix", [("WAV", "FLOAT", "wav"), ("FLAC", "PCM_16", "flac"), ("OGG", "VORBIS", "ogg")])
def test_real_decoder_formats_and_metadata(tmp_path, format, subtype, suffix):
    if not sf.check_format(format, subtype):
        pytest.skip(f"Installed libsndfile does not support {format}/{subtype}")
    sr = 48000
    t = np.arange(sr) / sr
    stereo = np.column_stack((0.4 * np.sin(2*np.pi*220*t), 0.2 * np.sin(2*np.pi*220*t)))
    path = tmp_path / f"recording.{suffix}"
    sf.write(path, stereo, sr, format=format, subtype=subtype)
    before = hashlib.sha256(path.read_bytes()).digest()
    audio = load_audio(path)
    assert audio.metadata.original_sample_rate == sr
    assert audio.metadata.channels == 2
    assert audio.metadata.original_frames == sr
    assert audio.metadata.duration_seconds == 1
    assert audio.metadata.downmix == "arithmetic_mean"
    assert audio.sample_rate == 22050
    assert len(audio.samples) == 22050
    assert not audio.samples.flags.writeable
    assert hashlib.sha256(path.read_bytes()).digest() == before
    # Lossy OGG affects amplitude a little; phase/mean behavior tested exactly below.
    assert np.sqrt(np.mean(audio.samples**2)) == pytest.approx(0.3 / np.sqrt(2), rel=0.05)


def test_stereo_mean_and_polarity_warning(tmp_path):
    y = 0.2 * np.sin(2*np.pi*440*np.arange(22050)/22050)
    path = tmp_path / "opposite.wav"
    sf.write(path, np.column_stack((y, -y)), 22050, subtype="DOUBLE")
    audio = load_audio(path)
    assert np.max(np.abs(audio.samples)) == 0
    assert any("cancellation" in w for w in audio.metadata.warnings)


def test_clipping_is_diagnosed_without_limiting(tmp_path):
    path = tmp_path / "clipped.wav"
    samples = np.array([1.25, -1.1, 0.1, 0.0])
    sf.write(path, samples, 22050, subtype="DOUBLE")
    audio = load_audio(path)
    assert audio.metadata.clipped_sample_fraction == 0.5
    np.testing.assert_array_equal(audio.samples, samples)


@pytest.mark.parametrize("samples", [np.array([]), np.array([0, np.nan]), np.array([0, np.inf])])
def test_empty_and_nonfinite_audio(tmp_path, samples):
    path = tmp_path / "bad.wav"
    sf.write(path, samples, 22050, subtype="DOUBLE")
    with pytest.raises(AudioError, match="empty|non-finite"):
        load_audio(path)


def test_extreme_amplitude_rejected_before_overflow(tmp_path):
    path = tmp_path / "overflow.wav"
    sf.write(path, np.array([1e300, -1e300]), 22050, subtype="DOUBLE")
    with pytest.raises(AudioError, match="amplitude"):
        load_audio(path)


def test_invalid_missing_and_multichannel_files(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"this is not audio")
    with pytest.raises(AudioError, match="Cannot decode"):
        load_audio(path)
    with pytest.raises(AudioError):
        load_audio(tmp_path / "absent.flac")
    sf.write(path, np.zeros((100, 3)), 22050)
    with pytest.raises(AudioError, match="mono or stereo"):
        load_audio(path)


@pytest.mark.parametrize("length", [1, 100, 1000])
def test_very_short_files_are_predictable(tmp_path, length):
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(length), 22050, subtype="FLOAT")
    result = analyze_file(path)
    assert len(result.voiced) == 1 + length // 512
    assert np.all(np.isnan(result.f0_hz[~result.voiced]))
    assert any("Short clip" in warning for warning in result.warnings)


def test_resampling_length_and_tone():
    source_rate = 48000
    n = 48001
    y = np.sin(2*np.pi*440*np.arange(n)/source_rate)
    out = resample_audio(y, source_rate, 22050)
    assert len(out) == int(np.ceil(n * 22050 / source_rate))
    ref = np.sin(2*np.pi*440*np.arange(len(out))/22050)
    np.testing.assert_allclose(out[100:-100], ref[100:-100], atol=0.002)
    assert resample_audio(y, source_rate, source_rate) is y


@pytest.mark.parametrize("change", [
    {"fmin": 0}, {"fmax": 15000}, {"fmin": 2000}, {"sample_rate": 0},
    {"frame_length": 511}, {"frame_length": 128}, {"hop_length": 8192},
    {"switch_prob": 1}, {"resolution": 0.001}, {"no_trough_prob": -1},
    {"max_duration_seconds": np.nan}, {"max_memory_mb": 0}, {"frame_length": True},
    {"fmin": 440, "fmax": 450},
])
def test_config_rejects_invalid_or_impractical_values(change):
    with pytest.raises(ConfigurationError):
        AnalysisConfig(**change)


def test_duration_and_memory_safeguards_before_decode(tmp_path):
    path = tmp_path / "long.wav"
    sf.write(path, np.zeros(22050), 22050)
    with pytest.raises((ConfigurationError, AudioError), match="limit"):
        load_audio(path, AnalysisConfig(max_duration_seconds=0.5))
    with pytest.raises((ConfigurationError, AudioError), match="budget"):
        load_audio(path, AnalysisConfig(max_memory_mb=1))


def test_pathological_resampling_ratio_is_bounded(tmp_path):
    path = tmp_path / "unusual_rate.wav"
    sf.write(path, np.zeros(4), 1_000_003, subtype="FLOAT")
    with pytest.raises(AudioError, match="Resampling filter"):
        load_audio(path)

