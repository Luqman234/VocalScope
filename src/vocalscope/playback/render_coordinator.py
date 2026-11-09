# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Revision-checked preview renders with explicit decoder file leases.

No GTK calls. Every edit advances revision before debounce/render starts. Native
rendering reuses Stage 4A. Old audio remains leased until replacement reaches a
safe state. Obsolete completion is discarded even if cancellation lost the race.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import RLock,Event
from queue import Queue
import copy,shutil,tempfile
from ..synthesis.process import render_snapshot_in_process
from ..synthesis.models import RenderConfig
from ..synthesis.models import check_cancelled
from ..synthesis.export import verify_audio


@dataclass(frozen=True)
class RenderStatus:
    current_revision: int=0
    requested_revision: int=0
    in_progress: tuple[int,...]=()
    validated_revision: int=0
    active_revision: int=0
    state: str='EMPTY'
    error: str | None=None
    discarded_revisions: int=0


class RenderCoordinator:
    def __init__(self,runner=render_snapshot_in_process):
        self.root=Path(tempfile.mkdtemp(prefix='vocalscope-audition-'));self.runner=runner;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='vocalscope-rerender')
        self.lock=RLock();self.events=Queue();self.current_revision=0;self.requested_revision=0;self.validated_revision=0;self.active_revision=0
        self.snapshot=None;self.jobs={};self.files={};self.pins={};self.closed=False;self.state='EMPTY';self.error=None
        self.epoch=0;self.cancelled_revision=None;self.discarded_revisions=0

    def status(self):
        with self.lock:return RenderStatus(self.current_revision,self.requested_revision,tuple(self.jobs),self.validated_revision,self.active_revision,self.state,self.error,self.discarded_revisions)

    def revise(self,snapshot):
        with self.lock:
            if self.closed:raise RuntimeError('Render coordinator is closed.')
            self.current_revision+=1;self.snapshot=copy.deepcopy(snapshot);self.state='STALE';self.error=None
            self.epoch+=1;self.cancelled_revision=None
            for job in self.jobs.values():job['cancel'].set()
            self._prune();return self.current_revision

    def render_current(self,soundfont,config=None):
        with self.lock:
            if self.closed or self.snapshot is None:raise RuntimeError('No live project revision.')
            revision=self.current_revision
            if revision in self.jobs:
                if self.jobs[revision]['cancel'].is_set():self.jobs[revision]['retry']=(soundfont,config);self.state='WAITING_FOR_CANCEL'
                return revision
            self.resume_current()
            if revision==self.validated_revision:return revision
            snapshot=copy.deepcopy(self.snapshot);config=config or RenderConfig();cancelled=Event();directory=self.root/f'revision-{revision}'
            self.jobs[revision]={'cancel':cancelled,'directory':directory};self.requested_revision=revision;self.state='RENDERING';self.error=None
            def work():
                result=None;error=None
                try:
                    check_cancelled(cancelled)
                    result=self.runner(snapshot,soundfont,directory,config,formats=('wav',),cancelled=cancelled)
                    path=Path(result['paths']['wav']);verify_audio(path,config,result['report']['frames'],nonempty=bool(snapshot['notes']))
                except Exception as exc:error=f'{type(exc).__name__}: {exc}'
                with self.lock:
                    job=self.jobs.pop(revision,{})
                    if self.closed or revision!=self.current_revision or cancelled.is_set():
                        self.discarded_revisions+=1
                        shutil.rmtree(directory,ignore_errors=True);self.events.put({'kind':'obsolete','revision':revision});self._prune()
                        if not self.closed and revision==self.current_revision and job.get('retry'):
                            self.render_current(*job['retry'])
                        return
                    if error:
                        self.state='ERROR';self.error=error;shutil.rmtree(directory,ignore_errors=True);self.events.put({'kind':'error','revision':revision,'error':error})
                    else:
                        self.files[revision]={'path':path,'directory':directory,'report':result['report']};self.validated_revision=revision;self.state='READY'
                        self.events.put({'kind':'ready','revision':revision,'path':str(path),'report':result['report']})
                    self._prune()
            self.pool.submit(work);return revision

    def request(self,snapshot,soundfont,config=None):
        revision=self.revise(snapshot);self.render_current(soundfont,config);return revision

    def is_current(self,revision):
        with self.lock:return not self.closed and revision!=self.cancelled_revision and revision==self.current_revision and revision==self.validated_revision and revision in self.files

    def resume_current(self):
        """Explicit retry authorizes a new activation epoch, never an old one."""
        with self.lock:
            if self.cancelled_revision==self.current_revision:self.cancelled_revision=None;self.epoch+=1

    def activation_token(self,revision):
        with self.lock:return self.epoch if self.is_current(revision) else None

    def pin(self,revision):
        with self.lock:
            if not self.is_current(revision):return False
            self.pins[revision]=self.pins.get(revision,0)+1;return True

    def commit(self,revision,token=None):
        """Linearization point: validates current revision and records activation."""
        with self.lock:
            if not self.is_current(revision) or token is not None and token!=self.epoch:return False
            self.active_revision=revision;self.state='ACTIVE';self._prune();return True

    def unpin(self,revision):
        with self.lock:
            count=self.pins.get(revision,0)
            if count<=1:self.pins.pop(revision,None)
            else:self.pins[revision]=count-1
            self._prune()

    def cancel(self):
        with self.lock:
            self.epoch+=1;self.cancelled_revision=self.current_revision
            for job in self.jobs.values():job['cancel'].set();job.pop('retry',None)
            self.state='CANCELLED'

    def _prune(self):
        keep={self.active_revision,self.current_revision}
        for revision,info in list(self.files.items()):
            if revision not in keep and not self.pins.get(revision):shutil.rmtree(info['directory'],ignore_errors=True);self.files.pop(revision)

    def close(self):
        """Call only after the transport has released all files; wait off GTK."""
        with self.lock:self.closed=True;self.cancel()
        self.pool.shutdown(wait=True,cancel_futures=False);shutil.rmtree(self.root,ignore_errors=True)
