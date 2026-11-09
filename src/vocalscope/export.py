# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Lossless frame serialization and staged CSV/JSON/PNG exports."""

import csv
from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator

import numpy as np

from .errors import VocalScopeError
from .models import AnalysisConfig, AnalysisResult, AudioMetadata

SCHEMA_VERSION = "1.1.0"
FIELDS = ("time_seconds", "f0_hz", "voiced", "voiced_probability", "midi_pitch", "nearest_note", "cents_deviation",
          "estimator_id", "confidence_type", "confidence_value")


def frame_records(result: AnalysisResult) -> Iterator[dict[str, float | bool | str | None]]:
    for index, values in enumerate(zip(result.time_seconds, result.f0_hz, result.voiced,
                      result.voiced_probability, result.midi_pitch,
                      result.nearest_note, result.cents_deviation, strict=True)):
        row: dict[str, float | bool | str | None] = {}
        for key, value in zip(FIELDS[:7], values, strict=True):
            if isinstance(value, (bool, np.bool_)):
                row[key] = bool(value)
            elif isinstance(value, (float, np.floating)):
                row[key] = float(value) if np.isfinite(value) else None
            else:
                row[key] = value
        row.update(estimator_id=result.estimator_id, confidence_type=result.confidence_type,
                   confidence_value=float(result.confidence[index]))
        yield row


def result_document(result: AnalysisResult) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": asdict(result.metadata),
        "estimator": {"id": result.estimator_id, "version": result.estimator_version,
                      "configuration": result.estimator_configuration, "confidence_type": result.confidence_type,
                      "metadata": result.backend_metadata, "initialization_seconds": result.initialization_seconds},
        "analysis": {**asdict(result.config), "algorithm": result.backend_metadata.get("algorithm", "librosa.pyin"), "center": True,
                     "pad_mode": "constant", "fill_na": None, "analysis_samples": result.analysis_samples,
                     "time_alignment": "timestamps are actual backend frame centers; consult estimator metadata for rate and hop",
                     "preprocessing": "arithmetic-mean stereo downmix, scipy.signal.resample_poly if required; no gain, gate or smoothing"},
        "semantics": {
            "voiced_probability": "pYIN probability of voicing, not calibrated probability of correct F0",
            "confidence_value": "backend-specific score; consult confidence_type; neither scores nor probabilities are calibrated pitch correctness",
            "missing_pitch": "null for all pitch fields when unvoiced",
            "nearest_note": "scientific pitch notation with sharps; exact half-semitone ties to even MIDI integer",
            "edge_frames": "zero-padded; final center may exceed source duration by less than one analysis sample after resampling",
        },
        "versions": result.versions, "warnings": result.warnings,
        "summary": result.summary(), "frames": list(frame_records(result)),
    }


def result_from_document(document: dict) -> AnalysisResult:
    """Reconstruct the exact core contract from schema 1.0.0 (also used by IPC).

    No pickle or executable deserialization is used. AnalysisResult validates
    frame lengths, finiteness, voicing and missing-value consistency.
    """
    if document.get("schema_version") not in ("1.0.0", SCHEMA_VERSION):
        raise ValueError("Unsupported VocalScope result schema.")
    source = dict(document["source"])
    source["warnings"] = tuple(source.get("warnings", ()))
    config = AnalysisConfig(**{f.name: document["analysis"][f.name] for f in fields(AnalysisConfig)})
    rows = document["frames"]
    estimator = document.get("estimator", {})
    if any(type(row["voiced"]) is not bool for row in rows):
        raise ValueError("Serialized voiced flags must be JSON booleans.")
    numeric = {key: np.asarray([row[key] for row in rows], dtype=np.float64)
               for key in ("time_seconds", "f0_hz", "voiced_probability", "midi_pitch", "cents_deviation")}
    return AnalysisResult(
        metadata=AudioMetadata(**source), config=config,
        analysis_samples=int(document["analysis"]["analysis_samples"]),
        **numeric, voiced=np.asarray([row["voiced"] for row in rows], dtype=bool),
        nearest_note=[row["nearest_note"] for row in rows],
        runtime_seconds=float(document["summary"]["runtime_seconds"]),
        versions=dict(document["versions"]), warnings=tuple(document["warnings"]),
        estimator_id=estimator.get("id", "pyin"), estimator_version=estimator.get("version", ""),
        estimator_configuration=estimator.get("configuration", {}),
        confidence_type=estimator.get("confidence_type", "pyin_voicing_probability"),
        confidence=np.asarray([row.get("confidence_value", row["voiced_probability"]) for row in rows], dtype=float),
        backend_metadata=estimator.get("metadata", {}), initialization_seconds=estimator.get("initialization_seconds", 0.0),
    )


def export_bundle(result: AnalysisResult, directory: str | Path, *, formats: tuple[str, ...] = ("csv", "json", "png"), overwrite: bool = False) -> dict[str, Path]:
    """Render all files before publishing; existing files require explicit overwrite.

    Each file is published atomically. A multi-file export is not one filesystem
    transaction; power loss can leave a partial bundle. Source is always protected.
    """
    if not formats or set(formats) - {"csv", "json", "png"}:
        raise VocalScopeError("Export formats must be one or more of csv, json, png.")
    directory = Path(directory).expanduser().resolve()
    stem = Path(result.metadata.filename).stem
    paths = {fmt: directory / f"{stem}.{fmt}" for fmt in dict.fromkeys(formats)}
    for target in paths.values():
        if target.resolve() == Path(result.metadata.path).resolve():
            raise VocalScopeError("Export destination would overwrite the source recording.")
        if target.exists() and not overwrite:
            raise VocalScopeError(f"Output already exists: {target}. Choose another directory or use --overwrite.")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".vocalscope-", dir=directory) as staging:
            staged = {fmt: Path(staging) / path.name for fmt, path in paths.items()}
            if "csv" in staged:
                with staged["csv"].open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=FIELDS)
                    writer.writeheader()
                    for row in frame_records(result):
                        row["voiced"] = "true" if row["voiced"] else "false"
                        writer.writerow(row)
            if "json" in staged:
                with staged["json"].open("w", encoding="utf-8") as stream:
                    json.dump(result_document(result), stream, indent=2, allow_nan=False)
                    stream.write("\n")
            if "png" in staged:
                from matplotlib.backends.backend_agg import FigureCanvasAgg
                from .plotting import create_figure
                figure = create_figure(result)
                FigureCanvasAgg(figure).print_png(staged["png"])
                figure.clear()
            published: list[Path] = []
            try:
                for fmt, target in paths.items():
                    if overwrite:
                        os.replace(staged[fmt], target)
                    else:
                        os.link(staged[fmt], target)
                        published.append(target)
            except OSError:
                for path in published:
                    path.unlink(missing_ok=True)
                raise
    except OSError as exc:
        raise VocalScopeError(f"Cannot export results: {exc}") from exc
    return paths

