# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Lazy backend registry. Availability checks never import torch or load weights."""

from importlib.util import find_spec
from .base import EstimatorConfig, EstimatorOutput, PitchEstimator
from ..errors import VocalScopeError


def availability() -> dict[str, str | None]:
    missing = [name for name in ("torch", "torchaudio", "torchcrepe") if find_spec(name) is None]
    return {"pyin": None, "yin": None,
            "crepe": "Missing optional packages: " + ", ".join(missing) if missing else None}


def get_estimator(identifier: str) -> PitchEstimator:
    if identifier in ("pyin", "yin"):
        from .classical import ClassicalEstimator
        return ClassicalEstimator(identifier)
    if identifier == "crepe":
        if availability()["crepe"]:
            raise VocalScopeError(availability()["crepe"] + "; install CPU PyTorch and vocalscope[crepe].")
        from .crepe import CrepeEstimator
        return CrepeEstimator()
    raise VocalScopeError(f"Unknown estimator {identifier!r}; choose pyin, yin, or crepe.")

