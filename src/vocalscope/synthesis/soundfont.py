# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Explicit path -> application settings -> structurally verified system font.

No downloads; no paths from transcription source metadata are opened here.
"""
from pathlib import Path
import hashlib,json,os,stat,struct
from .models import RenderConfig,SynthesisError

SYSTEM_FONTS=(Path('/usr/share/soundfonts/FluidR3_GM.sf2'),Path('/usr/share/soundfonts/FluidR3_GM.sf3'),Path('/usr/share/sounds/sf2/FluidR3_GM.sf2'),Path('/usr/share/sounds/sf2/TimGM6mb.sf2'),Path('/usr/share/soundfonts/default.sf2'))


def settings_path():
    return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'vocalscope'/'synthesis.json'


def validate_soundfont(path,config=None,*,hash_file=True):
    config=config or RenderConfig();path=Path(path).expanduser().resolve()
    try:
        info=path.stat()
        if not stat.S_ISREG(info.st_mode):raise SynthesisError('SoundFont must be a regular file.')
        if not 12<=info.st_size<=config.max_soundfont_mb*1024**2:raise SynthesisError('SoundFont is empty or exceeds the file-size limit.')
        if path.suffix.lower() not in ('.sf2','.sf3'):raise SynthesisError('Choose an SF2 or SF3 SoundFont.')
        with path.open('rb') as stream:
            header=stream.read(12)
            if header[:4]!=b'RIFF' or header[8:]!=b'sfbk' or struct.unpack('<I',header[4:8])[0]+8!=info.st_size:raise SynthesisError('Invalid SoundFont RIFF/sfbk container or size.')
            digest=hashlib.sha256();digest.update(header)
            if hash_file:
                for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        result={'path':str(path),'size_bytes':info.st_size,'mtime_ns':info.st_mtime_ns,'sha256':digest.hexdigest() if hash_file else None,
            'license':'SoundFont sample licensing is separate; supplied externally. Verify the font license before redistribution.'}
        return result
    except OSError as exc:raise SynthesisError(f'Cannot read SoundFont {path}: {exc}') from exc


def resolve_soundfont(explicit=None,*,settings_file=None,config=None):
    if explicit is not None:return Path(validate_soundfont(explicit,config,hash_file=False)['path'])
    settings=Path(settings_file) if settings_file else settings_path()
    if settings.exists():
        if not settings.is_file() or settings.stat().st_size>65536:raise SynthesisError('Invalid or oversized synthesis settings file.')
        try:
            values=json.loads(settings.read_text());configured=values.get('soundfont_path')
            if configured is not None:
                if not isinstance(configured,str) or not configured:raise ValueError('soundfont_path must be a path string.')
                return Path(validate_soundfont(configured,config,hash_file=False)['path'])
        except (ValueError,TypeError,AttributeError) as exc:raise SynthesisError(f'Invalid synthesis settings: {exc}') from exc
    for candidate in SYSTEM_FONTS:
        if candidate.is_file():
            try:return Path(validate_soundfont(candidate,config,hash_file=False)['path'])
            except SynthesisError:continue
    raise SynthesisError('A piano SoundFont is required. Pass --soundfont /path/to/piano.sf2, set soundfont_path in '+str(settings)+', or install Arch soundfont-fluid.')
