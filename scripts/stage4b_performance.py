# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Bounded CPU/RSS/transport measurements; no independent playback timer."""
import argparse
from dataclasses import asdict
import hashlib,json,platform,tempfile
from pathlib import Path
from time import monotonic,sleep
import numpy as np
import psutil
import soundfile as sf
from vocalscope.playback.models import PlaybackConfig,Session,Source,State
from vocalscope.playback.transport import Transport
from vocalscope.playback.render_coordinator import RenderCoordinator
from vocalscope.synthesis.project import read_project_snapshot
from vocalscope.synthesis.models import RenderConfig


def wait(predicate,timeout=20):
    deadline=monotonic()+timeout
    while not predicate() and monotonic()<deadline:sleep(.01)
    if not predicate():raise RuntimeError('Performance operation timed out')


def timed(operation):
    start=monotonic();value=operation();return monotonic()-start,value


def measure_cpu(process,seconds,transport=None):
    process.cpu_percent(None);start=monotonic();rss=process.memory_info().rss;positions=[]
    while monotonic()-start<seconds:
        rss=max(rss,process.memory_info().rss)
        if transport:positions.append(asdict(transport.snapshot()))
        sleep(.02)
    return {'elapsed_seconds':monotonic()-start,'cpu_percent_one_core_100':process.cpu_percent(None),
            'sampled_peak_process_rss_bytes':rss,'position_start':positions[0] if positions else None,'position_end':positions[-1] if positions else None}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--sink',default='fakesink',choices=['fakesink','pipewiresink','pulsesink']);p.add_argument('--soundfont',type=Path,required=True)
    p.add_argument('--project',type=Path,default=Path('results/stage3-human-pyin/vocadito_1.notes.json'))
    p.add_argument('--vocal',type=Path,default=Path('data/vocadito/Audio/vocadito_1.wav'));p.add_argument('--piano',type=Path,default=Path('results/stage4a-release-piano/piano.wav'));args=p.parse_args()
    report={'schema_version':'1.0.0','sink':args.sink,'platform':platform.platform(),'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),platform.processor()),'rows':[]}
    process=psutil.Process();t=Transport(PlaybackConfig(sink=args.sink,master_gain=.03 if args.sink!='fakesink' else .8));c=None
    try:
        report['idle_empty']=measure_cpu(process,1.2,t)
        load,_=timed(lambda:t.load(Session(vocal=Source(args.vocal),piano=Source(args.piano))).result(15));report['human_load_seconds']=load
        report['idle_ready']=measure_cpu(process,1.2,t)
        startup,_=timed(lambda:t.play().result(5));report['playing_ack_seconds']=startup
        report['vocal_playing']=measure_cpu(process,2,t)
        t.set_mix('mix').result(5);report['mixed_playing']=measure_cpu(process,2,t)
        seek=[]
        for position in [1.,10.,20.,.5]:
            elapsed,_=timed(lambda:t.seek(position).result(5));seek.append({'target_seconds':position,'ack_seconds':elapsed,'query_position_seconds':t.snapshot().position_seconds})
        report['human_seek']=seek;t.pause().result(5)
        report['paused']=measure_cpu(process,1.2,t)
        snapshot=read_project_snapshot(args.project);before=hashlib.sha256(args.project.read_bytes()).hexdigest();c=RenderCoordinator()
        begin=monotonic();revision=c.request(snapshot,args.soundfont,RenderConfig(sample_rate=48000,normalize_peak=True));wait(lambda:c.status().validated_revision==revision);report['human_background_render_validation_seconds']=monotonic()-begin
        assert c.pin(revision);replace_time,_=timed(lambda:t.replace_piano(Source(c.files[revision]['path']),revision,accept=lambda:c.commit(revision)).result(12));c.unpin(revision);report['paused_piano_replacement_seconds']=replace_time
        # Edit only a detached note snapshot; source project stays read-only.
        snapshot['notes'][0]['midi_note']=min(127,snapshot['notes'][0]['midi_note']+1)
        snapshot['notes'][0]['cents_deviation']=100*(snapshot['notes'][0]['midi_pitch']-snapshot['notes'][0]['midi_note']);snapshot['notes'][0]['edited']=True
        t.play().result(4);position=t.snapshot().position_seconds;begin=monotonic();revision=c.request(snapshot,args.soundfont,RenderConfig(sample_rate=48000,normalize_peak=True));wait(lambda:c.status().validated_revision==revision)
        report['edited_background_render_validation_seconds']=monotonic()-begin
        assert c.pin(revision);replace_time,_=timed(lambda:t.replace_piano(Source(c.files[revision]['path']),revision,accept=lambda:c.commit(revision)).result(12));c.unpin(revision)
        report['playing_piano_replacement_seconds']=replace_time;report['playing_position_before_render']=position;report['playing_position_after_replacement']=t.snapshot().position_seconds
        report['source_project_sha256_unchanged']=before==hashlib.sha256(args.project.read_bytes()).hexdigest()
        t.pause().result(4);report['diagnostics']=t.diagnostics().result(4)
        with tempfile.TemporaryDirectory() as temp:
            for duration in [1,5,15,120]:
                path=Path(temp)/f'{duration}.wav'
                with sf.SoundFile(path,'w',samplerate=48000,channels=2,subtype='FLOAT') as output:
                    block=np.zeros((48000,2),dtype='float32')
                    block[:,0]=.02*np.sin(2*np.pi*220*np.arange(48000)/48000)
                    for _ in range(duration):output.write(block)
                load,_=timed(lambda:t.load(Session(vocal=Source(path),piano=Source(path))).result(12));t.set_mix('mix').result(5)
                elapsed,_=timed(lambda:t.play().result(4));sample=measure_cpu(process,3 if duration==120 else min(.5,duration/2),t)
                t.pause().result(4);seek_elapsed,_=timed(lambda:t.seek(duration*.8).result(5))
                report['rows'].append({'source_duration_seconds':duration,'load_seconds':load,'play_ack_seconds':elapsed,'seek_ack_seconds':seek_elapsed,'measurement':sample})
        elapsed,_=timed(lambda:t.close().result(6));assert t.wait_closed();report['shutdown_seconds']=elapsed
        c.close();c=None
        report['peak_process_rss_bytes']=__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss*1024
        report['peak_largest_child_rss_bytes']=__import__('resource').getrusage(__import__('resource').RUSAGE_CHILDREN).ru_maxrss*1024
        report['status']='complete';report['semantics']='CPU 100%=one core; sampled RSS and kernel high-water marks. Playback intervals are bounded, 120s source is not played for 120s. No physical speaker latency measurement.'
    finally:
        t.close().result(6);t.wait_closed()
        if c:c.close()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,default=str,indent=2,allow_nan=False)+'\n');print(args.output)


if __name__=='__main__':main()
