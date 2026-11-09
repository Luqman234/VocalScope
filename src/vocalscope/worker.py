# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Isolated headless DSP process, coordinated by the GUI's background thread.

Numba's Viterbi kernel can retain the GIL. A thread alone is not sufficient to
keep GTK responsive. This module uses JSON over owned subprocess pipes, with
no shell, GTK imports, shared semaphore dependency or executable serialization.
"""

from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
from threading import Event

from .errors import VocalScopeError
from .export import result_document, result_from_document
from .models import AnalysisConfig, AnalysisResult
from .backends import EstimatorConfig


def analyze_in_process(path: str | Path, config: AnalysisConfig, cancelled: Event | None = None, settings: EstimatorConfig | None = None) -> AnalysisResult:
    return _request_in_process({"path":str(path),"config":asdict(config),"estimator":asdict(settings or EstimatorConfig())},cancelled)


def transcribe_in_process(result, cancelled=None, *, max_memory_mb: float | None = None):
    """Reuse acoustic measurements with an optional current DSP admission budget."""
    from .transcription.serialization import from_document
    payload = {'job':'transcribe','acoustic':result_document(result)}
    if max_memory_mb is not None:
        payload['max_memory_mb'] = replace(result.config, max_memory_mb=max_memory_mb).max_memory_mb
    return _request_in_process(payload,cancelled,from_document)


def _request_in_process(payload, cancelled=None, decoder=result_from_document):
    request = json.dumps(payload, allow_nan=False)
    process = subprocess.Popen(
        [sys.executable, "-m", "vocalscope.worker"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        pending_input: str | None = request
        while True:
            if cancelled is not None and cancelled.is_set():
                raise VocalScopeError("Rendering cancelled; no completed output was published." if payload.get("job") in ("render_piano","inspect_soundfont") else "Analysis cancelled because the window closed.")
            try:
                stdout, stderr = process.communicate(input=pending_input, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pending_input = None
        if process.returncode != 0:
            raise VocalScopeError(f"Analysis process failed (exit {process.returncode}): {stderr.strip() or 'no diagnostic available'}")
        try:
            return decoder(json.loads(stdout))
        except (ValueError, KeyError, TypeError) as exc:
            raise VocalScopeError(f"Invalid response from analysis process: {exc}") from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if request.get('job') in ('render_piano','inspect_soundfont'):
            from .synthesis.models import RenderConfig
            from .synthesis.fluidsynth_backend import FluidSynthBackend
            config=RenderConfig(**request.get('render_config',{}))
            if request['job']=='inspect_soundfont':
                with FluidSynthBackend(request['soundfont'],config) as backend:
                    response={'soundfont':backend.info,'backend':backend.metadata,'timings':backend.timings}
            else:
                from .transcription.models import NoteEvent
                from .synthesis.export import stage_render
                report,staged=stage_render(tuple(NoteEvent(**n) for n in request['notes']),request['soundfont'],config,
                    request['workdir'],formats=request['formats'],duration_seconds=request['duration_seconds'],provenance=request['provenance'])
                response={'report':report,'staged':staged}
            json.dump(response,sys.stdout,allow_nan=False)
            return 0
        if request.get('job')=='transcribe':
            from .audio import load_audio
            from .datasets import digest
            from .transcription.pipeline import transcribe_analysis
            from .transcription.serialization import document
            acoustic=result_from_document(request['acoustic'])
            config = replace(acoustic.config, max_memory_mb=request['max_memory_mb']) if 'max_memory_mb' in request else acoustic.config
            audio=load_audio(acoustic.metadata.path,config)
            expected=acoustic.backend_metadata.get('source_sha256')
            if expected and digest(Path(acoustic.metadata.path))!=expected:raise ValueError('Audio changed since analysis.')
            project = transcribe_analysis(audio,acoustic)
            project.timings['dsp_resource_policy'] = {
                'max_memory_mb': config.max_memory_mb,
                'semantics': 'Estimated DSP working-array admission budget; not allocated memory or a process RSS cap.',
            }
            json.dump(document(project),sys.stdout,allow_nan=False)
            return 0
        config = AnalysisConfig(**request["config"])
        from .pitch import analyze_file
        from .datasets import digest
        try:identity=digest(Path(request['path']))
        except OSError:identity=None  # decoder retains the established user-facing input error
        result = analyze_file(request["path"], config, EstimatorConfig(**request.get("estimator", {})))
        if digest(Path(request['path']))!=identity:raise ValueError('Source audio changed during analysis.')
        result=replace(result,backend_metadata={**result.backend_metadata,'source_sha256':identity})
        json.dump(result_document(result), sys.stdout, allow_nan=False)
        return 0
    except (VocalScopeError, ValueError, KeyError, TypeError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except MemoryError:
        print("Insufficient memory for analysis.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

