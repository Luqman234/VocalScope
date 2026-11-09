#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Reproduce the pYIN no-trough prior comparison; no amplitude/confidence gate."""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

import numpy as np
import soundfile as sf

from vocalscope.models import AnalysisConfig
from vocalscope.notes import parse_frequency
from vocalscope.pitch import analyze_file, library_versions
from vocalscope.validation import SEED, evaluate, make_case


def main() -> None:
    report = {"versions": library_versions(), "method": "Compare pYIN parameters on deterministic files. Noise seeds 7, 91 and 20261109. No post-hoc voicing mask, RMS gate or invented pitch confidence.", "measurements": []}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "comparison.wav"
        for frame in (2048, 4096):
            for prior in (0.01, 0.001):
                config = AnalysisConfig(frame_length=frame, fmax=parse_frequency("C6"), no_trough_prob=prior)
                for name, seed in (("noise_only", 7), ("noise_only", 91), ("noise_only", SEED), ("noise_snr_0", SEED), ("soft_A4", SEED)):
                    case = make_case(name)
                    y = np.random.default_rng(seed).normal(0, 0.1, len(case.samples)) if name == "noise_only" else case.samples
                    sf.write(path, y, case.sample_rate, subtype="FLOAT")
                    result = analyze_file(path, config)
                    row = {"frame_length": frame, "no_trough_prob": prior, "case": name, "seed": seed,
                           "interior": evaluate(result, case.truth_hz(result.time_seconds), case.evaluation_mask(result.time_seconds))}
                    report["measurements"].append(row)
                    print(json.dumps(row), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/voicing_comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

