# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Headless batch entry point; GTK is imported only by the gui subcommand."""

import argparse
from dataclasses import fields
from pathlib import Path
import sys

from . import __version__
from .errors import VocalScopeError


def _backend_arguments(parser, *, selection=True, model='full'):
    if selection:parser.add_argument('--estimator',dest='estimator_id',choices=('pyin','yin','crepe'),default='pyin')
    parser.add_argument('--crepe-model',choices=('tiny','full'),default=model)
    parser.add_argument('--batch-size',dest='crepe_batch_size',type=int,default=128)
    parser.add_argument('--crepe-hop-length',type=int,default=160,help='CREPE hop at its native 16000 Hz rate.')
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--device',choices=('cpu',),default='cpu')
    parser.add_argument('--yin-voicing-threshold',type=float,default=0.6,help='Normalized lag correlation, not a probability.')
    parser.add_argument('--yin-trough-threshold',type=float,default=0.1)
    parser.add_argument('--crepe-voicing-threshold',type=float,default=0.5,help='CREPE periodicity, not calibrated pitch correctness.')
    parser.add_argument('--pyin-voicing-threshold',type=float,default=None,help='Optional extra rejection threshold; omitted preserves Stage 1 Viterbi baseline.')


def _configuration(args):
    from .models import AnalysisConfig
    from .notes import parse_frequency
    values={f.name:getattr(args,f.name,f.default) for f in fields(AnalysisConfig)}
    for key in ('fmin','fmax'):
        if isinstance(values[key],str):values[key]=parse_frequency(values[key],values['a4_hz'])
    return AnalysisConfig(**values)


def _backend_configuration(args):
    from .backends import EstimatorConfig
    return EstimatorConfig(**{f.name:getattr(args,f.name,f.default) for f in fields(EstimatorConfig)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vocalscope", description="Offline monophonic vocal pitch analysis, editable note transcription and evaluation.")
    parser.add_argument("--version", action="version", version=f"VocalScope {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Analyze audio and export CSV, JSON and/or PNG without a display.")
    analyze.add_argument("audio", type=Path)
    analyze.add_argument("--output", type=Path, default=Path("results"), help="Output directory (default: results).")
    analyze.add_argument("--fmin", default="C2", help="Minimum Hz or note (default: C2).")
    analyze.add_argument("--fmax", default="D6", help="Maximum Hz or note (default: D6, headroom for C6).")
    analyze.add_argument("--sample-rate", type=int, default=22050)
    analyze.add_argument("--frame-length", type=int, default=2048)
    analyze.add_argument("--hop-length", type=int, default=512)
    analyze.add_argument("--resolution", type=float, default=0.1, help="pYIN pitch bin resolution in semitones (default: 0.1).")
    analyze.add_argument("--switch-prob", type=float, default=0.01)
    analyze.add_argument("--no-trough-prob", type=float, default=0.001)
    analyze.add_argument("--max-transition-rate", type=float, default=35.92, help="Maximum pitch transition in octaves/second.")
    analyze.add_argument("--a4-hz", type=float, default=440.0)
    analyze.add_argument("--max-duration", dest="max_duration_seconds", type=float, default=300, help="Duration safeguard in seconds.")
    analyze.add_argument("--max-memory-mb", type=float, default=1024, help="Estimated DSP array budget in MiB, excluding library/JIT overhead.")
    analyze.add_argument("--formats", nargs="+", choices=("csv", "json", "png"), default=["csv", "json", "png"])
    analyze.add_argument("--overwrite", action="store_true", help="Replace existing output files (source is always protected).")
    _backend_arguments(analyze)
    benchmark=commands.add_parser('benchmark',help='Evaluate Vocadito against human F0, generate measured reports.')
    benchmark.add_argument('--dataset',choices=('vocadito',),default='vocadito')
    benchmark.add_argument('--dataset-path',type=Path,default=Path('data/vocadito'))
    benchmark.add_argument('--estimators',default='pyin,yin,crepe',help='Comma-separated backend IDs.')
    benchmark.add_argument('--output',type=Path,default=Path('reports/stage2/benchmark'))
    benchmark.add_argument('--cache-dir',type=Path)
    benchmark.add_argument('--split',choices=('development','test','all'),default='test')
    benchmark.add_argument('--seed',type=int,default=20261109)
    benchmark.add_argument('--max-tracks',type=int,help='Maximum per partition; explicitly labels a smoke run.')
    benchmark.add_argument('--calibrate',action='store_true',help='Select thresholds on development tracks only; retain baseline and evaluate held-out test tracks.')
    benchmark.add_argument('--no-resume',action='store_true')
    benchmark.add_argument('--folds',type=int);benchmark.add_argument('--fold',type=int,default=0)
    benchmark.add_argument('--fmin',default='C2');benchmark.add_argument('--fmax',default='D6')
    benchmark.add_argument('--frame-length',type=int,default=2048);benchmark.add_argument('--hop-length',type=int,default=512)
    benchmark.add_argument('--sample-rate',type=int,default=22050)
    benchmark.add_argument('--no-trough-prob',type=float,default=0.001)
    _backend_arguments(benchmark,selection=False,model='tiny')
    dataset=commands.add_parser('dataset',help='Explicitly download or verify the local CC BY 4.0 Vocadito corpus.')
    dataset.add_argument('action',choices=('download','verify'));dataset.add_argument('--path',type=Path,default=Path('data/vocadito'))
    transcribe=commands.add_parser('transcribe',help='Interpret monophonic singing as editable notes and export MIDI/JSON/CSV/PNG.')
    transcribe.add_argument('audio',type=Path)
    transcribe.add_argument('--output',type=Path,default=Path('results/transcription'))
    transcribe.add_argument('--fmin',default='C2');transcribe.add_argument('--fmax',default='D6')
    transcribe.add_argument('--sample-rate',type=int,default=22050)
    transcribe.add_argument('--frame-length',type=int,default=2048);transcribe.add_argument('--hop-length',type=int,default=512)
    transcribe.add_argument('--a4-hz',type=float,default=440.)
    transcribe.add_argument('--method',choices=('naive','pitch-only','combined'),default='combined')
    transcribe.add_argument('--min-duration',type=float,default=.06)
    transcribe.add_argument('--bridge-gap',type=float,default=.08)
    transcribe.add_argument('--pitch-change',type=float,default=.8)
    transcribe.add_argument('--onset-threshold',type=float,default=.35)
    transcribe.add_argument('--max-duration',dest='max_duration_seconds',type=float,default=300)
    transcribe.add_argument('--max-memory-mb',type=float,default=1024)
    transcribe.add_argument('--overwrite',action='store_true')
    _backend_arguments(transcribe,model='tiny')
    note_bench=commands.add_parser('benchmark-notes',help='Singer-disjoint note evaluation against both Vocadito annotators.')
    note_bench.add_argument('--dataset-path',type=Path,default=Path('data/vocadito'))
    note_bench.add_argument('--estimators',default='pyin,crepe')
    note_bench.add_argument('--output',type=Path,default=Path('reports/stage3/benchmark'))
    note_bench.add_argument('--prediction-report',type=Path,help='Optional immutable Stage 2 results.json for cached predictions.')
    note_bench.add_argument('--cache-dir',type=Path,help='Stage 2 cache directory when reusing predictions.')
    note_bench.add_argument('--seed',type=int,default=20261109)
    note_bench.add_argument('--max-tracks',type=int,help='Limit each split for a clearly labeled smoke experiment.')
    render=commands.add_parser('render-piano',help='Render current editable project notes to real offline SoundFont piano WAV/FLAC.')
    render.add_argument('project',type=Path)
    render.add_argument('--soundfont',type=Path)
    render.add_argument('--settings',type=Path,help='Optional synthesis JSON with soundfont_path; otherwise use XDG application settings.')
    render.add_argument('--output',type=Path,default=Path('results/piano'))
    render.add_argument('--sample-rate',type=int,default=44100)
    render.add_argument('--gain',type=float,default=.2)
    render.add_argument('--tail-seconds',type=float,default=1.5)
    render.add_argument('--bank',type=int,default=0);render.add_argument('--preset',type=int,default=0)
    render.add_argument('--polyphony',type=int,default=256)
    render.add_argument('--interpolation',type=int,choices=(0,1,4,7),default=4)
    render.add_argument('--reverb',action='store_true');render.add_argument('--chorus',action='store_true')
    render.add_argument('--normalize-peak',action='store_true',help='Explicitly normalize the rendered peak to 0.98 before encoding.')
    render.add_argument('--formats',nargs='+',choices=('wav','flac'),default=['wav','flac'])
    playback=commands.add_parser('playback-test',help='Exercise one shared GStreamer vocal/piano timeline with a bounded diagnostic.')
    playback.add_argument('--vocal',type=Path);playback.add_argument('--piano',type=Path)
    playback.add_argument('--sink',choices=('auto','pipewiresink','pulsesink','fakesink','appsink'),default='fakesink')
    playback.add_argument('--seconds',type=float,default=1.)
    playback.add_argument('--output',type=Path,required=True)
    gui = commands.add_parser("gui", help="Launch the native GTK4/libadwaita application.")
    gui.add_argument("--max-memory-mb", type=float, default=1024,
                     help="Initial estimated DSP array budget in MiB (default: 1024); adjustable in Analysis parameters. Not allocated memory or a process memory cap.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command=='playback-test':
            from .playback.diagnostics import run_playback_test
            report=run_playback_test(args.vocal,args.piano,args.output,sink=args.sink,seconds=args.seconds)
            print(f"Playback diagnostic {report['status']}: {args.output}")
            return 0
        if args.command=='render-piano':
            from .synthesis.models import RenderConfig
            from .synthesis.soundfont import resolve_soundfont
            from .synthesis.project import read_project_snapshot
            from .synthesis.process import render_snapshot_in_process
            config=RenderConfig(sample_rate=args.sample_rate,gain=args.gain,tail_seconds=args.tail_seconds,bank=args.bank,preset=args.preset,
                polyphony=args.polyphony,interpolation=args.interpolation,reverb=args.reverb,chorus=args.chorus,normalize_peak=args.normalize_peak)
            font=resolve_soundfont(args.soundfont,settings_file=args.settings,config=config)
            snapshot=read_project_snapshot(args.project)
            result=render_snapshot_in_process(snapshot,font,args.output,config,formats=args.formats)
            report=result['report']
            print(f"Rendered {len(snapshot['notes'])} current notes, {report['duration_seconds']:.3f} s stereo at {config.sample_rate} Hz; {report['soundfont']['preset_name']}.")
            for warning in report['warnings']:print(f'Warning: {warning}',file=sys.stderr)
            for kind,path in result['paths'].items():print(f'{kind.upper()}: {path}')
            return 0
        if args.command == "gui":
            from .models import AnalysisConfig
            config = AnalysisConfig(max_memory_mb=args.max_memory_mb)
            try:
                from .gui import run
            except (ImportError, ValueError) as exc:
                raise VocalScopeError("GTK4 GUI dependencies unavailable. On Arch install gtk4 libadwaita python-gobject python-cairo and use a --system-site-packages venv. " + str(exc)) from exc
            return run(max_memory_mb=config.max_memory_mb)
        if args.command=='dataset':
            from .datasets import download_vocadito,Vocadito
            if args.action=='download':download_vocadito(args.path)
            dataset=Vocadito(args.path)
            tracks=[dataset.load_track(i) for i in dataset.track_ids]
            print(f'Verified Vocadito v3: {len(tracks)} tracks, {sum(t.duration_seconds for t in tracks):.3f} s; CC BY 4.0.')
            return 0
        if args.command=='benchmark':
            from .benchmark import run_benchmark
            report=run_benchmark(args.dataset_path,args.output,[x.strip() for x in args.estimators.split(',')],
                                 config=_configuration(args),settings=_backend_configuration(args),split=args.split,
                                 seed=args.seed,max_tracks=args.max_tracks,calibrate=args.calibrate,
                                 cache_dir=args.cache_dir,resume=not args.no_resume,folds=args.folds,fold=args.fold)
            print(f"Benchmark {report['status']}: {args.output/'REPORT.md'}")
            return 0 if report['status']=='complete' else 1
        if args.command=='transcribe':
            from .transcription.pipeline import transcribe_file
            from .transcription.models import TranscriptionConfig
            from .transcription.serialization import export_bundle as export_notes
            c=TranscriptionConfig(method=args.method,min_duration=args.min_duration,bridge_gap=args.bridge_gap,pitch_change=args.pitch_change,onset_threshold=args.onset_threshold)
            project=transcribe_file(args.audio,_configuration(args),_backend_configuration(args),c)
            paths=export_notes(project,args.output,overwrite=args.overwrite)
            print(f"Transcribed {project.duration:.3f} s: {len(project.notes)} notes; {project.acoustic.estimator_id}; {project.config.method}.")
            for key,path in paths.items():print(f'{key.upper()}: {path}')
            return 0
        if args.command=='benchmark-notes':
            from .transcription.benchmark import run_benchmark as run_notes
            backends=tuple(x.strip() for x in args.estimators.split(','))
            if not backends or any(x not in ('pyin','yin','crepe') for x in backends):raise ValueError('Unknown estimator selection.')
            report=run_notes(args.dataset_path,args.output,estimators=backends,prediction_report=args.prediction_report,cache_dir=args.cache_dir,seed=args.seed,max_tracks=args.max_tracks)
            print(f"Note benchmark {report['status']}: {args.output/'REPORT.md'}")
            return 0 if report['status']=='complete' else 1
        from .models import AnalysisConfig
        from .notes import parse_frequency
        from .pitch import analyze_file
        from .export import export_bundle
        config = _configuration(args)
        result = analyze_file(args.audio, config, _backend_configuration(args))
        paths = export_bundle(result, args.output, formats=tuple(args.formats), overwrite=args.overwrite)
        for warning in result.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"Analyzed {result.metadata.duration_seconds:.3f} s: {len(result.time_seconds)} frames, {result.voiced.mean():.1%} voiced; {result.estimator_id} inference {result.runtime_seconds:.3f} s, initialization {result.initialization_seconds:.3f} s.")
        for fmt, path in paths.items():
            print(f"{fmt.upper()}: {path}")
        return 0
    except (VocalScopeError, ValueError, OSError) as exc:
        print(f"vocalscope: {exc}", file=sys.stderr)
        return 2
    except MemoryError:
        print("vocalscope: insufficient memory; shorten audio or use a larger hop length.", file=sys.stderr)
        return 1
    except ModuleNotFoundError as exc:
        print(f"vocalscope: missing Python dependency {exc.name!r}. Install with 'python -m pip install -r requirements.txt' inside the project venv.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("vocalscope: interrupted.", file=sys.stderr)
        return 130

