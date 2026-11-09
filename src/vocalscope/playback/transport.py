# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Single Gst-owner thread, asynchronous commands, cached immutable snapshots.

No GLib main loop is required by headless clients. Streaming threads post Gst
messages; the owner polls the bus and commands. GTK never queries Gst directly.
"""
from concurrent.futures import Future
from collections import deque
from dataclasses import replace
from queue import Queue,Empty
from threading import Thread,Lock,Event
from time import monotonic
from .models import State,Snapshot,Session,Source,Loop,PlaybackConfig,PlaybackError,Superseded
from .gst import bindings
from .sources import discover
from .timeline import session_duration
from .engine import Engine


class Transport:
    def __init__(self,config=None):
        self.config=config or PlaybackConfig();self.commands=Queue();self.lock=Lock();self._snapshot=Snapshot();self.engine=None;self.session=None;self.metadata={}
        self._wanted=State.READY;self._pending=None;self._deferred_seek=None;self._waiters=[];self._closed=False;self._loop=None;self._loop_count=0;self._loop_ready=False;self._generation=0;self.history=deque(maxlen=2048);self._sink_index=0;self._last_poll=0.;self._mix_state=None;self._bootstrap_commands=deque();self._delayed_close=None
        self._wake_queued=Event()
        self._render_progress=None
        self._last_render_check=0.
        self._close_future=None
        self.thread=Thread(target=self._run,name='vocalscope-gstreamer',daemon=False);self.thread.start()

    def _wakeup(self):
        if not self._wake_queued.is_set() and not self._closed:
            self._wake_queued.set();self.commands.put(('wake',(),None))

    def snapshot(self):
        with self.lock:return self._snapshot

    def _update(self,**values):
        with self.lock:self._snapshot=replace(self._snapshot,**values)

    def _submit(self,name,*args):
        future=Future()
        if self._closed:future.set_exception(PlaybackError('Playback controller is closed.'));return future
        self.commands.put((name,args,future));return future

    def load(self,session,accept=None):return self._submit('load',session,accept)
    def play(self):return self._submit('state',State.PLAYING)
    def pause(self):return self._submit('state',State.PAUSED)
    def stop(self):return self._submit('stop')
    def seek(self,seconds):return self._submit('seek',seconds)
    def set_loop(self,loop):return self._submit('loop',loop)
    def set_mix(self,mode,*,vocal_gain=None,piano_gain=None):return self._submit('mix',mode,vocal_gain,piano_gain)
    def replace_piano(self,source,revision,accept=None):return self._submit('replace',source,revision,accept)
    def recover(self):return self._submit('recover')
    def capture(self,clear=False):return self._submit('capture',clear)
    def diagnostics(self):return self._submit('diagnostics')
    def close(self):
        with self.lock:
            if self._close_future is None:
                self._close_future=Future();self._closed=True;self.commands.put(('close',(),self._close_future))
            return self._close_future

    def wait_closed(self,timeout=5):self.thread.join(timeout);return not self.thread.is_alive()

    def _sinks(self):
        Gst,_,_,_=bindings()
        if self.config.sink!='auto':return [self.config.sink]
        return [s for s in ('pipewiresink','pulsesink') if Gst.ElementFactory.find(s)]

    def _dispose(self):
        if self.engine:self.engine.close();self.engine=None

    def _build(self,session,position,future,kind='load',metadata=None):
        Gst,_,_,_=bindings()
        infos=metadata or {n:discover(s) for n,s in [('vocal',session.vocal),('piano',session.piano)] if s is not None}
        sinks=self._sinks()
        if not sinks:raise PlaybackError('No PipeWire/PulseAudio GStreamer sink is installed; install gst-plugin-pipewire or gst-plugins-good.')
        if self._sink_index>=len(sinks):raise PlaybackError('No requested audio output could initialize.')
        oldmix=self._mix_state if kind!='load' else None
        if self.engine and kind!='load':oldmix=(self.engine.mixer.mode,dict(self.engine.mixer.gains))
        self._dispose();self.session=session;self.metadata=infos;duration=session_duration(infos)
        self.engine=Engine(infos,self.config,sinks[self._sink_index],self._wakeup);self._generation+=1
        self._render_progress=None
        if oldmix:self.engine.mixer.set(oldmix[0],position,{n:i['offset_seconds'] for n,i in infos.items()},vocal_gain=oldmix[1]['vocal'],piano_gain=oldmix[1]['piano'],immediate=True)
        self._mix_state=(self.engine.mixer.mode,dict(self.engine.mixer.gains))
        self._update(state=State.LOADING if kind=='load' else State.RECOVERING,position_valid=False,seeking=True,error=None,duration_seconds=duration,
            sink=sinks[self._sink_index],generation=self._generation,
            vocal_duration_seconds=infos.get('vocal',{}).get('duration_seconds',0),piano_duration_seconds=infos.get('piano',{}).get('duration_seconds',0))
        self._pending={'kind':kind,'phase':'preroll','position':min(position,duration),'future':future,'deadline':monotonic()+self.config.operation_timeout}
        if sinks[self._sink_index]=='pipewiresink':
            self._pending['phase']='bootstrap'
            result=self.engine.pipeline.set_state(Gst.State.PLAYING)
        else:result=self.engine.pipeline.set_state(Gst.State.PAUSED)
        if result==Gst.StateChangeReturn.FAILURE:raise PlaybackError('Playback pipeline could not preroll.')

    def _seek(self,position,future=None,kind='seek'):
        if not self.engine:raise PlaybackError('Load audio before seeking.')
        duration=self.snapshot().duration_seconds
        if not isinstance(position,(int,float)) or not 0<=position<=duration:raise ValueError('Seek position must be within session duration.')
        self._loop_ready=False
        # Bootstrap is over and the native sink is paused. Unmute BEFORE
        # producing the new preroll, so the first audible buffer is preserved.
        self.engine.master.set_property('volume',self.config.master_gain)
        seq=self.engine.seek(position,self._loop.end_seconds if self._loop and self._loop.enabled else duration,False)
        self._pending={'kind':kind,'phase':'seek','position':position,'future':future,'seq':seq,'deadline':monotonic()+self.config.operation_timeout}
        self._update(state=State.SEEKING,seeking=True,position_valid=False)
        self.engine.mixer.apply(position,{n:i['offset_seconds'] for n,i in self.metadata.items()},immediate=True)

    def _finish_future(self,future,value=None,error=None):
        if future is not None and not future.done():
            if error:future.set_exception(error)
            else:future.set_result(self.snapshot() if value is None else value)

    def _check_pending(self):
        if not self._pending or not self.engine:return
        Gst,_,_,_=bindings();p=self._pending
        if monotonic()>p['deadline']:raise PlaybackError(f"Timed out waiting for {p['kind']} and both source segments.")
        result,current,pending=self.engine.pipeline.get_state(0)
        if result==Gst.StateChangeReturn.FAILURE:raise PlaybackError('Pipeline state transition failed.')
        if result==Gst.StateChangeReturn.ASYNC:return
        if p['phase']=='bootstrap':
            # Wait for the actual first native render (muted), not a timer or
            # state-change guess. This activates PipeWire's pool before flush.
            stats=self.engine.sink.get_property('stats')
            if not stats or not stats.get_value('rendered'):return
            p['phase']='preroll';self.engine.pipeline.set_state(Gst.State.PAUSED);return
        if p['phase']=='preroll':
            extras={k:p[k] for k in ('accept','rollback','result_error','replacement_timing') if k in p}
            self._seek(p['position'],p['future'],p['kind']);self._pending.update(extras);return
        if not all(self.engine.segment_ack.get(name)==p['seq'] for name in self.metadata):return
        if p['kind'] in ('replace','load') and p.get('accept') is not None and not p['accept']():
            rollback=p.get('rollback');future=p['future'];self._pending=None
            if rollback is None:
                self._dispose();self._update(state=State.EMPTY,position_valid=False,seeking=False,piano_revision=0)
                self._finish_future(future,error=Superseded('Initial render became obsolete before playback activation.'));return
            self._build(rollback[0],p['position'],future,'rollback',rollback[1])
            self._pending['result_error']=Superseded('Render became obsolete during source replacement; previous source restored.')
            return
        self._pending=None
        self.engine.master.set_property('volume',self.config.master_gain)
        self._update(piano_revision=self.session.piano_revision)
        self.history.append({'operation':p['kind'],'acknowledged_monotonic':monotonic(),'position':p['position'],'source_segments':dict(self.engine.segment_ack)})
        if 'replacement_timing' in p:
            self.history[-1].update(p['replacement_timing']);self.history[-1]['controlled_interruption_seconds']=monotonic()-p['replacement_timing']['pause_started_monotonic']
        self._set_gst_state()
        self._poll()
        self._finish_future(p['future'],error=p.get('result_error'))
        if self._deferred_seek:
            position,future=self._deferred_seek;self._deferred_seek=None;self._seek(position,future)

    def _set_gst_state(self):
        Gst,_,_,_=bindings()
        target=Gst.State.PLAYING if self._wanted==State.PLAYING else Gst.State.PAUSED
        if self.engine.pipeline.set_state(target)==Gst.StateChangeReturn.FAILURE:raise PlaybackError('Requested playback state was rejected.')

    def _poll(self):
        if not self.engine:return
        Gst,_,_,_=bindings();ok,position=self.engine.pipeline.query_position(Gst.Format.TIME)
        result,current,pending=self.engine.pipeline.get_state(0)
        state=self.snapshot().state
        if self._pending is None and result!=Gst.StateChangeReturn.ASYNC:
            if current==Gst.State.PLAYING:state=State.PLAYING
            elif current==Gst.State.PAUSED:state=self._wanted if self._wanted in (State.READY,State.PAUSED,State.STOPPED) else State.PAUSED
        latency=None;query=Gst.Query.new_latency()
        if self.engine.pipeline.query(query):
            live,minimum,maximum=query.parse_latency();latency=minimum/Gst.SECOND
        self._update(state=state,position_seconds=min(self.snapshot().duration_seconds,max(0.,position/Gst.SECOND)) if ok else self.snapshot().position_seconds,
            position_valid=bool(ok and self._pending is None),seeking=self._pending is not None,sampled_monotonic=monotonic(),mode=self.engine.mixer.mode,
            loop=self._loop,loop_count=self._loop_count,latency_seconds=latency,peak=self.engine.last_peak)
        remaining=[]
        for wanted,f in self._waiters:
            if state==wanted and self._pending is None:self._finish_future(f)
            else:remaining.append((wanted,f))
        self._waiters=remaining
        # Some native sink disconnects leave Gst PLAYING and clock queries
        # advancing without posting ERROR. Successful sink-render progress is
        # a separate observation; it must not be inferred from media time.
        if state==State.PLAYING and self._pending is None and self._wanted==State.PLAYING:
            now=monotonic()
            if now-self._last_render_check>=.1:
                self._last_render_check=now
                stats=self.engine.sink.get_property('stats');rendered=int(stats.get_value('rendered')) if stats else None
                if self._render_progress is None or self._render_progress[0]!=rendered:self._render_progress=(rendered,now)
                elif now-self._render_progress[1]>self.config.output_stall_timeout:
                    raise PlaybackError('Audio output stalled: no buffers rendered by the sink. Check the output device/server, then Recover output.')
        else:self._render_progress=None;self._last_render_check=0.
        if self._loop and self._loop.enabled and self._wanted==State.PLAYING and self._pending is None and ok and (position/Gst.SECOND>=self._loop.end_seconds-1/48000 or self._loop_ready and self.engine.segment_clock_finished()):
            self._loop_count+=1;self._seek(self._loop.start_seconds,kind='loop_restart')

    def _command(self,name,args,f):
        if name=='wake':return
        Gst,_,_,_=bindings()
        if self._pending and self._pending['phase']=='bootstrap' and name in ('stop','loop','replace','recover','load'):
            self._bootstrap_commands.append((name,args,f));return
        if name=='load':
            rollback=(self.session,dict(self.metadata)) if self.engine else None
            self._cancel_pending();self._wanted=State.READY;self._loop=None;self._loop_count=0;self._sink_index=0;self._build(args[0],0.,f)
            self._pending.update(accept=args[1],rollback=rollback);return
        if name=='close':
            self._update(state=State.CLOSING);self._cancel_pending();self._dispose();self._update(state=State.EMPTY,position_seconds=0.,position_valid=False);self._finish_future(f);return 'close'
        if name=='diagnostics':
            value={'history':list(self.history),'sources':self.metadata,'events':list(self.engine.events) if self.engine else [],'capture_arrivals':list(self.engine.arrivals) if self.engine else [],'version':Gst.version_string(),'clock':self.engine.pipeline.get_clock().get_name() if self.engine and self.engine.pipeline.get_clock() else None,'snapshot':self.snapshot()}
            self._finish_future(f,value);return
        if name=='capture':self._finish_future(f,self.engine.captured(*args) if self.engine else []);return
        if name=='recover':
            if self.session is None:raise PlaybackError('No session to recover.')
            if self._pending:
                if self._pending['kind']=='recover':
                    self._finish_future(f,error=Superseded('Recovery already in progress.'));return
                self._cancel_pending()
            self._build(self.session,self.snapshot().position_seconds,f,'recover');return
        if not self.engine:
            if self.session and self.snapshot().state==State.ERROR and (name=='stop' or name=='state' and args[0]==State.PAUSED):
                self._wanted=State.STOPPED if name=='stop' else State.PAUSED
                if name=='stop':self._update(position_seconds=0.)
                self._finish_future(f);return
            raise PlaybackError('Load audio or Recover output before using the transport.')
        if name=='state':
            remaining=[]
            for wanted,previous in self._waiters:
                if wanted!=args[0]:self._finish_future(previous,error=Superseded('Playback intent superseded.'))
                else:remaining.append((wanted,previous))
            self._waiters=remaining
            self._wanted=args[0];self._waiters.append((args[0],f))
            if self._pending is None:
                if args[0]==State.PLAYING and self._loop and self._loop.enabled and not self._loop.start_seconds<=self.snapshot().position_seconds<self._loop.end_seconds:self._seek(self._loop.start_seconds)
                elif self.snapshot().position_seconds>=self.snapshot().duration_seconds-.001 and args[0]==State.PLAYING:self._seek(0.)
                else:self._set_gst_state()
            return
        if name=='stop':
            self._wanted=State.STOPPED;self._cancel_pending();self.engine.pipeline.set_state(Gst.State.PAUSED);self._seek(0.,f,'stop');return
        if name=='seek':
            position=float(args[0])
            if not 0<=position<=self.snapshot().duration_seconds:raise ValueError('Seek outside session duration.')
            if self._loop and self._loop.enabled and not self._loop.start_seconds<=position<self._loop.end_seconds:raise ValueError('Seek inside the enabled loop, or disable looping.')
            if self._pending:
                if self._deferred_seek:self._finish_future(self._deferred_seek[1],error=Superseded('Seek coalesced into a newer request.'))
                self._deferred_seek=(position,f)
            else:self._seek(position,f)
            return
        if name=='loop':
            loop=args[0]
            if loop:loop.validate(self.snapshot().duration_seconds)
            self._loop=loop;position=self.snapshot().position_seconds
            if loop and loop.enabled and not loop.start_seconds<=position<loop.end_seconds:position=loop.start_seconds
            self._cancel_pending();self._seek(position,f,'loop');return
        if name=='mix':
            mode,vocal,piano=args
            if mode=='vocal' and 'vocal' not in self.metadata or mode=='piano' and 'piano' not in self.metadata:raise ValueError('That source is not loaded.')
            self.engine.mixer.set(mode,self.snapshot().position_seconds,{n:i['offset_seconds'] for n,i in self.metadata.items()},vocal,piano,immediate=self.snapshot().state!=State.PLAYING)
            self._mix_state=(self.engine.mixer.mode,dict(self.engine.mixer.gains))
            self._poll()
            if self.snapshot().state!=State.PLAYING:
                if self._pending:
                    if self._deferred_seek:self._finish_future(self._deferred_seek[1],error=Superseded('Mixer seek coalesced.'))
                    self._deferred_seek=(self._pending['position'],f)
                else:self._seek(self.snapshot().position_seconds,f,'mix_preroll')
            else:self._finish_future(f)
            return
        if name=='replace':
            source,revision,accept=args
            if accept is not None and not callable(accept):raise ValueError('Invalid revision acceptance callback.')
            if type(revision) is not int or revision<0:raise ValueError('Revision must be a nonnegative integer.')
            if revision<self.session.piano_revision:raise Superseded('Obsolete piano revision rejected.')
            # Discover/validate before stopping the last valid playback source.
            preparation=monotonic();info=discover(source);metadata=dict(self.metadata);metadata['piano']=info
            session=replace(self.session,piano=source,piano_revision=revision)
            self._poll();position=self.snapshot().position_seconds;rollback=(self.session,dict(self.metadata));self._cancel_pending();pause_started=monotonic();self._build(session,position,f,'replace',metadata)
            self._pending.update(accept=accept,rollback=rollback,replacement_timing={'preparation_seconds':pause_started-preparation,'pause_started_monotonic':pause_started});return
        raise PlaybackError('Unknown playback command.')

    def _cancel_pending(self):
        for _,_,f in self._bootstrap_commands:self._finish_future(f,error=Superseded('Playback operation superseded.'))
        self._bootstrap_commands.clear()
        for _,f in self._waiters:self._finish_future(f,error=Superseded('Playback intent superseded.'))
        self._waiters=[]
        if self._pending:self._finish_future(self._pending.get('future'),error=Superseded('Operation superseded.'))
        if self._deferred_seek:self._finish_future(self._deferred_seek[1],error=Superseded('Seek superseded.'))
        self._pending=None;self._deferred_seek=None

    def _error(self,exc,extra_future=None):
        futures=[extra_future]
        if self._pending:futures.append(self._pending.get('future'))
        if self._deferred_seek:futures.append(self._deferred_seek[1])
        futures.extend(f for _,f in self._waiters)
        futures.extend(f for _,_,f in self._bootstrap_commands);self._bootstrap_commands.clear()
        self._pending=None;self._deferred_seek=None;self._waiters=[]
        try:self._dispose()
        except Exception as cleanup:exc=PlaybackError(f'{exc}; output cleanup: {cleanup}')
        self._update(state=State.ERROR,error=str(exc),position_valid=False,seeking=False)
        for f in futures:self._finish_future(f,error=PlaybackError(str(exc)))

    def _bus(self):
        if not self.engine:return
        Gst,_,_,_=bindings()
        for _ in range(100):
            message=self.engine.bus.pop()
            if message is None:break
            if message.type==Gst.MessageType.STATE_CHANGED and message.src==self.engine.pipeline:
                old,new,pending_state=message.parse_state_changed()
                if self._pending is None and new in (Gst.State.PLAYING,Gst.State.PAUSED):
                    acknowledged=State.PLAYING if new==Gst.State.PLAYING else self._wanted if self._wanted in (State.READY,State.PAUSED,State.STOPPED) else State.PAUSED
                    ok,media=self.engine.pipeline.query_position(Gst.Format.TIME)
                    self._update(state=acknowledged,position_seconds=media/Gst.SECOND if ok else self.snapshot().position_seconds,position_valid=bool(ok),sampled_monotonic=monotonic())
                    remaining=[]
                    for wanted,f in self._waiters:
                        if wanted==acknowledged:self._finish_future(f)
                        else:remaining.append((wanted,f))
                    self._waiters=remaining
            if message.type==Gst.MessageType.ERROR:
                error,debug=message.parse_error();pending=self._pending
                if self.config.sink=='auto' and self._sink_index+1<len(self._sinks()) and pending and pending['kind']=='load':
                    self._sink_index+=1;self._build(self.session,pending['position'],pending['future'],'load',self.metadata)
                    self._pending.update({k:pending[k] for k in ('accept','rollback') if k in pending});return
                raise PlaybackError(f'{self.engine.sink_name}: {error.message} ({debug or "no plugin detail"})')
            if message.type in (Gst.MessageType.EOS,Gst.MessageType.SEGMENT_DONE):
                self.history.append({'bus':Gst.MessageType.get_name(message.type),'seqnum':message.get_seqnum(),'seek_seqnum':self.engine.last_seek_seq,'position':self.snapshot().position_seconds})
                if self._loop and self._loop.enabled:
                    self._loop_ready=True
                elif message.type==Gst.MessageType.EOS:
                    self._wanted=State.PAUSED;self.engine.pipeline.set_state(Gst.State.PAUSED)
            elif message.type==Gst.MessageType.CLOCK_LOST:
                self.history.append({'bus':'clock-lost','position':self.snapshot().position_seconds})
                self.engine.pipeline.set_state(Gst.State.PAUSED);self._set_gst_state()
            elif message.type==Gst.MessageType.LATENCY:self.engine.pipeline.recalculate_latency()
            elif message.type==Gst.MessageType.BUFFERING:
                percent=message.parse_buffering()
                if percent<100:self.engine.pipeline.set_state(Gst.State.PAUSED)
                elif self._pending is None:self._set_gst_state()

    def _run(self):
        try:
            while True:
                try:
                    bootstrap=self._pending and self._pending['phase']=='bootstrap'
                    if self._delayed_close is not None and not bootstrap:
                        name,args,f='close',(),self._delayed_close;self._delayed_close=None
                    elif self._bootstrap_commands and not bootstrap:name,args,f=self._bootstrap_commands.popleft()
                    else:name,args,f=self.commands.get(timeout=.01)
                    if name=='wake':
                        self._wake_queued.clear()
                    if name=='close':
                        if bootstrap:
                            self._delayed_close=f;self._update(state=State.CLOSING);continue
                        self._cancel_pending()
                        try:self._dispose();self._update(state=State.EMPTY,position_valid=False);self._finish_future(f)
                        except Exception as exc:self._finish_future(f,error=PlaybackError(str(exc)))
                        return
                    try:
                        if self._command(name,args,f)=='close':return
                    except (ValueError,PlaybackError) as exc:
                        if name in ('load','recover'):self._error(exc,extra_future=f)
                        else:self._finish_future(f,error=exc)
                    except Exception as exc:self._error(exc,extra_future=f)
                except Empty:pass
                try:self._bus();self._check_pending();self._poll()
                except Exception as exc:
                    self._error(exc)
        finally:self._dispose()
