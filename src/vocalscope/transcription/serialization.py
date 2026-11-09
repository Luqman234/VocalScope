# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Versioned self-contained projects; validated snapshot journal, atomic files."""
import csv,io,json,os,tempfile
from pathlib import Path
from dataclasses import asdict
from ..export import result_document,result_from_document
from .models import TranscriptionConfig,TranscriptionResult,NoteEvent,Boundary,validate_notes
from . import ALGORITHM_VERSION

SCHEMA_VERSION='1.0.0'


def document(project):
    return {'schema_version':SCHEMA_VERSION,'kind':'vocalscope.transcription','algorithm_version':project.algorithm_version,
        'source_sha256':project.source_sha256,'acoustic':result_document(project.acoustic),
        'configuration':asdict(project.config),'generated_notes':[asdict(n) for n in project.generated_notes],
        'notes':[asdict(n) for n in project.notes],'boundaries':[asdict(b) for b in project.boundaries],
        'timings':project.timings,'journal':project.journal,'cursor':project.cursor,
        'semantics':{'overlap':'strictly monophonic, touching intervals allowed','source_frames':'half-open; edited splits retain parent interval flagged explicitly',
        'midi_pitch':'measured fractional MIDI center; manual key edits change midi_note only','velocity':'constant default 80, not inferred piano intent',
        'acoustic':'immutable F0 with original NaN gaps represented as JSON null','journal':'before/after validated note snapshots; cursor selects applied prefix'}}


def from_document(d):
    if d.get('schema_version')!=SCHEMA_VERSION or d.get('kind')!='vocalscope.transcription':raise ValueError('Unsupported transcription project schema.')
    acoustic=result_from_document(d['acoustic'])
    identity=d['source_sha256']
    if not isinstance(identity,str) or len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid audio identity hash.')
    p=TranscriptionResult(acoustic,identity,TranscriptionConfig(**d['configuration']),[NoteEvent(**n) for n in d['generated_notes']],
        [Boundary(**b) for b in d['boundaries']],d.get('timings'))
    p.algorithm_version=d['algorithm_version']
    if not isinstance(p.algorithm_version,str) or not p.algorithm_version:raise ValueError('Invalid segmentation version.')
    journal=d.get('journal',[]);cursor=d.get('cursor',0)
    if type(cursor) is not int or not 0<=cursor<=len(journal):raise ValueError('Invalid edit cursor.')
    previous=p.generated_notes
    for item in journal:
        before=validate_notes([NoteEvent(**n) for n in item['before']],p.duration)
        after=validate_notes([NoteEvent(**n) for n in item['after']],p.duration)
        if any(n.source_end_frame is not None and n.source_end_frame>len(acoustic.time_seconds) for n in (*before,*after)):raise ValueError('Edited source interval exceeds acoustic analysis.')
        if before!=previous or item['operation'] not in ('add','edit','delete','split','merge'):raise ValueError('Broken edit journal chain.')
        previous=after
    expected=p.generated_notes if cursor==0 else validate_notes([NoteEvent(**n) for n in journal[cursor-1]['after']],p.duration)
    actual=validate_notes([NoteEvent(**n) for n in d['notes']],p.duration)
    if expected!=actual:raise ValueError('Project notes disagree with edit journal.')
    p.notes=actual;p.journal=journal;p.cursor=cursor
    return p


def atomic_write(path,data,*,overwrite=False,source=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if source and path.resolve()==Path(source).resolve():raise ValueError('Cannot overwrite source recording.')
    fd,name=tempfile.mkstemp(prefix='.vocalscope-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        if overwrite:os.replace(name,path)
        else:
            # Atomic no-clobber publication, including a concurrently created file.
            os.link(name,path);os.unlink(name)
    finally:
        if os.path.exists(name):os.unlink(name)
    return path


def save_project(p,path,*,overwrite=False):
    return atomic_write(path,(json.dumps(document(p),indent=2,allow_nan=False)+'\n').encode(),overwrite=overwrite,source=p.acoustic.metadata.path)


def load_project(path):
    try:
        return from_document(json.loads(Path(path).read_text(),parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON literal.'))))
    except (KeyError,TypeError) as exc:raise ValueError(f'Damaged transcription project: {exc}') from exc


def export_bundle(p,directory,*,overwrite=False):
    from .midi_export import midi_bytes
    from .plotting import figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    directory=Path(directory);stem=Path(p.acoustic.metadata.filename).stem+'.notes'
    table=io.StringIO();fields=list(NoteEvent.__dataclass_fields__)
    writer=csv.DictWriter(table,fieldnames=fields);writer.writeheader()
    for n in p.notes:
        row=asdict(n);row['flags']=json.dumps(row['flags']);writer.writerow(row)
    fig=figure(p);png=io.BytesIO();FigureCanvasAgg(fig).print_png(png)
    payload={'json':(json.dumps(document(p),indent=2,allow_nan=False)+'\n').encode(),'csv':table.getvalue().encode(),'mid':midi_bytes(p.notes),'png':png.getvalue()}
    paths={ext:directory/f'{stem}.{ext}' for ext in payload}
    if not overwrite and any(path.exists() for path in paths.values()):raise FileExistsError('Transcription outputs already exist; choose a new directory or --overwrite.')
    for ext,data in payload.items():atomic_write(paths[ext],data,overwrite=overwrite,source=p.acoustic.metadata.path)
    return paths
