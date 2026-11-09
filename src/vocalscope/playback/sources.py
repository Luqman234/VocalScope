# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Discover local audio without touching transcription/F0 or modifying files."""
import stat
import numpy as np
import soundfile as sf
from .gst import bindings
from .models import PlaybackError


def discover(source):
    Gst,_,_,Pb=bindings();path=source.path
    if not path.exists() or not stat.S_ISREG(path.stat().st_mode):raise PlaybackError(f'Missing regular audio file: {path}')
    discoverer=Pb.Discoverer.new(5*Gst.SECOND)
    try:info=discoverer.discover_uri(path.as_uri())
    except Exception as exc:raise PlaybackError(f'Cannot decode {path.name}: {exc}') from exc
    if info.get_result()!=Pb.DiscovererResult.OK or not info.get_audio_streams():raise PlaybackError(f'Unsupported or damaged audio: {path}')
    duration=info.get_duration()/Gst.SECOND
    if duration<=0 or duration>3600:raise PlaybackError('Playback supports nonempty local audio up to 3600 seconds.')
    # Reject malformed float containers before initializing a native sink.
    # Integer PCM is finite by construction. Other installed Gst decoders are
    # still allowed; the output probe also checks their decoded/mixed PCM.
    try:
        with sf.SoundFile(path) as stream:
            if stream.subtype in ('FLOAT','DOUBLE'):
                for block in stream.blocks(blocksize=65536,dtype='float32',always_2d=True):
                    if not np.isfinite(block).all():raise PlaybackError('Audio contains non-finite PCM; playback refused.')
    except sf.LibsndfileError:pass
    audio=info.get_audio_streams()[0]
    return {'path':str(path),'uri':path.as_uri(),'duration_seconds':duration,'channels':audio.get_channels(),'sample_rate':audio.get_sample_rate(),'offset_seconds':source.offset_seconds}
