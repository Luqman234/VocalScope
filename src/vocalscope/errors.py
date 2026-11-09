# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Errors suitable for presentation at CLI and GUI boundaries."""


class VocalScopeError(Exception):
    """Expected input, resource, or analysis failure."""


class AudioError(VocalScopeError):
    """Audio could not be safely decoded."""


class ConfigurationError(VocalScopeError, ValueError):
    """Invalid or impractical analysis parameters."""

