# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Bounded disk-spooled WAV/FLAC encoding, read-back validation, safe publication."""
from dataclasses import asdict
import hashlib,json,os,shutil,tempfile,resource
from pathlib import Path
from time import perf_counter
import numpy as np
import soundfile as sf
from .models import RenderConfig,SynthesisError,check_cancelled
from .renderer import stream_notes
from .scheduler import schedule_notes
from .diagnostics import WaveformDiagnostics

FORMATS={'wav':('WAV','FLOAT'),'flac':('FLAC','PCM_24')}


def validate_formats(formats):
    formats=tuple(formats)
    if not formats or len(set(formats))!=len(formats) or set(formats)-set(FORMATS):raise ValueError('Choose one or both formats: wav, flac.')
    return formats


def note_identity(notes):
    return hashlib.sha256(json.dumps([asdict(n) for n in notes],sort_keys=True,allow_nan=False).encode()).hexdigest()


def verify_audio(path,config,expected_frames,*,nonempty=False,cancelled=None):
    diagnostic=WaveformDiagnostics(config.sample_rate)
    try:
        with sf.SoundFile(path) as source:
            if source.samplerate!=config.sample_rate or source.channels!=2 or source.frames!=expected_frames:raise SynthesisError('Export read-back metadata disagrees with the scheduled render.')
            info={'format':source.format,'subtype':source.subtype,'frames':source.frames,'sample_rate':source.samplerate,'channels':source.channels}
            while True:
                check_cancelled(cancelled);block=source.read(config.chunk_frames,dtype='float32',always_2d=True)
                if not len(block):break
                diagnostic.add(block)
    except (sf.LibsndfileError,OSError) as exc:raise SynthesisError(f'Cannot reopen rendered audio: {exc}') from exc
    stats=diagnostic.result()
    if stats['frames']!=expected_frames:raise SynthesisError('Decoder returned a truncated render.')
    if nonempty and stats['peak_absolute']==0:raise SynthesisError('Encoded notes are silent; gain may be below the selected PCM precision.')
    return {**info,'duration_seconds':expected_frames/config.sample_rate,'diagnostics':stats}


def stage_render(notes,soundfont,config,workdir,*,formats=('wav','flac'),duration_seconds=None,provenance=None,cancelled=None):
    """Prepare a complete bundle privately. This function never publishes files."""
    begin=perf_counter();notes=tuple(notes);formats=validate_formats(formats);workdir=Path(workdir)
    workdir.mkdir(parents=True,exist_ok=True)
    plan=schedule_notes(notes,config,duration_seconds=duration_seconds)
    needed=int(plan.frames*(8+sum(8 if f=='wav' else 7 for f in formats))*1.05)+1024**2
    if shutil.disk_usage(workdir).free<needed:raise SynthesisError('Insufficient disk space for the bounded-memory render spool and output files.')
    raw_path=workdir/'samples.raw'
    with sf.SoundFile(raw_path,'w',samplerate=config.sample_rate,channels=2,format='RAW',subtype='FLOAT',endian='LITTLE') as spool:
        report=stream_notes(notes,soundfont,config,spool.write,duration_seconds=duration_seconds,cancelled=cancelled)
    peak=report['diagnostics']['peak_absolute'];factor=config.peak_target/peak if config.normalize_peak and peak>0 else 1.
    if 'flac' in formats and peak*factor>=1:raise SynthesisError('FLAC integer PCM would clip at this gain. Lower --gain, explicitly use --normalize-peak, or export float WAV only.')
    report['normalization']={'enabled':config.normalize_peak,'factor':factor,'target':config.peak_target if config.normalize_peak else None}
    report['provenance']=dict(provenance or {})
    report['rendered_notes']=[asdict(n) for n in notes]
    report['rendered_notes_sha256']=note_identity(notes)
    report['files']={};staged={};timings=report['timings']
    for kind in formats:
        check_cancelled(cancelled);start=perf_counter();path=workdir/f'piano.{kind}';file_format,subtype=FORMATS[kind]
        with sf.SoundFile(raw_path,'r',samplerate=config.sample_rate,channels=2,format='RAW',subtype='FLOAT',endian='LITTLE') as source, sf.SoundFile(path,'w',samplerate=config.sample_rate,channels=2,format=file_format,subtype=subtype) as destination:
            while True:
                check_cancelled(cancelled);block=source.read(config.chunk_frames,dtype='float32',always_2d=True)
                if not len(block):break
                if factor!=1:block=(block.astype(np.float64)*factor).astype(np.float32)
                destination.write(block)
            destination.flush()
        timings[f'{kind}_encoding_seconds']=perf_counter()-start
        start=perf_counter();info=verify_audio(path,config,plan.frames,nonempty=bool(notes),cancelled=cancelled)
        if info['format']!=file_format or info['subtype']!=subtype:raise SynthesisError('Encoder used an unexpected audio representation.')
        timings[f'{kind}_verification_seconds']=perf_counter()-start
        info['filename']=path.name;info['size_bytes']=path.stat().st_size
        info['precision']='IEEE float32; retains finite values above full scale' if kind=='wav' else 'Lossless FLAC of quantized signed PCM24, not lossless float32; <=1 PCM24 LSB quantization error when in range'
        report['files'][kind]=info;staged[kind]=str(path)
    raw_path.unlink()
    timings['end_to_end_prepublication_seconds']=perf_counter()-begin
    report['resources']={'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'pcm_chunk_frames':config.chunk_frames,'pcm_chunk_bytes':config.chunk_frames*8,'memory_semantics':'process high water including imports and SoundFont; excludes kernel disk cache and GUI parent'}
    report['versions']={'numpy':np.__version__,'soundfile':sf.__version__,'libsndfile':sf.__libsndfile_version__}
    report['semantics']={'tail':'Fixed bounded duration after content end, never a changed MIDI offset; residual tail energy reported',
        'empty':'Pure silence for requested content duration plus tail; at least one frame if both are zero',
        'timing':'Scheduled rounding <=0.5 sample; FluidSynth internal buffer and SoundFont attack are separate latency sources',
        'diagnostics':'Top-level diagnostics describe raw synthesis before optional normalization; each encoded file has its own decoded diagnostics',
        'streaming':'Disk float32 spool plus fixed-size blocks; output size does not allocate a full PCM array in RAM'}
    manifest=workdir/'render.json';manifest.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');staged['json']=str(manifest)
    for path in staged.values():
        with open(path,'rb') as stream:os.fsync(stream.fileno())
    return report,staged


def publish_render(staged,directory,*,protected_paths=(),cancelled=None):
    """No-clobber links; rollback only files created by this publication.

    Manifest is published last. Cancellation before it rolls back new links;
    a crash/power loss during publication can leave a partial unclaimed bundle.
    """
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    protected={Path(p).expanduser().resolve() for p in protected_paths if p}
    targets={kind:directory/Path(path).name for kind,path in staged.items()}
    if any(p.resolve() in protected for p in targets.values()):raise SynthesisError('Cannot replace an input project, SoundFont or source recording.')
    if any(p.exists() or p.is_symlink() for p in targets.values()):raise FileExistsError('Piano exports already exist; choose a fresh output folder. Existing files are protected.')
    created=[]
    try:
        for kind in [k for k in staged if k!='json']+['json']:
            check_cancelled(cancelled);source=Path(staged[kind]);target=targets[kind]
            os.link(source,target);created.append((target,source.stat().st_ino))
        return {k:str(v) for k,v in targets.items()}
    except BaseException:
        for target,inode in reversed(created):
            try:
                if target.lstat().st_ino==inode:target.unlink()
            except FileNotFoundError:pass
        raise


def export_audio(notes,soundfont,directory,config=None,*,formats=('wav','flac'),duration_seconds=None,provenance=None,protected_paths=(),cancelled=None):
    """Public in-process export with deterministic cleanup on Python exceptions."""
    config=config or RenderConfig();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.vocalscope-render-',dir=directory) as work:
        report,staged=stage_render(notes,soundfont,config,work,formats=formats,duration_seconds=duration_seconds,provenance=provenance,cancelled=cancelled)
        paths=publish_render(staged,directory,protected_paths=(*protected_paths,soundfont),cancelled=cancelled)
    return {'report':report,'paths':paths}
