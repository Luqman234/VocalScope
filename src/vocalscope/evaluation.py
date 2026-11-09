# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Reference-grid alignment and metrics; no interpolation across voicing gaps."""

import numpy as np
from .errors import VocalScopeError


def align_frames(times: np.ndarray, f0: np.ndarray, voiced: np.ndarray, reference_times: np.ndarray,
                 duration_seconds: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest actual frame center, ties earlier. No extrapolation past first/last
    prediction or audio duration; outside coverage is unvoiced, counted as a miss.
    No interpolation is applied to pitch, including at voiced/unvoiced boundaries.
    """
    times, reference_times = np.asarray(times), np.asarray(reference_times)
    if not len(times) or np.any(np.diff(times) <= 0) or len(f0) != len(times) or len(voiced) != len(times):
        raise ValueError('Predictions must have ordered, aligned frames.')
    right = np.clip(np.searchsorted(times, reference_times), 0, len(times)-1)
    left = np.maximum(0, right-1)
    indices = np.where(np.abs(reference_times-times[left]) <= np.abs(times[right]-reference_times), left, right)
    covered = (reference_times >= times[0]) & (reference_times <= times[-1]+1e-10) & (reference_times <= duration_seconds+1e-10)
    v = voiced[indices] & covered & np.isfinite(f0[indices]) & (f0[indices] > 0)
    return np.where(v, f0[indices], 0.0), v, covered


def metrics(reference_hz: np.ndarray, estimated_hz: np.ndarray, estimated_voiced: np.ndarray) -> dict:
    try:
        import mir_eval.melody as melody
    except ImportError as exc:
        raise VocalScopeError("Scientific evaluation requires vocalscope[benchmark] (mir_eval).") from exc
    ref, est, ev = np.asarray(reference_hz), np.asarray(estimated_hz), np.asarray(estimated_voiced, dtype=bool)
    if ref.shape != est.shape or ev.shape != ref.shape or not len(ref):
        raise ValueError('Metric arrays must be nonempty and aligned.')
    if not np.all(np.isfinite(ref)) or np.any(ref < 0) or np.any(ev & (~np.isfinite(est) | (est <= 0))):
        raise ValueError('Reference Hz must be finite/nonnegative; voiced estimates must be positive/finite.')
    rv = ref > 0
    common = rv & ev
    errors = 1200*np.log2(est[common]/ref[common])
    absolute = np.abs(errors)
    rc, ec = melody.hz2cents(ref), melody.hz2cents(np.where(ev, est, 0.0))
    nv, nu, ne, nc = int(rv.sum()), int((~rv).sum()), int(ev.sum()), int(common.sum())
    fp, fn = int((~rv & ev).sum()), int((rv & ~ev).sum())
    # mir_eval strict <50 cents. Stage 1's historical <=50 convention remains
    # unchanged in validation.py; this Stage 2 convention is explicitly versioned.
    pitch = int((absolute < 50).sum())
    chroma = int((np.abs(errors - 1200*np.rint(errors/1200)) < 50).sum())
    tn = int((~rv & ~ev).sum())
    octave = int(((np.rint(errors/1200) != 0) & (np.abs(errors-1200*np.rint(errors/1200)) < 50)).sum())
    precision = nc/ne if ne else None
    recall = nc/nv if nv else None
    denominator = 2*nc + fp + fn
    result = {
        'frames': len(ref), 'reference_voiced_frames': nv, 'reference_unvoiced_frames': nu,
        'estimated_voiced_frames': ne, 'mutually_voiced_frames': nc, 'false_positive_frames': fp,
        'false_negative_frames': fn, 'correct_pitch_frames': pitch, 'correct_chroma_frames': chroma,
        'correct_unvoiced_frames': tn, 'octave_error_frames': octave,
        'raw_pitch_accuracy_50c': float(melody.raw_pitch_accuracy(rv, rc, ev, ec)) if nv else None,
        'raw_chroma_accuracy': float(melody.raw_chroma_accuracy(rv, rc, ev, ec)) if nv else None,
        'voicing_recall': recall, 'voicing_false_alarm_rate': fp/nu if nu else None,
        'voicing_precision': precision, 'voicing_f1': 2*nc/denominator if denominator else None,
        'overall_accuracy': float(melody.overall_accuracy(rv, rc, ev, ec)),
        'median_absolute_error_cents': float(np.median(absolute)) if nc else None,
        'mean_absolute_error_cents': float(np.mean(absolute)) if nc else None,
        'p90_absolute_error_cents': float(np.percentile(absolute,90)) if nc else None,
        'p95_absolute_error_cents': float(np.percentile(absolute,95)) if nc else None,
        'octave_error_rate': octave/nc if nc else None,
    }
    return result


def aggregate(aligned: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> dict:
    if not aligned:
        return {'frame_weighted': None, 'track_macro': None, 'tracks': 0}
    per_track = [metrics(*a) for a in aligned]
    weighted = metrics(*(np.concatenate([a[i] for a in aligned]) for i in range(3)))
    metric_names = [k for k in weighted if k not in ('frames',) and not k.endswith('_frames')]
    macro = {k: float(np.mean([m[k] for m in per_track if m[k] is not None]))
             if any(m[k] is not None for m in per_track) else None for k in metric_names}
    return {'frame_weighted': weighted, 'track_macro': macro, 'tracks': len(aligned),
            'macro_defined_tracks': {k: sum(m[k] is not None for m in per_track) for k in metric_names}}


def fixed_split(identifiers: list[str], seed: int = 20261109, folds: int | None = None, fold: int = 0) -> dict:
    ids = sorted(set(identifiers))
    if len(ids) != len(identifiers) or len(ids) < 2:
        raise ValueError('Splits need at least two unique tracks.')
    shuffled = np.random.default_rng(seed).permutation(ids).tolist()
    if folds is not None:
        if not 2 <= folds <= len(ids) or not 0 <= fold < folds:
            raise ValueError('Require 2 <= folds <= tracks and 0 <= fold < folds.')
        test = np.array_split(np.asarray(shuffled),folds)[fold].tolist()
    else:
        test = shuffled[len(shuffled)//2:]
    return {'seed':seed,'train':[],'development':sorted(set(ids)-set(test)), 'test':sorted(test),
            'folds':folds,'fold':fold,'unit':'whole track; no frame-level random split'}


def select_threshold(dev_predictions: list[tuple[np.ndarray, np.ndarray, np.ndarray]], confidence_type: str) -> dict:
    """Input is development-only (reference, candidates, score), already aligned.
    Macro-track F1 is the prespecified objective. Tie break: lowest threshold,
    preferring recall. Callers explicitly audit disjoint development/test IDs.
    """
    grid = {'pyin_voicing_probability':[0.0,0.01,0.1,0.3,0.5,0.7,0.9],
            'normalized_autocorrelation':[0.3,0.5,0.6,0.7,0.8,0.9],
            'crepe_periodicity':[0.1,0.2,0.3,0.5,0.7,0.9]}[confidence_type]
    rows=[]
    for threshold in grid:
        evaluated=[]
        for ref, candidate, score in dev_predictions:
            v = np.isfinite(candidate) & (candidate>0) & (score>=threshold) & (score>0)
            evaluated.append((ref,np.where(v,candidate,0),v))
        summary=aggregate(evaluated)
        rows.append({'threshold':threshold,**summary})
    valid=[r for r in rows if r['track_macro'] and r['track_macro']['voicing_f1'] is not None]
    selected=max(valid,key=lambda r:(r['track_macro']['voicing_f1'],-r['threshold']))['threshold'] if valid else None
    return {'confidence_type':confidence_type,'objective':'development track-macro voicing F1; ties choose lower threshold',
            'selected_threshold':selected,'development_precision_recall':rows}

