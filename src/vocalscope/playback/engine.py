# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""One shared pipeline, operated only by the transport owner thread.

Dynamic pad callbacks only link Gst pads. Probes translate canonical seeks into
source coordinates and record acknowledgements; no GTK or state waits there.
"""
from collections import deque
from threading import Lock
import numpy as np
from .gst import bindings
from .models import PlaybackError
from .mixer import Mixer


class Engine:
    def __init__(self,metadata,config,sink_name,wakeup=None):
        self.Gst,_,_,_=bindings();Gst=self.Gst;self.metadata=metadata;self.config=config;self.closed=False;self.signals=[];self.probes=[];self.released=False
        self.pipeline=Gst.Pipeline.new('vocalscope-shared-clock');self.branches={};self.events=deque(maxlen=512);self.capture=deque();self.capture_frames=0;self.arrivals=deque(maxlen=5000);self.capture_lock=Lock();self.segment_ack={};self.last_peak=0.;self.output_segment=None
        self.mix=self.element('audiomixer','shared_mixer');self.mix.set_property('output-buffer-duration',10*Gst.MSECOND)
        self.mix.set_property('alignment-threshold',0)
        master=self.element('volume','master');self.master=master;master.set_property('volume',0. if sink_name=='pipewiresink' else config.master_gain)
        convert=self.element('audioconvert','output_convert');caps=self.element('capsfilter','output_caps');caps.set_property('caps',Gst.Caps.from_string('audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=2'))
        self.sink=self.element(sink_name,'output');self.sink_name=sink_name
        if self.sink.find_property('sync'):self.sink.set_property('sync',config.sink_sync)
        if self.sink.find_property('enable-last-sample'):self.sink.set_property('enable-last-sample',False)
        if sink_name=='pipewiresink':
            self.sink.set_property('client-name','VocalScope')
            # PipeWire 1.6.10 activates its audio pool only on first render.
            # The transport performs a muted bootstrap before paused seeks.
        if sink_name=='pulsesink':self.sink.set_property('client-name','VocalScope')
        if sink_name=='appsink':
            self.sink.set_property('emit-signals',True);self.sink.set_property('max-buffers',8);self.sink.set_property('drop',True);self.sink.set_property('wait-on-eos',False)
            self.signals.append((self.sink,self.sink.connect('new-sample',self._sample)))
        for left,right in zip([self.mix,master,convert,caps],[master,convert,caps,self.sink]):
            if not left.link(right):raise PlaybackError('Output audio caps could not be linked.')
        volumes={}
        for name,info in metadata.items():
            decoder=self.element('uridecodebin',name+'_decode');decoder.set_property('uri',info['uri'])
            queue=self.element('queue',name+'_queue');queue.set_property('max-size-time',100*Gst.MSECOND);queue.set_property('max-size-bytes',0);queue.set_property('max-size-buffers',0)
            cv=self.element('audioconvert',name+'_convert');resample=self.element('audioresample',name+'_resample');cap=self.element('capsfilter',name+'_caps');cap.set_property('caps',Gst.Caps.from_string('audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=2'))
            volume=self.element('volume',name+'_gain');volumes[name]=volume
            for a,b in zip([queue,cv,resample,cap],[cv,resample,cap,volume]):
                if not a.link(b):raise PlaybackError('Cannot link decoder audio conversion.')
            pad=self.mix.request_pad_simple('sink_%u')
            if volume.get_static_pad('src').link(pad)!=Gst.PadLinkReturn.OK:raise PlaybackError('Cannot connect mixer input.')
            branch={'decoder':decoder,'queue':queue,'volume':volume,'pad':pad,'offset':info['offset_seconds'],'duration':info['duration_seconds']}
            self.branches[name]=branch
            def added(_decoder,source_pad,q=queue):
                if self.closed:return
                caps=source_pad.get_current_caps() or source_pad.query_caps(None)
                if caps and caps.get_structure(0).get_name().startswith('audio/'):
                    sink=q.get_static_pad('sink')
                    if not sink.is_linked():source_pad.link(sink)
            self.signals.append((decoder,decoder.connect('pad-added',added)))
            probe_pad=queue.get_static_pad('sink');self.probes.append((probe_pad,probe_pad.add_probe(Gst.PadProbeType.EVENT_UPSTREAM,self._upstream,name)))
            probe_pad=volume.get_static_pad('src');self.probes.append((probe_pad,probe_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM|Gst.PadProbeType.BUFFER,self._downstream,name)))
            pad.set_offset(round(max(0.,info['offset_seconds'])*Gst.SECOND))
        self.mixer=Mixer(volumes,config)
        if 'vocal' not in volumes:self.mixer.set('piano',0,{},immediate=True)
        probe_pad=self.mix.get_static_pad('src');self.probes.append((probe_pad,probe_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM,self._output_event)))
        self.invalid_pcm=False
        probe_pad=caps.get_static_pad('src');self.probes.append((probe_pad,probe_pad.add_probe(Gst.PadProbeType.BUFFER,self._output_pcm)))
        self.bus=self.pipeline.get_bus()
        if wakeup is not None:
            def notify(bus,message,data):
                if not self.closed:wakeup()
                return Gst.BusSyncReply.PASS
            self.bus.set_sync_handler(notify,None)

    def element(self,factory,name):
        element=self.Gst.ElementFactory.make(factory,name)
        if element is None:raise PlaybackError(f'Missing GStreamer plugin: {factory}. Install the documented Arch playback packages.')
        self.pipeline.add(element);return element

    def _upstream(self,pad,info,name):
        Gst=self.Gst;event=info.get_event()
        if event.type==Gst.EventType.SEEK:
            rate,fmt,flags,start_type,start,stop_type,stop=event.parse_seek();branch=self.branches[name];offset=round(branch['offset']*Gst.SECOND)
            local_start=max(0,start-offset);duration=round(branch['duration']*Gst.SECOND)
            local_start=min(local_start,duration)
            local_stop=min(duration,max(local_start,stop-offset)) if stop_type==Gst.SeekType.SET else stop
            branch['pad'].set_offset(max(0,offset-start))
            translated=Gst.Event.new_seek(rate,fmt,flags,start_type,local_start,stop_type,local_stop)
            translated.set_seqnum(event.get_seqnum())
            self.events.append({'type':'source_seek','source':name,'seqnum':event.get_seqnum(),'canonical_start':start/Gst.SECOND,'source_start':local_start/Gst.SECOND})
            if offset==0 and start<=duration:return Gst.PadProbeReturn.OK
            peer=pad.get_peer()
            if peer is not None:peer.send_event(translated)
            return Gst.PadProbeReturn.DROP
        return Gst.PadProbeReturn.OK

    def _downstream(self,pad,info,name):
        Gst=self.Gst
        if info.type&Gst.PadProbeType.BUFFER:
            buffer=info.get_buffer()
            if hasattr(self,'mixer'):self.mixer.ahead[name]=int(buffer.pts+(buffer.duration if buffer.duration!=Gst.CLOCK_TIME_NONE else 0))
            return Gst.PadProbeReturn.OK
        event=info.get_event()
        if event.type in (Gst.EventType.SEGMENT,Gst.EventType.EOS):
            if event.type==Gst.EventType.SEGMENT:self.segment_ack[name]=event.get_seqnum()
            else:self.segment_ack.setdefault(name,event.get_seqnum())
            row={'type':event.type.value_nick,'source':name,'seqnum':event.get_seqnum()}
            if event.type==Gst.EventType.SEGMENT:
                segment=event.parse_segment();row.update(start=segment.start/Gst.SECOND,time=segment.time/Gst.SECOND,base=segment.base/Gst.SECOND)
            self.events.append(row)
        return Gst.PadProbeReturn.OK

    def _output_event(self,pad,info):
        event=info.get_event()
        if event.type==self.Gst.EventType.SEGMENT:self.output_segment=event.parse_segment().copy()
        return self.Gst.PadProbeReturn.OK

    def segment_clock_finished(self):
        segment=self.output_segment;clock=self.pipeline.get_clock()
        if segment is None or clock is None or segment.stop==self.Gst.CLOCK_TIME_NONE:return False
        running_end=segment.to_running_time(self.Gst.Format.TIME,max(segment.start,segment.stop-1))+1
        if running_end==self.Gst.CLOCK_TIME_NONE:return False
        query=self.Gst.Query.new_latency();latency=0
        if self.pipeline.query(query):latency=query.parse_latency()[1]
        return clock.get_time()-self.pipeline.get_base_time()>=running_end+latency

    def _output_pcm(self,pad,info):
        Gst=self.Gst;buffer=info.get_buffer();ok,mapping=buffer.map(Gst.MapFlags.READ)
        if ok:
            try:
                data=np.frombuffer(mapping.data,dtype='<f4')
                if not np.isfinite(data).all():
                    if not self.invalid_pcm:
                        from gi.repository import GLib
                        self.invalid_pcm=True
                        error=GLib.Error.new_literal(Gst.StreamError.quark(),'Decoded/mixed audio contains non-finite PCM; playback stopped.',int(Gst.StreamError.DECODE))
                        self.pipeline.post_message(Gst.Message.new_error(self.pipeline,error,'invalid floating-point media'))
                    return Gst.PadProbeReturn.DROP
                self.last_peak=float(np.max(abs(data),initial=0.))
            finally:buffer.unmap(mapping)
        return Gst.PadProbeReturn.OK

    def _sample(self,sink):
        Gst=self.Gst;sample=sink.emit('pull-sample')
        if sample is None:return Gst.FlowReturn.EOS
        buffer=sample.get_buffer();ok,mapping=buffer.map(Gst.MapFlags.READ)
        if ok:
            try:
                audio=np.frombuffer(mapping.data,dtype='<f4').reshape(-1,2).copy();self.last_peak=float(np.max(abs(audio),initial=0.))
                segment=sample.get_segment();media=segment.to_stream_time(Gst.Format.TIME,buffer.pts)
                row=(int(media),audio)
                from time import monotonic
                self.arrivals.append({'media_ns':int(media),'frames':len(audio),'arrival_monotonic':monotonic()})
                with self.capture_lock:
                    self.capture.append(row);self.capture_frames+=len(audio)
                    limit=round(self.config.capture_seconds*48000)
                    while self.capture and self.capture_frames>limit:self.capture_frames-=len(self.capture.popleft()[1])
            finally:buffer.unmap(mapping)
        return Gst.FlowReturn.OK

    def captured(self,clear=False):
        with self.capture_lock:
            rows=list(self.capture)
            if clear:self.capture.clear();self.capture_frames=0
            return rows

    def seek(self,position,stop=None,segment=False):
        Gst=self.Gst;flags=Gst.SeekFlags.FLUSH|Gst.SeekFlags.ACCURATE
        if segment:flags|=Gst.SeekFlags.SEGMENT
        event=Gst.Event.new_seek(1.,Gst.Format.TIME,flags,Gst.SeekType.SET,round(position*Gst.SECOND),Gst.SeekType.SET if stop is not None else Gst.SeekType.NONE,round(stop*Gst.SECOND) if stop is not None else -1)
        seq=Gst.util_seqnum_next();event.set_seqnum(seq);self.last_seek_seq=seq
        self.segment_ack.clear()
        if not self.pipeline.send_event(event):raise PlaybackError('Shared pipeline seek was rejected.')
        return seq

    def close(self):
        if self.released:return
        self.closed=True;self.pipeline.set_state(self.Gst.State.NULL);status,current,pending=self.pipeline.get_state(2*self.Gst.SECOND)
        if current!=self.Gst.State.NULL:raise PlaybackError('Old output pipeline has not reached NULL; replacement is unsafe.')
        for element,handler in self.signals:element.disconnect(handler)
        for pad,probe in self.probes:pad.remove_probe(probe)
        self.signals.clear();self.probes.clear()
        for branch in self.branches.values():self.mix.release_request_pad(branch['pad'])
        self.bus.set_flushing(True);self.released=True
        self.bus.set_sync_handler(None,None)
