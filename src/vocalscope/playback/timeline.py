# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Pure timeline helpers; no wall-clock extrapolation."""

def active_note_ids(notes,media_time):
    return tuple(n.note_id for n in notes if n.start_seconds<=media_time<n.end_seconds)


def session_duration(metadata):
    return max(max(0.,m['duration_seconds']+m['offset_seconds']) for m in metadata.values())
