# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Centered audio features on their own grid; scores are relative, not probabilities."""
from dataclasses import dataclass
from time import perf_counter
import librosa
import numpy as np
from scipy.signal import find_peaks
from .models import Boundary


@dataclass(frozen=True)
class AcousticFeatures:
    times: np.ndarray
    flux: np.ndarray
    rms: np.ndarray
    flatness: np.ndarray
    candidates: tuple[Boundary,...]
    configuration: dict
    timings: dict


def extract_features(audio,threshold=.35):
    begin=perf_counter();hop=256;frame=1024
    y=audio.samples;sr=audio.sample_rate
    # librosa's centered STFT and onset_strength(center=True) compensate their
    # own window delay; no additional half-frame timestamp shift is applied.
    spectrum=np.abs(librosa.stft(y,n_fft=frame,hop_length=hop,center=True,pad_mode='constant'))
    power=librosa.power_to_db(spectrum**2,ref=1.,top_db=80)
    flux=librosa.onset.onset_strength(S=power,sr=sr,hop_length=hop,n_fft=frame,center=True)
    rms=librosa.feature.rms(S=spectrum,frame_length=frame,hop_length=hop)[0]
    flatness=librosa.feature.spectral_flatness(S=spectrum)[0]
    times=librosa.frames_to_time(np.arange(len(flux)),sr=sr,hop_length=hop)
    scale=float(np.percentile(flux[flux>0],95)) if np.any(flux>0) else 1.
    relative=flux/max(scale,1e-12)
    extracted=perf_counter();peaks,_=find_peaks(relative,height=threshold,prominence=.175,distance=max(1,int(.06*sr/hop)))
    candidates=[]
    width=max(1,round(.06*sr/hop))
    for p in peaks:
        if times[p]>=audio.metadata.duration_seconds:continue
        before=rms[max(0,p-width):p];after=rms[p:min(len(rms),p+width)]
        # Distinct rearticulation needs an energy rise/dip as well as a flux peak.
        dip=bool(len(before) and len(after) and np.min(before)<.8*np.max(after) and np.max(after)>1e-10)
        if dip:candidates.append(Boundary(float(times[p]),'spectral_flux+energy',float(relative[p]),'articulation'))
    return AcousticFeatures(times,relative,rms,flatness,tuple(candidates),
        {'sample_rate':sr,'hop_length':hop,'frame_length':frame,'center':True,'onset_threshold':threshold,'score':'flux / positive-flux 95th percentile; energy dip < 0.8 of following maximum'},
        {'feature_extraction_seconds':extracted-begin,'onset_detection_seconds':perf_counter()-extracted})
