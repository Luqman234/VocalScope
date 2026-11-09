# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Real human-project edit/undo/redo/render/swap stress, without GTK or audio device."""
import argparse,json,gc
from pathlib import Path
from time import monotonic,sleep
import psutil
from vocalscope.transcription.serialization import load_project
from vocalscope.synthesis.project import project_snapshot
from vocalscope.synthesis.models import RenderConfig
from vocalscope.playback.render_coordinator import RenderCoordinator
from vocalscope.playback.transport import Transport
from vocalscope.playback.models import *


def wait(predicate,timeout=12):
 deadline=monotonic()+timeout
 while not predicate() and monotonic()<deadline:sleep(.005)
 if not predicate():raise TimeoutError('Edit soak')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cycles',type=int,default=12);args=parser.parse_args()
 p=load_project('results/stage3-human-pyin/vocadito_1.notes.json');c=RenderCoordinator();t=Transport(PlaybackConfig(sink='fakesink'));process=psutil.Process();rows=[];root=c.root;notes=p.notes;failure=None
 try:
  t.load(Session(vocal=Source('data/vocadito/Audio/vocadito_1.wav'),piano=Source('results/stage4a-release-piano/piano.wav'))).result(9);t.set_mix('mix').result(3)
  for i in range(args.cycles):
   start=monotonic();identifier=p.notes[0].note_id;p.edit(identifier,midi_note=notes[0].midi_note+1);c.request(project_snapshot(p),'data/soundfonts/TimGM6mb.sf2',RenderConfig(sample_rate=48000,normalize_peak=True))
   p.undo();c.request(project_snapshot(p),'data/soundfonts/TimGM6mb.sf2',RenderConfig(sample_rate=48000,normalize_peak=True))
   p.redo();revision=c.request(project_snapshot(p),'data/soundfonts/TimGM6mb.sf2',RenderConfig(sample_rate=48000,normalize_peak=True));wait(lambda:c.status().validated_revision==revision)
   render=monotonic()-start
   if i%2:t.pause().result(3)
   else:t.play().result(3)
   position=t.snapshot().position_seconds;assert c.pin(revision);token=c.activation_token(revision)
   if i%4==0:
    c.cancel();c.resume_current()
    try:t.replace_piano(Source(c.files[revision]['path']),revision,accept=lambda:c.commit(revision,token)).result(8)
    except Superseded:pass
    else:raise AssertionError('Cancelled token activated')
    token=c.activation_token(revision)
   begin=monotonic();t.replace_piano(Source(c.files[revision]['path']),revision,accept=lambda:c.commit(revision,token)).result(8);swap=monotonic()-begin;c.unpin(revision)
   assert t.snapshot().piano_revision==revision and not c.pins
   rows.append(dict(cycle=i,render_with_obsolete_cancellation_seconds=render,swap_seconds=swap,position_error_seconds=t.snapshot().position_seconds-position,
    rss_bytes=process.memory_info().rss,fd_count=process.num_fds(),children=len(process.children()),discarded=c.status().discarded_revisions,owned_render_directories=len(list(c.root.glob('revision-*')))))
  wait(lambda:not c.status().in_progress)
 except Exception as exc:failure=repr(exc)
 finally:t.close().result(6);assert t.wait_closed();c.close();gc.collect()
 report=dict(status='failed' if failure else 'complete',error=failure,rows=rows,discarded_revisions=c.status().discarded_revisions,temporary_root_removed=not root.exists(),children_after_cleanup=len(process.children()))
 args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(args.output)
 if failure:raise RuntimeError(failure)


if __name__=='__main__':main()
