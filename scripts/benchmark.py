#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Run actual synthetic accuracy and serial CPU benchmarks; save all evidence."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import platform
import resource
import tempfile
from time import perf_counter

import numpy as np
import soundfile as sf

from vocalscope.models import AnalysisConfig
from vocalscope.notes import parse_frequency
from vocalscope.pitch import analyze_file, library_versions
from vocalscope.validation import CASE_NAMES, SEED, evaluate, make_case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/benchmark.json"))
    parser.add_argument("--durations", type=float, nargs="+", default=[1, 5, 15])
    parser.add_argument("--frame-length", type=int, default=2048)
    parser.add_argument("--fmax", default="D6")
    parser.add_argument("--no-trough-prob", type=float, default=0.001)
    args = parser.parse_args()
    config = AnalysisConfig(frame_length=args.frame_length, fmax=parse_frequency(args.fmax), no_trough_prob=args.no_trough_prob)
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), cpu)
    report = {
        "status": "running", "environment": {"platform": platform.platform(), "cpu": cpu,
        "versions": library_versions()}, "seed": SEED, "config": asdict(config),
        "method": "Float WAV input; frame centers aligned to analytic truth. Interior metrics exclude 250 ms at file edges and discontinuities; full metrics include all frames. Memory is Linux process ru_maxrss high water, includes imports/JIT and previous cases, not incremental DSP memory. First case is cold in this process (disk JIT caches may exist). Serial wall times on shared host; no GPU.",
        "accuracy": [], "window_tradeoffs": [], "performance": [], "human_vocal_accuracy": "Not independently established; no annotated human recordings supplied.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    with tempfile.TemporaryDirectory(prefix="vocalscope-benchmark-") as temp:
        for index, name in enumerate(CASE_NAMES):
            case = make_case(name, duration=3 if name == "silence_gap" else 2)
            path = Path(temp) / f"{name}.wav"
            sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
            start = perf_counter()
            result = analyze_file(path, config)
            total = perf_counter() - start
            truth = case.truth_hz(result.time_seconds)
            row = {"case": name, "description": case.description, "duration_seconds": len(case.samples)/case.sample_rate,
                   "cold_process_first_case": index == 0, "interior": evaluate(result, truth, case.evaluation_mask(result.time_seconds)),
                   "full_clip": evaluate(result, truth), "pyin_runtime_seconds": result.runtime_seconds,
                   "load_and_analysis_wall_seconds": total, "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
            if name.startswith("vibrato"):
                use = case.evaluation_mask(result.time_seconds) & result.voiced
                est_cents = 1200 * np.log2(result.f0_hz[use] / 440)
                ref_cents = 1200 * np.log2(truth[use] / 440)
                row["trajectory_correlation"] = float(np.corrcoef(est_cents, ref_cents)[0, 1]) if len(est_cents) > 1 and est_cents.std() > 0 else None
                row["estimated_to_true_cents_std_ratio"] = float(est_cents.std() / ref_cents.std()) if len(est_cents) else None
            report["accuracy"].append(row)
            print(json.dumps(row), flush=True)
            save()
        # Controlled parameter comparison; the baseline above is always retained.
        for name in ("vibrato_5hz", "glissando", "boundary_C2"):
            for frame_length in (1024, 2048, 4096):
                if frame_length == config.frame_length:
                    continue
                case = make_case(name)
                path = Path(temp) / "window_comparison.wav"
                sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
                comparison_config = replace(config, frame_length=frame_length)
                result = analyze_file(path, comparison_config)
                truth = case.truth_hz(result.time_seconds)
                row = {"case": name, "frame_length": frame_length,
                       "interior": evaluate(result, truth, case.evaluation_mask(result.time_seconds)),
                       "pyin_runtime_seconds": result.runtime_seconds}
                if name.startswith("vibrato"):
                    use = case.evaluation_mask(result.time_seconds) & result.voiced
                    est_cents = 1200 * np.log2(result.f0_hz[use] / 440)
                    ref_cents = 1200 * np.log2(truth[use] / 440)
                    row["trajectory_correlation"] = float(np.corrcoef(est_cents, ref_cents)[0, 1]) if len(est_cents) > 1 and est_cents.std() > 0 else None
                    row["estimated_to_true_cents_std_ratio"] = float(est_cents.std() / ref_cents.std()) if len(est_cents) else None
                report["window_tradeoffs"].append(row)
                print(json.dumps(row), flush=True)
                save()
        for duration in args.durations:
            case = make_case("harmonics", duration=duration)
            path = Path(temp) / "timing.wav"
            sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
            start = perf_counter()
            result = analyze_file(path, config)
            wall = perf_counter() - start
            row = {"duration_seconds": duration, "pyin_runtime_seconds": result.runtime_seconds,
                   "load_and_analysis_wall_seconds": wall, "runtime_over_audio_duration": wall / duration,
                   "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
            report["performance"].append(row)
            print(json.dumps(row), flush=True)
            save()
    report["status"] = "complete"
    save()


if __name__ == "__main__":
    main()

