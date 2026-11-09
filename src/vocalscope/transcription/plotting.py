# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Synchronized acoustic contour and editable piano-roll rendering."""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter,MaxNLocator
from ..notes import note_name


def draw(fig,project,*,selected=None,dark=False,reference=None):
    fig.set_layout_engine(None)
    fig.clear();bg='#202124' if dark else 'white';fg='#eeeeee' if dark else '#222222'
    fig.set_facecolor(bg)
    upper,lower=fig.subplots(2,1,sharex=True,gridspec_kw={'height_ratios':[1,1]})
    for ax in (upper,lower):
        ax.set_facecolor(bg);ax.tick_params(colors=fg);ax.xaxis.label.set_color(fg);ax.yaxis.label.set_color(fg)
        ax.grid(alpha=.18);ax.yaxis.set_major_locator(MaxNLocator(integer=True));ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_:note_name(int(round(v)))))
    if project is not None:
        a=project.acoustic
        upper.plot(a.time_seconds,a.midi_pitch,color='#65b5ff',linewidth=1,label=f'{a.estimator_id}: continuous pitch')
        hop=np.median(np.diff(a.time_seconds)) if len(a.time_seconds)>1 else .02
        edges=np.r_[np.maximum(0,a.time_seconds-hop/2),a.time_seconds[-1]+hop/2]
        upper.stairs((~a.voiced).astype(float),edges,baseline=0,fill=True,transform=upper.get_xaxis_transform(),color='gray',alpha=.14)
        for b in project.boundaries:upper.axvline(b.time_seconds,color='#efb366',alpha=.2,linewidth=.6)
        for n in project.notes:
            lower.add_patch(Rectangle((n.start_seconds,n.midi_note-.35),n.end_seconds-n.start_seconds,.7,
                facecolor='#efb366' if n.note_id==selected else '#65b5ff',edgecolor=fg,linewidth=.5))
        if reference is not None:
            for start,end,pitch in reference:lower.plot([start,end],[pitch,pitch],color='#f28e8e',linewidth=2,alpha=.8)
        values=np.r_[a.midi_pitch[np.isfinite(a.midi_pitch)],[n.midi_note for n in project.notes]]
        lo,hi=(float(values.min())-2,float(values.max())+2) if len(values) else (48,84)
        upper.set_ylim(lo,hi);lower.set_ylim(lo,hi);upper.set_xlim(0,project.duration)
        upper.legend(fontsize=8,labelcolor=fg,facecolor=bg)
    upper.set_ylabel('Acoustic pitch');lower.set_ylabel('Piano notes');lower.set_xlabel('Time (seconds)')
    fig.subplots_adjust(left=.09,right=.98,top=.97,bottom=.1,hspace=.12)
    return upper,lower


def figure(project):
    fig=Figure(figsize=(12,7),dpi=110);draw(fig,project);return fig


class NotePlot:
    """Interactive artist cache. Export plotting above stays stateless."""
    def __init__(self,fig):
        self.figure=fig;self.key=None;self.axes=();self.patches={};self.previous={};self.selection=None
        self.rebuilds=0;self.geometry_updates=0

    def update(self,project,*,selected=None,dark=False,dynamic=False):
        key=(id(project.acoustic),dark)
        if key!=self.key or tuple(self.figure.axes[:2])!=self.axes:
            self.axes=draw(self.figure,project,selected=None if dynamic else selected,dark=dark)
            self.key=key;self.patches=dict(zip((n.note_id for n in project.notes),self.axes[1].patches))
            self.previous={n.note_id:n for n in project.notes};self.selection=selected;self.rebuilds+=1
            return {'rebuilt':True,'limits':True,'geometry':True}
        lower=self.axes[1];current={n.note_id:n for n in project.notes};changed=False
        for identifier in self.previous.keys()-current.keys():self.patches.pop(identifier).remove();changed=True
        for identifier,note in current.items():
            if self.previous.get(identifier)==note:continue
            patch=self.patches.get(identifier)
            if patch is None:
                patch=Rectangle((0,0),1,.7,facecolor='#65b5ff',edgecolor='#888888',linewidth=.5,animated=dynamic)
                lower.add_patch(patch);self.patches[identifier]=patch
            patch.set_xy((note.start_seconds,note.midi_note-.35));patch.set_width(note.end_seconds-note.start_seconds);changed=True
        if not dynamic and (changed or selected!=self.selection):
            for identifier,patch in self.patches.items():patch.set_facecolor('#efb366' if identifier==selected else '#65b5ff')
            changed=True
        limits=False
        if current:
            lo,hi=lower.get_ylim();values=[n.midi_note for n in current.values()]
            if min(values)<lo+.35 or max(values)>hi-.35:
                for ax in self.axes:ax.set_ylim(min(lo,min(values)-2),max(hi,max(values)+2))
                limits=True
        self.previous=current;self.selection=selected
        if changed:self.geometry_updates+=1
        return {'rebuilt':False,'limits':limits,'geometry':changed}
