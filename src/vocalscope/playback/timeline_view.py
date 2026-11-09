# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Persistent axes and cached static PCM/F0/note layers; dynamic overlays only.

GTK/Matplotlib calls stay on the main thread. The queried media time is the
sole cursor authority. A full draw invalidates both caches; edits can rebuild
only the piano-roll region, without ticks, waveform or F0 reconstruction.
"""
from time import monotonic
from matplotlib.patches import Rectangle
from .timeline import active_note_ids


class TimelineView:
    def __init__(self,window):
        self.window=window;self.wave=None;self.lines=[];self.patches=[];self.background=None;self.grid=None;self.enabled=False;self.active_ids=();self.last_age=0.;self.drawn_position=0.;self.duration=0.;self.last_limits=None
        self.base_axes=();self.wave_axis=None;self.wave_artist=None;self.wave_identity=None;self.notes=();self.overlays=[];self.last_visual=None;self.last_snapshot=None
        self.counters={'decorations':0,'full_layouts':0,'background_captures':0,'note_bakes':0,'blits':0,'skipped_updates':0,'dynamic_artists':0}
        self.draw_handler=window.canvas.mpl_connect('draw_event',self.capture)

    def decorate(self,duration,*,full=False):
        fig=self.window.figure
        if not self.enabled or not fig.axes:return
        self.counters['decorations']+=1
        if len(fig.axes)==1:
            lower=fig.add_axes([.09,.10,.89,.30],sharex=fig.axes[0]);lower.set_ylabel('Piano notes');lower.set_xlabel('Time (s)');lower.set_ylim(48,84)
        upper,lower=fig.axes[:2];new_axes=self.base_axes!=(upper,lower) or self.wave_axis not in fig.axes
        if new_axes:
            self.base_axes=(upper,lower);self.lines=[];self.overlays=[];self.background=None;self.grid=None;self.wave_artist=None;self.wave_identity=None
            for ax in list(fig.axes[2:]):ax.remove()
            upper.set_position([.09,.48,.89,.28]);lower.set_position([.09,.10,.89,.30])
            self.wave_axis=fig.add_axes([.09,.83,.89,.12],sharex=upper);self.wave_axis.set_ylabel('Waveform',fontsize=8);self.wave_axis.tick_params(labelbottom=False,labelsize=8)
            self.wave_axis.set_facecolor(upper.get_facecolor());fg=upper.yaxis.label.get_color();self.wave_axis.tick_params(colors=fg);self.wave_axis.yaxis.label.set_color(fg);self.wave_axis.set_ylim(-1,1)
            for ax in fig.axes:self.lines.append(ax.axvline(0,color='#ff6c74',linewidth=1,animated=True))
            self.counters['full_layouts']+=1;full=True
        if id(self.wave)!=self.wave_identity:
            if self.wave_artist is not None:self.wave_artist.remove();self.wave_artist=None
            if self.wave is not None:self.wave_artist=self.wave_axis.fill_between(*self.wave,color='#83a9c8',alpha=.7,linewidth=0)
            self.wave_identity=id(self.wave);full=True
        # Resampling/encoding can change a render's container duration by a
        # fraction of a canonical sample; retain the existing visual viewport.
        if abs(self.duration-duration)>.5/48000:
            limits=self.last_limits or (0,duration)
            if abs(limits[0])<1e-6 and abs(limits[1]-self.duration)<.001 or self.duration==0:limits=(0,duration)
            upper.set_xlim(max(0,limits[0]),min(duration,max(limits[1],limits[0]+.05)));full=True
        self.duration=duration;self.last_limits=upper.get_xlim()
        project=self.window.transcription.project;notes=tuple(project.notes) if project else ()
        patches=[p for p in lower.patches if p.get_gid()!='playback-overlay']
        self.patches=list(zip(notes,patches))
        for _,patch in self.patches:patch.set_animated(True);patch.set_facecolor('#65b5ff');patch.set_edgecolor('#888888');patch.set_linewidth(.5)
        changed=notes!=self.notes;self.notes=notes;self.last_visual=None
        if full or self.grid is None:
            self.background=None;self.grid=None;self.window.canvas.draw_idle()
        elif changed:self.refresh_notes()
        elif self.last_snapshot is not None:self.update(self.last_snapshot)

    def _bake(self):
        for _,patch in self.patches:patch.axes.draw_artist(patch)
        self.background=self.window.canvas.copy_from_bbox(self.window.figure.bbox)
        self.counters['note_bakes']+=1

    def capture(self,event):
        if not self.enabled or not self.lines or self.window.closed:return
        if self.base_axes!=tuple(self.window.figure.axes[:2]):return
        self.grid=self.window.canvas.copy_from_bbox(self.base_axes[1].bbox)
        self._bake();self.last_visual=None;self.counters['background_captures']+=1

    def refresh_notes(self):
        if self.grid is None:return
        canvas=self.window.canvas
        # Clear previously drawn cursor/highlights before updating the note area.
        if self.background is not None:canvas.restore_region(self.background)
        canvas.restore_region(self.grid);self._bake();self.last_visual=None
        if self.last_snapshot is not None:self.update(self.last_snapshot)
        else:self._present()

    def _present(self):
        canvas=self.window.canvas;canvas.blit(self.window.figure.bbox)
        # GTK4Agg 3.11 inherits the no-op FigureCanvasBase.blit. Explicitly
        # invalidate the GTK drawing area; this paints the existing Agg buffer
        # without reconstructing the figure or regenerating its ticks.
        if hasattr(canvas,'queue_draw'):canvas.queue_draw()

    def update(self,snapshot):
        if not self.enabled or not self.lines or not snapshot.position_valid:return
        if self.base_axes!=tuple(self.window.figure.axes[:2]) or any(line.axes is None for line in self.lines):return
        self.last_snapshot=snapshot;position=snapshot.position_seconds;project=self.window.transcription.project
        if self.lines[0].axes is not None:self.last_limits=self.lines[0].axes.get_xlim()
        self.active_ids=active_note_ids(project.notes,position) if project else ()
        selected=self.window.transcription.selected;self.drawn_position=position;self.last_age=max(0.,monotonic()-snapshot.sampled_monotonic)
        key=(position,self.active_ids,selected)
        if self.background is None:return
        if key==self.last_visual:self.counters['skipped_updates']+=1;return
        self.last_visual=key;canvas=self.window.canvas;canvas.restore_region(self.background)
        highlighted=[n for n,_ in self.patches if n.note_id in self.active_ids or n.note_id==selected]
        while len(self.overlays)<len(highlighted):
            patch=Rectangle((0,0),1,.7,animated=True,gid='playback-overlay');self.base_axes[1].add_patch(patch);self.overlays.append(patch)
        for note,patch in zip(highlighted,self.overlays):
            active=note.note_id in self.active_ids;chosen=note.note_id==selected
            patch.set_xy((note.start_seconds,note.midi_note-.35));patch.set_width(note.end_seconds-note.start_seconds)
            patch.set_facecolor('#68cf91' if active else '#efb366');patch.set_edgecolor('#efb366' if chosen else '#888888');patch.set_linewidth(1.5 if chosen else .5)
            patch.axes.draw_artist(patch)
        for line in self.lines:line.set_xdata([position,position]);line.axes.draw_artist(line)
        self.counters['dynamic_artists']+=len(highlighted)+len(self.lines);self.counters['blits']+=1;self._present()

    def shutdown(self):
        self.window.canvas.mpl_disconnect(self.draw_handler);self.background=None;self.grid=None;self.last_snapshot=None
