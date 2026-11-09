# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Checksum-pinned Vocadito v3 loader, with no automatic network access."""

from dataclasses import dataclass
import csv
import hashlib
import http.client
from importlib.resources import files
import json
from pathlib import Path
import urllib.request
import shutil
import zipfile

import numpy as np
import soundfile as sf
from .errors import VocalScopeError

SOURCE = "https://zenodo.org/records/5578807"
ARCHIVE_URL = "https://zenodo.org/api/records/5578807/files/vocadito.zip/content"
ARCHIVE_MD5 = "dea40fd18f14d899643c4ba221b33a46"
INDEX_MD5 = "ff83648dc2311c0c11fe8f304bbb62d4"
LICENSE = "CC-BY-4.0"
ATTRIBUTION = "Bittner, Pasalo, Bosch, Meseguer-Brocal, Rubinstein (2021), vocadito v3, doi:10.5281/zenodo.5578807"


def digest(path: Path, algorithm: str = 'sha256') -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


@dataclass(frozen=True)
class VocalTrack:
    track_id: str
    audio_path: Path
    annotation_path: Path
    reference_times: np.ndarray
    reference_f0: np.ndarray  # Original 0 Hz unvoiced convention, unaltered.
    duration_seconds: float
    audio_sha256: str
    annotation_sha256: str
    singer_id: str | None = None


def load_reference(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    try:
        data = np.loadtxt(path, delimiter=',', ndmin=2)
    except (ValueError, OSError) as exc:
        raise VocalScopeError(f"Invalid or missing F0 annotation {path}: {exc}") from exc
    if data.ndim != 2 or data.shape[1] != 2 or len(data) < 2:
        raise VocalScopeError("F0 annotations require at least two time_seconds,frequency_hz rows.")
    t, f = data.T
    if not np.all(np.isfinite(data)) or np.any(np.diff(t) <= 0) or t[0] < 0 or np.any(f < 0):
        raise VocalScopeError("F0 annotations require ordered nonnegative times and finite nonnegative Hz (0 = unvoiced).")
    t.setflags(write=False); f.setflags(write=False)
    return t, f


class Vocadito:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        index_bytes = files('vocalscope').joinpath('resources/vocadito_index_1.0.json').read_bytes()
        if hashlib.md5(index_bytes).hexdigest() != INDEX_MD5:
            raise VocalScopeError("Bundled official Vocadito index checksum mismatch.")
        self.index = json.loads(index_bytes)
        matches = [p for p in (self.root, self.root/'vocadito', self.root/'Vocadito') if (p/'Audio').is_dir()]
        if len(matches) != 1:
            raise VocalScopeError(f"Vocadito not found or ambiguous at {self.root}; run 'vocalscope dataset download --path {self.root}' or supply its extracted root.")
        self.root = matches[0]
        metadata = self.root/'vocadito_metadata.csv'
        expected = self.index['metadata']['vocadito_metadata'][1]
        if not metadata.is_file() or digest(metadata, 'md5') != expected:
            raise VocalScopeError(f"Vocadito metadata missing or damaged: {metadata}")
        with metadata.open(newline='') as stream:
            self.metadata = {r['track_id']: r for r in csv.DictReader(stream)}

    @property
    def track_ids(self) -> list[str]:
        return sorted(self.index['tracks'], key=int)

    def load_track(self, identifier: str) -> VocalTrack:
        if identifier not in self.index['tracks']:
            raise VocalScopeError(f"Unknown Vocadito track {identifier!r}.")
        record = self.index['tracks'][identifier]
        paths = []
        for kind in ('audio', 'f0'):
            relative, checksum = record[kind]
            p = (self.root/relative).resolve()
            if not p.is_relative_to(self.root) or not p.is_file():
                raise VocalScopeError(f"Track {identifier}: missing {kind} file: {p}")
            if digest(p, 'md5') != checksum:
                raise VocalScopeError(f"Track {identifier}: damaged {kind} file (MD5 mismatch): {p}")
            paths.append(p)
        audio, annotation = paths
        times, f0 = load_reference(annotation)
        try:
            info = sf.info(audio)
        except (OSError, sf.LibsndfileError) as exc:
            raise VocalScopeError(f"Track {identifier}: invalid audio: {exc}") from exc
        duration = info.frames / info.samplerate
        if info.frames <= 0 or times[-1] > duration + max(np.median(np.diff(times)), 0.001) + 1e-8:
            raise VocalScopeError(f"Track {identifier}: F0 annotations and audio do not align.")
        return VocalTrack(identifier, audio, annotation, times, f0, duration, digest(audio), digest(annotation),
                          self.metadata.get(identifier, {}).get('singer_id'))

    def identity(self) -> dict:
        return {'dataset': 'vocadito', 'version': 'v3', 'source': SOURCE, 'license': LICENSE,
                'attribution': ATTRIBUTION, 'archive_md5': ARCHIVE_MD5, 'index_md5': INDEX_MD5,
                'annotation_semantics': 'Original frame-level CSV, seconds/Hz; 0 Hz = unvoiced',
                'track_count': len(self.track_ids)}


def download_vocadito(root: str | Path) -> Path:
    """Explicit opt-in download. Verify before extracting; never package media."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root/'vocadito.zip'
    if not archive.exists() or digest(archive, 'md5') != ARCHIVE_MD5:
        temporary = archive.with_suffix('.download')
        if archive.exists() and not temporary.exists():
            archive.replace(temporary)  # explicitly requested repair/resume
        try:
            for attempt in range(6):
                offset=temporary.stat().st_size if temporary.exists() else 0
                request=urllib.request.Request(ARCHIVE_URL,headers={'Range':f'bytes={offset}-'} if offset else {})
                try:
                    with urllib.request.urlopen(request,timeout=60) as response:
                        append=offset>0 and response.status==206
                        if append and not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                            raise VocalScopeError('Unexpected resume range in dataset download.')
                        with temporary.open('ab' if append else 'wb') as output:
                            shutil.copyfileobj(response,output,length=1024*1024)
                except (OSError,http.client.HTTPException):
                    if attempt==5:raise
                    continue
                if digest(temporary,'md5')==ARCHIVE_MD5:break
                # Short transfers can resume. A full-size invalid archive must
                # restart, rather than append corrupt bytes forever.
                if temporary.stat().st_size>=58_492_257:temporary.unlink()
            else:raise VocalScopeError('Vocadito download incomplete after six attempts; rerun to resume the .download file.')
            temporary.replace(archive)
        except (OSError,http.client.HTTPException) as exc:
            raise VocalScopeError(f"Dataset download failed: {exc}") from exc
    with zipfile.ZipFile(archive) as zipped:
        if sum(i.file_size for i in zipped.infolist()) > 512*1024**2:
            raise VocalScopeError("Unexpectedly large dataset archive.")
        for item in zipped.infolist():
            if not (root/item.filename).resolve().is_relative_to(root) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise VocalScopeError("Unsafe archive entry.")
        zipped.extractall(root)
    (root/'ATTRIBUTION.txt').write_text(f'{ATTRIBUTION}\n{SOURCE}\nLicense: {LICENSE}\nhttps://creativecommons.org/licenses/by/4.0/\n')
    return root

