# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Comparable real GLib event-loop scenario for old installed wheel/new source.

No sleep/Future.result/GLib manual iteration on the GTK thread. The app owns
rendering and playback; this harness only schedules actions and polls outcomes.
"""
import argparse,cProfile,functools,importlib.util,json,os,sys,traceback
import psutil
from pathlib import Path
from time import monotonic


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--profile',type=Path)
    parser.add_argument('--project',type=Path,default=Path('results/stage3-human-pyin/vocadito_1.notes.json'))
    parser.add_argument('--vocal',type=Path,default=Path('data/vocadito/Audio/vocadito_1.wav'));parser.add_argument('--piano',type=Path,default=Path('results/stage4a-release-piano/piano.wav'))
    parser.add_argument('--soundfont',type=Path,default=Path('data/soundfonts/TimGM6mb.sf2'));parser.add_argument('--sink',default='fakesink',choices=['fakesink','pipewiresink']);parser.add_argument('--steady-seconds',type=float,default=8)
    args=parser.parse_args()
    # Same instrumentation even when PYTHONPATH selects the unmodified wheel.
    spec=importlib.util.spec_from_file_location('vocalscope_latency_probe',Path(__file__).resolve().parents[1]/'src/vocalscope/ui_metrics.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);metrics=module.LoopMetrics()
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import GLib,Gtk,Gdk
    Gtk.init()
    if Gdk.Display.get_default() is None:raise RuntimeError('Native display required')
    process=psutil.Process();resources=[];process.cpu_percent(None)
    def sample_resources():
        resources.append({'time':monotonic(),'phase':metrics.phase,'rss_bytes':process.memory_info().rss,'fd_count':process.num_fds(),'threads':process.num_threads(),'children':len(process.children()),'cpu_percent':process.cpu_percent(None)})
        return GLib.SOURCE_CONTINUE
    resource_timer=GLib.timeout_add(500,sample_resources)
    loop=GLib.MainLoop();metrics.start(GLib);prof=cProfile.Profile() if args.profile else None
    if prof:prof.enable()
    state={'error':None};actions=[];phase_times={};counters={};started=monotonic()
    def wrap(cls,name,label=None):
        original=getattr(cls,name)
        @functools.wraps(original)
        def measured(*a,**k):
            with metrics.operation(label or cls.__name__+'.'+name):return original(*a,**k)
        setattr(cls,name,measured)
    def phase(name,action=lambda:None,predicate=lambda:True,hold=.15,timeout=20):actions.append((name,action,predicate,hold,timeout))
    def series(action,count,interval=.12):
        state['series_remaining']=count
        def step():
            try:action(count-state['series_remaining']);state['series_remaining']-=1
            except Exception:fail();return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE if state['series_remaining'] else GLib.SOURCE_REMOVE
        GLib.timeout_add(round(interval*1000),step)
    def future(f):state['future']=f
    def future_done():
        f=state.get('future')
        if f is None or not f.done():return False
        if f.exception():raise f.exception()
        return True
    def fail():
        state['error']=traceback.format_exc();print(state['error'],file=sys.stderr)
        if state.get('window'):state['window'].close()
        GLib.timeout_add(1000,lambda:loop.quit() or GLib.SOURCE_REMOVE)
    def next_phase():
        if not actions:loop.quit();return GLib.SOURCE_REMOVE
        name,action,predicate,hold,timeout=actions.pop(0);metrics.phase=name;begin=monotonic()
        try:
            with metrics.operation('scenario.'+name):action()
        except Exception:fail();return GLib.SOURCE_REMOVE
        def check():
            try:
                elapsed=monotonic()-begin
                if elapsed>timeout:raise TimeoutError(name)
                if elapsed>=hold and predicate():
                    phase_times[name]=elapsed;GLib.idle_add(next_phase);return GLib.SOURCE_REMOVE
            except Exception:fail();return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        GLib.timeout_add(5,check);return GLib.SOURCE_REMOVE
    def initialize():
        try:
            import vocalscope
            from vocalscope.gui import VocalScopeApplication
            from vocalscope.transcription.workspace import TranscriptionWorkspace
            from vocalscope.playback.workspace import PlaybackWorkspace
            from vocalscope.playback.timeline_view import TimelineView
            from vocalscope.playback.models import PlaybackConfig,State,Loop
            from matplotlib.backends.backend_gtk4agg import FigureCanvasGTK4Agg
            from matplotlib.figure import Figure
            for cls,names in [(TranscriptionWorkspace,['set_project','update_notes','draw','select','edit']),
                (PlaybackWorkspace,['poll','decorate','project_changed']), (TimelineView,['decorate','update']),
                (FigureCanvasGTK4Agg,['draw','blit','on_draw_event']),(Figure,['clear'])]:
                for name in names:wrap(cls,name)
            app=VocalScopeApplication();app.set_application_id('io.github.vocalscope.StabilizationProfile');app.register(None)
            state.update(app=app,module=vocalscope.__file__,version=vocalscope.__version__)
            with metrics.operation('window.activate'):app.activate()
            w=app.get_active_window();state['window']=w;ws=w.transcription;p=ws.playback;p.config=PlaybackConfig(sink=args.sink,master_gain=.03 if args.sink=='pipewiresink' else .8)
            phase('mapping',predicate=lambda:w.get_mapped(),hold=.5)
            phase('open_audio',lambda:w.load_path(args.vocal),lambda:not w.busy,hold=.2)
            phase('load_project',lambda:ws.load_from(args.project),lambda:ws.project is not None and not w.busy,hold=.3)
            phase('expand_panel',lambda:p.expander.set_expanded(True),hold=.4)
            def load():p.auto.set_active(False);p.piano.set_text(str(args.piano));p.command('load')
            phase('load_waveform',load,lambda:p.prepared and p.view.wave is not None,hold=.3)
            phase('start',lambda:p.command('play'),lambda:p.transport.snapshot().state==State.PLAYING,hold=.3)
            phase('steady_playback',hold=args.steady_seconds,timeout=args.steady_seconds+5)
            phase('seeks',lambda:series(lambda i:future(p.transport.seek(2.+i*.2)),10),lambda:state['series_remaining']==0 and future_done(),hold=1.5)
            def edit(i):ws.fields['midi_note'].set_text(str(64+i%3));ws.edit('apply')
            phase('single_edit',lambda:edit(0),hold=.4)
            phase('many_edits',lambda:series(edit,15,.12),lambda:state['series_remaining']==0,hold=2.)
            phase('undo_redo',lambda:series(lambda i:ws.edit('undo' if i%2==0 else 'redo'),10),lambda:state['series_remaining']==0,hold=1.5)
            phase('mix_switches',lambda:series(lambda i:p.mode.set_selected(i%3),12),lambda:state['series_remaining']==0,hold=1.6)
            def render():ws.rendering.font_entry.set_text(str(args.soundfont));p.render_preview()
            phase('render_replace',render,lambda:p.coordinator.status().active_revision==p.coordinator.status().current_revision,hold=.2)
            phase('steady_after_edit',hold=args.steady_seconds,timeout=args.steady_seconds+5)
            phase('loop',lambda:future(p.transport.set_loop(Loop(2.,3.))),lambda:p.transport.snapshot().loop_count>=3,hold=3.2)
            phase('shutdown',lambda:w.close(),lambda:hasattr(p,'cleanup_thread') and not p.cleanup_thread.is_alive(),hold=.1)
            state['playback']=p;GLib.idle_add(next_phase)
        except Exception:fail()
        return GLib.SOURCE_REMOVE
    metrics.phase='initialize';GLib.idle_add(initialize)
    # Global safety timeout is itself GLib-based; native call hangs are bounded
    # by the invoking shell timeout in the documented command.
    guard=GLib.timeout_add_seconds(100,lambda:loop.quit() or GLib.SOURCE_REMOVE)
    loop.run();metrics.stop(GLib);GLib.source_remove(guard);GLib.source_remove(resource_timer)
    if prof:prof.disable();args.profile.parent.mkdir(parents=True,exist_ok=True);prof.dump_stats(str(args.profile))
    if state.get('window') and not state['window'].closed:state['window'].close()
    if state.get('app'):state['app'].quit()
    if actions and not state['error']:state['error']='Scenario incomplete'
    report=metrics.report();report.update(schema_version='1.0.0',status='failed' if state['error'] else 'complete',error=state['error'],module_path=state.get('module'),version=state.get('version'),resources=resources,
        display=Gdk.Display.get_default().__gtype__.name,sink=args.sink,elapsed_seconds=monotonic()-started,phase_seconds=phase_times,profile_enabled=bool(prof),pid=os.getpid())
    p=state.get('playback')
    if p:
        report['render_root_removed']=not p.coordinator.root.exists();report['transport_closed']=p.transport.wait_closed(0);report['visual_counters']=getattr(p.view,'counters',None)
        report['gtk_painted_frames']=getattr(state['window'].canvas,'presented_frames',None)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(args.output)
    return 1 if state['error'] else 0


if __name__=='__main__':raise SystemExit(main())
