#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Measure main-interpreter timer stalls without claiming physical GTK testing."""

import json
from pathlib import Path
import tempfile
from threading import Thread
from time import perf_counter, sleep

import soundfile as sf

from vocalscope.models import AnalysisConfig
from vocalscope.pitch import analyze_file
from vocalscope.validation import make_case
from vocalscope.worker import analyze_in_process


def main() -> None:
    case = make_case("harmonics", duration=15)
    config = AnalysisConfig()
    report = {"method": "15 s audio, 10 ms main-interpreter timer while background thread computes. Indirect GIL/IPC test; no GTK window or Wayland verification.", "measurements": []}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "timer.wav"
        sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
        analyze_file(path, config)  # warm imports and on-disk JIT caches
        for name, compute in (("thread_only", analyze_file), ("thread_with_child_process", analyze_in_process)):
            errors = []

            def work():
                try:
                    compute(path, config)
                except Exception as exc:
                    errors.append(str(exc))

            thread = Thread(target=work)
            start = before = perf_counter()
            thread.start()
            gaps = []
            while thread.is_alive():
                sleep(0.01)
                now = perf_counter()
                gaps.append(now - before)
                before = now
            thread.join()
            row = {"mode": name, "audio_duration_seconds": 15,
                   "wall_seconds": perf_counter() - start, "tick_count": len(gaps),
                   "max_timer_gap_seconds": max(gaps), "errors": errors}
            report["measurements"].append(row)
            print(json.dumps(row), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/responsiveness.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

