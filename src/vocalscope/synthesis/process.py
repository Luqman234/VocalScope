# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Parent-owned staging protects outputs even if native code crashes or is killed."""
from dataclasses import asdict
from pathlib import Path
import tempfile
from ..worker import _request_in_process
from ..transcription.models import NoteEvent
from .models import RenderConfig,check_cancelled
from .soundfont import resolve_soundfont
from .export import publish_render,validate_formats


def inspect_in_process(soundfont,config=None,cancelled=None):
    config=config or RenderConfig();path=resolve_soundfont(soundfont,config=config)
    return _request_in_process({'job':'inspect_soundfont','soundfont':str(path),'render_config':asdict(config)},cancelled,lambda value:value)


def render_snapshot_in_process(snapshot,soundfont,directory,config=None,*,formats=('wav','flac'),cancelled=None):
    config=config or RenderConfig();formats=validate_formats(formats)
    # Validate before process creation, without opening source audio metadata.
    notes=tuple(NoteEvent(**n) for n in snapshot['notes'])
    from .scheduler import schedule_notes
    schedule_notes(notes,config,duration_seconds=snapshot['duration_seconds'])
    path=resolve_soundfont(soundfont,config=config);directory=Path(directory).expanduser().resolve();directory.mkdir(parents=True,exist_ok=True)
    expected=[directory/f'piano.{f}' for f in formats]+[directory/'render.json']
    if any(p.exists() or p.is_symlink() for p in expected):raise FileExistsError('Piano exports already exist; choose a fresh output folder.')
    # This directory belongs to the coordinator, not the C-library child. It is
    # cleaned after process wait/kill even when child finally blocks cannot run.
    with tempfile.TemporaryDirectory(prefix='.vocalscope-render-',dir=directory) as work:
        response=_request_in_process({'job':'render_piano','notes':snapshot['notes'],'duration_seconds':snapshot['duration_seconds'],
            'provenance':snapshot['provenance'],'soundfont':str(path),'workdir':work,'formats':formats,'render_config':asdict(config)},cancelled,lambda value:value)
        check_cancelled(cancelled)
        protected=[path,snapshot.get('protected_source_path'),snapshot['provenance'].get('project_path')]
        # Reject unexpected or redirected child paths, including native failures
        # that happen to leave arbitrary JSON text on stdout.
        if not isinstance(response,dict) or not isinstance(response.get('report'),dict) or response['report'].get('status')!='complete' or not isinstance(response.get('staged'),dict):raise ValueError('Incomplete response from render worker.')
        staged=response['staged']
        if set(staged)!=set(formats)|{'json'}:raise ValueError('Invalid render-worker output set.')
        for kind,staged_path in staged.items():
            expected_name='render.json' if kind=='json' else f'piano.{kind}'
            if Path(staged_path).resolve()!=Path(work)/expected_name:raise ValueError('Invalid render-worker staging path.')
        paths=publish_render(staged,directory,protected_paths=protected,cancelled=cancelled)
        return {'report':response['report'],'paths':paths}
