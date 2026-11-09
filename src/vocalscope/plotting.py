# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Backend-independent pitch figures. No pyplot, GTK, or global backend changes."""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .models import AnalysisResult
from .notes import hz_to_midi, note_name


def draw_result(figure: Figure, result: AnalysisResult | None, *, dark: bool = False) -> None:
    """Draw unmodified MIDI trajectory and separate voicing-probability panel."""
    figure.clear()
    background, foreground, grid = ("#202328", "#ebedf0", "#454b54") if dark else ("#ffffff", "#252a32", "#d9dee6")
    figure.set_facecolor(background)
    pitch_ax, prob_ax = figure.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [4, 1]})
    for ax in (pitch_ax, prob_ax):
        ax.set_facecolor(background)
        ax.tick_params(colors=foreground, labelsize=9)
        ax.xaxis.label.set_color(foreground)
        ax.yaxis.label.set_color(foreground)
        ax.title.set_color(foreground)
        for spine in ax.spines.values():
            spine.set_color(grid)
        ax.grid(True, color=grid, linewidth=0.5, alpha=0.6)
    pitch_ax.yaxis.set_major_locator(MaxNLocator(nbins=12, integer=True))
    pitch_ax.yaxis.set_major_formatter(FuncFormatter(lambda m, _: f"{note_name(round(m))} ({m:.0f})"))
    pitch_ax.set_ylabel("Pitch · note (MIDI)")
    score_labels={'pyin':'Voicing\nprobability','yin':'YIN lag\ncorrelation','crepe':'CREPE\nperiodicity'}
    prob_ax.set_ylabel(score_labels.get(result.estimator_id if result else 'pyin','Backend score'))
    prob_ax.set_xlabel("Time (seconds)")
    prob_ax.set_ylim(-0.03, 1.03)
    prob_ax.set_yticks([0, 0.5, 1])
    if result is None:
        pitch_ax.set_title("Open a mono or stereo vocal recording, then Analyze", fontsize=12)
        pitch_ax.set_ylim(36, 84)
        return
    t = result.time_seconds
    def frame_coordinate(x: float, _y: float) -> str:
        index = min(int(np.searchsorted(t, x)), len(t) - 1)
        if index > 0 and abs(t[index - 1] - x) < abs(t[index] - x):
            index -= 1
        prefix = f"Frame {index} · {t[index]:.3f} s · {result.confidence_type}={result.confidence[index]:.3f}"
        if not result.voiced[index]:
            return prefix + " · unvoiced"
        return (prefix + f" · {result.f0_hz[index]:.3f} Hz · MIDI {result.midi_pitch[index]:.3f}"
                + f" · {result.nearest_note[index]} {result.cents_deviation[index]:+.1f} cents")
    pitch_ax.format_coord = frame_coordinate
    prob_ax.format_coord = frame_coordinate
    # NaN separates line segments, including one-frame unvoiced interruptions.
    pitch_ax.plot(t, result.midi_pitch, color="#3da9e8", linewidth=1.1, marker=".", markersize=2, label=f"{result.estimator_id} F0")
    edges = np.r_[0.0, (t[:-1] + t[1:]) / 2, max(result.metadata.duration_seconds, float(t[-1]), 0.01)]
    for ax in (pitch_ax, prob_ax):
        # Explicit frame cells also shade a single unvoiced frame; fill_between
        # with a Boolean `where` mask requires adjacent True values to fill.
        ax.stairs((~result.voiced).astype(float), edges, baseline=0, fill=True,
                  transform=ax.get_xaxis_transform(), color="#a4abb5", alpha=0.20,
                  linewidth=0, label="Unvoiced")
    prob_ax.plot(t, result.confidence, color="#31ad8c", linewidth=1)
    voiced_pitch = result.midi_pitch[result.voiced]
    if voiced_pitch.size:
        low, high = float(voiced_pitch.min()), float(voiced_pitch.max())
        pitch_ax.set_ylim(low - 2, high + 2)
    else:
        pitch_ax.set_ylim(float(hz_to_midi(result.config.fmin)) - 1, float(hz_to_midi(result.config.fmax)) + 1)
    prob_ax.set_xlim(0, max(result.metadata.duration_seconds, float(t[-1]), 0.01))
    model=result.estimator_configuration.get('crepe_model','') if result.estimator_id=='crepe' else ''
    pitch_ax.set_title(f'{result.metadata.filename} · {result.estimator_id} {model}'.strip(), fontsize=12)
    legend = pitch_ax.legend(loc="upper right", fontsize=8, facecolor=background, edgecolor=grid)
    for text in legend.get_texts():
        text.set_color(foreground)


def create_figure(result: AnalysisResult | None = None, *, dark: bool = False) -> Figure:
    figure = Figure(figsize=(11, 6), dpi=110, layout="constrained")
    draw_result(figure, result, dark=dark)
    return figure

