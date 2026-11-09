# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Opt-in monotonic main-loop diagnostics; no GTK import or playback clock.

GLib timeouts reschedule from dispatch time rather than catching up. We measure
lateness against the previous callback's end + interval, retaining whole gaps
and lost intervals. This does not measure compositor presentation or audio.
"""
from collections import deque
from contextlib import contextmanager
from time import monotonic_ns
import math
import numpy as np


def distribution(values):
    values=np.asarray(values,dtype=float)
    if not len(values):return dict(count=0,median_ms=None,p95_ms=None,p99_ms=None,max_ms=None)
    return dict(count=len(values),median_ms=float(np.median(values)*1000),p95_ms=float(np.percentile(values,95)*1000),
                p99_ms=float(np.percentile(values,99)*1000),max_ms=float(max(values)*1000))


class LoopMetrics:
    def __init__(self,interval=.01,capacity=200_000,clock=monotonic_ns):
        if not math.isfinite(interval) or interval<=0:raise ValueError('Positive finite interval required.')
        self.interval_ns=round(interval*1e9);self.clock=clock;self.rows=deque(maxlen=capacity);self.operations=deque(maxlen=capacity)
        self.phase='startup';self.expected=None;self.previous=None;self.source=None;self.dropped=0

    def begin(self):
        now=self.clock();self.expected=now+self.interval_ns;self.previous=now

    def tick(self,callback=None):
        started=self.clock()
        if self.expected is None:self.begin()
        scheduled=self.expected;previous=self.previous
        try:
            if callback:callback()
        finally:
            finished=self.clock()
            if len(self.rows)==self.rows.maxlen:self.dropped+=1
            self.rows.append({'phase':self.phase,'scheduled_ns':scheduled,'started_ns':started,'finished_ns':finished,
                'delay_seconds':max(0,started-scheduled)/1e9,'execution_seconds':(finished-started)/1e9,
                'gap_seconds':(started-previous)/1e9,'missed_intervals':max(0,(started-scheduled)//self.interval_ns)})
            self.previous=started;self.expected=finished+self.interval_ns

    def start(self,glib):
        self.begin()
        def tick():self.tick();return glib.SOURCE_CONTINUE
        self.source=glib.timeout_add(round(self.interval_ns/1e6),tick)

    def stop(self,glib):
        if self.source is not None:glib.source_remove(self.source);self.source=None

    @contextmanager
    def operation(self,name):
        phase=self.phase;start=self.clock()
        try:yield
        finally:self.operations.append({'name':name,'phase':phase,'started_ns':start,'finished_ns':self.clock()})

    def report(self):
        def summary(rows):
            gaps=[r['gap_seconds'] for r in rows]
            return {'delay':distribution([r['delay_seconds'] for r in rows]),'execution':distribution([r['execution_seconds'] for r in rows]),
                'gap':distribution(gaps),'gaps_above_ms':{str(t):sum(g>t/1000 for g in gaps) for t in (16.7,50,100,250)},
                'delays_above_ms':{str(t):sum(r['delay_seconds']>t/1000 for r in rows) for t in (16.7,50,100,250)}}
        phases=sorted({r['phase'] for r in self.rows}|{r['phase'] for r in self.operations})
        names=sorted({r['name'] for r in self.operations})
        return {'interval_seconds':self.interval_ns/1e9,'dropped_samples':self.dropped,'all':summary(self.rows),
            'phases':{p:summary([r for r in self.rows if r['phase']==p]) for p in phases},
            'operations':{n:{**distribution([(r['finished_ns']-r['started_ns'])/1e9 for r in self.operations if r['name']==n]),
                'total_seconds':sum((r['finished_ns']-r['started_ns'])/1e9 for r in self.operations if r['name']==n)} for n in names},
            'samples':list(self.rows),'operation_samples':list(self.operations),
            'semantics':'Callback scheduling lateness, execution and gaps. Startup and steady phases separate; all samples retained. Not compositor/audio latency.'}
