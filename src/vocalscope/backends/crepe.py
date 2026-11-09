# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Optional CPU torchcrepe adapter. Weights are bundled; no inference downloads."""

from importlib.metadata import version
import hashlib
from pathlib import Path
from time import perf_counter
import numpy as np
from .base import EstimatorConfig, EstimatorOutput
from ..errors import ConfigurationError, VocalScopeError
from ..models import AnalysisConfig, AudioData
from ..preprocessing import resample_audio

_IDENTITIES: dict[str, str] = {}


class CrepeEstimator:
    def analyze(self, audio: AudioData, config: AnalysisConfig, settings: EstimatorConfig) -> EstimatorOutput:
        start = perf_counter()
        try:
            import torch
            import torchcrepe
            if config.fmin < 50 or config.fmax > torchcrepe.MAX_FMAX:
                raise ConfigurationError(f"CREPE bounds must lie in 50–{torchcrepe.MAX_FMAX:g} Hz.")
            torch.set_num_threads(settings.threads)
            torch.use_deterministic_algorithms(True)
            asset = Path(torchcrepe.__file__).parent / "assets" / f"{settings.crepe_model}.pth"
            if not asset.is_file():
                raise VocalScopeError(f"Bundled CREPE weights missing: {asset}. Reinstall torchcrepe; inference never downloads weights.")
            if settings.crepe_model not in _IDENTITIES:
                with asset.open("rb") as stream:
                    _IDENTITIES[settings.crepe_model] = hashlib.file_digest(stream, 'sha256').hexdigest()
            loaded = (getattr(torchcrepe.infer, 'capacity', None) == settings.crepe_model
                      and getattr(getattr(torchcrepe.infer,'model',None),'_vocalscope_verified_sha256',None)==_IDENTITIES[settings.crepe_model])
            if not loaded:
                try:
                    torchcrepe.load.model('cpu', settings.crepe_model)
                    torchcrepe.infer.model._vocalscope_verified_sha256=_IDENTITIES[settings.crepe_model]
                except BaseException:
                    # Upstream assigns infer.model/capacity before reading the
                    # checkpoint. Never reuse random weights after a failed load.
                    for attribute in ('model','capacity'):
                        if hasattr(torchcrepe.infer,attribute):delattr(torchcrepe.infer,attribute)
                    raise
            torchcrepe.infer.model.eval()
        except Exception as exc:
            raise VocalScopeError(f"Cannot initialize CPU CREPE: {exc}") from exc
        initialization = perf_counter() - start
        start = perf_counter()
        # Explicit model-rate resampling; upstream normalizes every 1024-sample
        # frame by removing its mean and dividing by max(std, 1e-10).
        y = resample_audio(audio.samples, audio.sample_rate, 16000)
        wave = torch.tensor(y, dtype=torch.float32, device='cpu').unsqueeze(0)
        numpy_state = np.random.get_state()
        try:
            np.random.seed(0)  # upstream cents dither uses scipy.stats / NumPy
            with torch.inference_mode(), torch.random.fork_rng(devices=[]):
                torch.manual_seed(0)
                activations = [torchcrepe.infer(batch, model=settings.crepe_model, device='cpu')
                               for batch in torchcrepe.preprocess(wave, 16000, settings.crepe_hop_length,
                                                                settings.crepe_batch_size, 'cpu', pad=True)]
                # Decode once for the entire recording. Upstream predict decodes
                # each batch separately, making Viterbi output depend on batch size.
                logits = torch.cat(activations, dim=0).T.unsqueeze(0)
                pitch, periodicity = torchcrepe.postprocess(logits, fmin=config.fmin, fmax=config.fmax,
                                                           decoder=torchcrepe.decode.viterbi, return_periodicity=True)
        finally:
            np.random.set_state(numpy_state)
        candidate = pitch.squeeze(0).cpu().numpy().astype(np.float64)
        score = np.clip(periodicity.squeeze(0).cpu().numpy().astype(np.float64), 0, 1)
        # The neural model can assign high periodicity to zeros. Reject only
        # exact-zero-energy frames here; no dBFS gate removes legitimate soft notes.
        padded = np.pad(y, 512)
        frames = np.lib.stride_tricks.sliding_window_view(padded, 1024)[::settings.crepe_hop_length]
        nonzero = np.any(frames != 0, axis=1)
        eligible = nonzero & (candidate >= config.fmin) & (candidate <= config.fmax)
        candidate = np.where(eligible, candidate, np.nan)
        voiced = eligible & (score >= settings.crepe_voicing_threshold)
        times = np.arange(len(candidate), dtype=np.float64) * settings.crepe_hop_length / 16000
        return EstimatorOutput('crepe', version('torchcrepe'), times, candidate, voiced, score,
                               'crepe_periodicity', 16000, initialization, perf_counter() - start,
                               {"algorithm": "torchcrepe.Crepe", "model_variant": settings.crepe_model,
                                "model_sha256": _IDENTITIES[settings.crepe_model], "torch_version": torch.__version__,
                                "inference_device": "cpu", "threads": settings.threads, "weights_reused": loaded,
                                "hop_length": settings.crepe_hop_length, "window_length": 1024,
                                "normalization": "upstream framewise mean removal / max(std, 1e-10)",
                                "resampling": "scipy.signal.resample_poly to 16000 Hz",
                                "decoder": "whole-track upstream Viterbi, no post-smoothing; fixed torch and NumPy RNG seeds 0",
                                "voicing_policy": "periodicity >= configured threshold and nonzero frame energy and in-range candidate",
                                "center": True, "pad_mode": "constant"})

