# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""GStreamer stream-time gain ramps; no independent Python audio timer."""
from .gst import bindings


class Mixer:
    def __init__(self,volumes,config):
        Gst,_,Controller,_=bindings();self.volumes=volumes;self.config=config;self.mode='vocal';self.gains={'vocal':1.,'piano':1.};self.controls={};self.envelopes={};self.ahead={}
        for name,element in volumes.items():
            control=Controller.InterpolationControlSource.new();control.set_property('mode',Controller.InterpolationMode.LINEAR)
            element.add_control_binding(Controller.DirectControlBinding.new_absolute(element,'volume',control));self.controls[name]=control
        self.apply(0,{},immediate=True)

    def targets(self):
        return {n:self.gains[n]*(.5 if self.mode=='mix' else 1.) if self.mode=='mix' or self.mode==n else 0. for n in self.volumes}

    def apply(self,position,offsets,*,immediate=False):
        Gst,_,_,_=bindings()
        for name,target in self.targets().items():
            stream=max(0.,position-offsets.get(name,0.))
            timestamp=max(round(stream*Gst.SECOND),self.ahead.get(name,0)) if not immediate else 0
            control=self.controls[name]
            start,end,first,last=self.envelopes.get(name,(0,0,self.volumes[name].get_property('volume'),self.volumes[name].get_property('volume')))
            old=last if timestamp>=end else first if timestamp<=start else first+(last-first)*(timestamp-start)/(end-start)
            control.unset_all()
            if immediate:
                control.set(0,target);self.volumes[name].set_property('volume',target);self.envelopes[name]=(0,0,target,target)
            else:
                end=timestamp+round(self.config.fade_seconds*Gst.SECOND)
                control.set(timestamp,float(old));control.set(end,target);self.envelopes[name]=(timestamp,end,float(old),target)

    def set(self,mode,position,offsets,vocal_gain=None,piano_gain=None,*,immediate=False):
        if mode not in ('vocal','piano','mix'):raise ValueError('Choose vocal, piano or mix.')
        for name,gain in [('vocal',vocal_gain),('piano',piano_gain)]:
            if gain is not None:
                if not 0<=gain<=1:raise ValueError('Source gain must be within [0,1].')
                self.gains[name]=float(gain)
        self.mode=mode;self.apply(position,offsets,immediate=immediate)
