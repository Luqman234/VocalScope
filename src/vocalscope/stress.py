# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Additional deterministic acoustic stress signals; analytic truth, not model labels."""

import numpy as np
from scipy.signal import butter,sosfilt
from .models import AnalysisConfig
from .validation import CASE_NAMES,SyntheticCase,make_case,phase_signal


def stress_cases(sample_rate: int = 22050) -> list[SyntheticCase]:
    cases=[make_case(name,duration=3 if name=='silence_gap' else 2,sr=sample_rate)
           for name in CASE_NAMES if not name.startswith('noise_snr_') and name!='noise_only']
    sr=sample_rate;t=np.arange(2*sr)/sr
    mask=lambda x:(x>=.25)&(x<=1.75)
    voiced=lambda x:np.full_like(x,220.)
    unvoiced=lambda x:np.full_like(x,np.nan)
    clean=phase_signal(np.full_like(t,220.),sr,(.35,.65,.5))
    cases.append(SyntheticCase('snr_clean',clean,sr,voiced,mask,'Clean reference for the multi-seed noise study'))
    for seed in (7,91,20261109):
        rng=np.random.default_rng(seed);noise=rng.normal(size=len(t))
        for snr in (20,10,5,0):
            mixed=clean+noise*np.sqrt(np.mean(clean**2)/np.mean(noise**2))*10**(-snr/20)
            cases.append(SyntheticCase(f'snr_{snr}_seed_{seed}',mixed,sr,voiced,mask,f'{snr} dB RMS SNR, seed {seed}'))
        cases.append(SyntheticCase(f'white_seed_{seed}',.1*noise,sr,unvoiced,mask,'Unpitched white Gaussian noise'))
        frequencies=np.fft.rfftfreq(len(t),1/sr)
        spectrum=np.fft.rfft(noise)/np.sqrt(np.maximum(frequencies,1))
        spectrum[0]=0
        pink=np.fft.irfft(spectrum,n=len(t));pink*=.1/np.sqrt(np.mean(pink**2))
        cases.append(SyntheticCase(f'pink_seed_{seed}',pink,sr,unvoiced,mask,'Unpitched 1/f-power noise'))
        breath=sosfilt(butter(4,[300,6000],fs=sr,btype='bandpass',output='sos'),noise)*np.sin(np.pi*t/2)**2
        breath*=.1/np.sqrt(np.mean(breath**2))
        cases.append(SyntheticCase(f'breath_seed_{seed}',breath,sr,unvoiced,mask,'Bandlimited envelope-shaped noise; synthetic breath-like, not human breath'))
    transient=np.zeros_like(t);begin=int(.99*sr);length=int(.02*sr)
    transient[begin:begin+length]=np.random.default_rng(7).normal(0,.2,length)
    cases.append(SyntheticCase('short_transient',transient,sr,unvoiced,mask,'20 ms unpitched noise burst'))
    falling=lambda x:440*np.exp2(-x/2)
    cases.append(SyntheticCase('falling_glissando',phase_signal(falling(t),sr),sr,falling,mask,'440→220 Hz exponential slide, integrated phase'))
    config=AnalysisConfig()
    for name,hz in [('below_lower',config.fmin*2**(-10/1200)),('above_lower',config.fmin*2**(10/1200)),
                    ('below_upper',config.fmax*2**(-10/1200)),('above_upper',config.fmax*2**(10/1200))]:
        truth=lambda x,hz=hz:np.full_like(x,hz)
        cases.append(SyntheticCase(name,phase_signal(truth(t),sr),sr,truth,mask,'±10 cents around configured pitch boundary; out-of-range truth is retained'))
    return cases

