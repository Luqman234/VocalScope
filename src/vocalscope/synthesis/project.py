# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Read-only Stage 3 integration. No original audio or estimator is opened."""
from dataclasses import asdict
import hashlib,json,stat
from pathlib import Path
from ..transcription.serialization import from_document
from .models import SynthesisError
from .export import note_identity

MAX_PROJECT_BYTES=64*1024**2


def project_snapshot(project):
    return {'notes':[asdict(n) for n in project.notes],'duration_seconds':project.duration,
        'provenance':{'source_audio_sha256':project.source_sha256,'estimator_id':project.acoustic.estimator_id,
            'estimator_version':project.acoustic.estimator_version,'estimator_configuration':project.acoustic.estimator_configuration,
            'analysis_configuration':asdict(project.acoustic.config),'transcription_algorithm_version':project.algorithm_version,
            'transcription_configuration':asdict(project.config),'edit_cursor':project.cursor,'journal_entries':len(project.journal),
            'notes_sha256':note_identity(project.notes)},
        # Only compare this string against output paths. Never decode, hash or
        # follow source audio paths from a project while rendering.
        'protected_source_path':project.acoustic.metadata.path}


def read_project_snapshot(path):
    path=Path(path).expanduser().resolve()
    try:
        if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size>MAX_PROJECT_BYTES:raise SynthesisError('Project must be a regular JSON file <=64 MiB.')
        with path.open('rb') as stream:data=stream.read(MAX_PROJECT_BYTES+1)
        if len(data)>MAX_PROJECT_BYTES:raise SynthesisError('Project exceeds 64 MiB.')
        doc=json.loads(data,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite JSON literal.')))
        if not isinstance(doc,dict):raise ValueError('Expected a project object.')
        snapshot=project_snapshot(from_document(doc))
        snapshot['provenance'].update({'project_path':str(path),'project_sha256':hashlib.sha256(data).hexdigest()})
        return snapshot
    except (ValueError,KeyError,TypeError,AttributeError,OSError) as exc:raise SynthesisError(f'Cannot load transcription project {path}: {exc}') from exc
