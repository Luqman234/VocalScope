# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Bounded programmatic transport diagnostic; wall time is measurement only."""
from dataclasses import asdict
from pathlib import Path
from time import monotonic,sleep
import json
from .models import Session,Source,PlaybackConfig,State
from .transport import Transport


def run_playback_test(vocal,piano,output,*,sink='fakesink',seconds=1.,master_gain=.05):
    if not .2<=seconds<=30:raise ValueError('Diagnostic duration must be 0.2–30 seconds.')
    output=Path(output).expanduser().resolve()
    if output in [Path(p).expanduser().resolve() for p in (vocal,piano) if p]:raise ValueError('Diagnostic output must not replace either audio source.')
    transport=Transport(PlaybackConfig(sink=sink,master_gain=master_gain));rows=[];timings={};start=monotonic()
    try:
        begin=monotonic();transport.load(Session(Source(vocal) if vocal else None,Source(piano) if piano else None)).result(15);timings['load_seconds']=monotonic()-begin
        begin=monotonic();transport.play().result(5);timings['play_ack_seconds']=monotonic()-begin
        deadline=monotonic()+seconds
        while monotonic()<deadline:rows.append(asdict(transport.snapshot()));sleep(.02)
        transport.pause().result(5);paused=transport.snapshot().position_seconds;sleep(.1);pause_drift=transport.snapshot().position_seconds-paused
        targets=[.1,min(.5,transport.snapshot().duration_seconds/2)]
        seeks=[]
        for target in targets:
            begin=monotonic();transport.seek(target).result(10);seeks.append({'target':target,'position':transport.snapshot().position_seconds,'ack_seconds':monotonic()-begin})
        if vocal and piano:
            transport.play().result(5)
            for mode in ('vocal','piano','mix'):
                before=transport.snapshot().position_seconds;transport.set_mix(mode).result(5);sleep(.05);rows.append(asdict(transport.snapshot()))
                if transport.snapshot().position_seconds<before-.02:raise RuntimeError('Source switching reset the media timeline.')
        diagnostics=transport.diagnostics().result(3);diagnostics['snapshot']=asdict(diagnostics['snapshot'])
        report={'schema_version':'1.0.0','status':'complete','sink':sink,'timings':timings,'samples':rows,'paused_drift_seconds':pause_drift,'seeks':seeks,'engine':diagnostics,
            'semantics':'Media positions are Gst queries; wall time measures operation completion only. Gst latency query is not physical/acoustic latency.','physical_listening':'not claimed','physical_acoustic_latency':'unverified'}
    finally:
        begin=monotonic();transport.close().result(5);closed=transport.wait_closed(5);cleanup=monotonic()-begin
    if not closed:raise RuntimeError('Playback thread failed to close.')
    report['cleanup_seconds']=cleanup;report['elapsed_seconds']=monotonic()-start
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    from ..transcription.serialization import atomic_write
    atomic_write(output,(json.dumps(report,indent=2,allow_nan=False)+'\n').encode(),source=vocal)
    return report
