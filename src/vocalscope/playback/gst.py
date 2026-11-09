# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Lazy optional bindings with actionable Arch installation errors."""
from functools import lru_cache
from .models import PlaybackError

@lru_cache(maxsize=1)
def bindings():
    try:
        import gi
        gi.require_version('Gst','1.0');gi.require_version('GstApp','1.0');gi.require_version('GstController','1.0');gi.require_version('GstPbutils','1.0')
        from gi.repository import Gst,GstApp,GstController,GstPbutils
        Gst.init(None)
        return Gst,GstApp,GstController,GstPbutils
    except (ImportError,ValueError) as exc:
        raise PlaybackError('GStreamer playback unavailable. On Arch install gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire python-gobject and use a --system-site-packages venv. '+str(exc)) from exc
