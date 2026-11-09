# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Native GTK4 UI. DSP/decoding/export run in one guarded background job.

    GTK and the embedded figure are touched only from the main-loop thread.
    DSP runs in a child process so compiled kernels cannot hold GTK's GIL.
    Closing a window cancels that process; it cannot update closed widgets.
"""

from pathlib import Path
from dataclasses import asdict
from threading import Event, Thread
from typing import Callable
from collections import deque
from time import monotonic

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402
from matplotlib.backends.backend_gtk4 import NavigationToolbar2GTK4  # noqa: E402
from matplotlib.backends.backend_gtk4agg import FigureCanvasGTK4Agg  # noqa: E402

from .audio import load_audio  # noqa: E402
from .export import export_bundle  # noqa: E402
from .models import AnalysisConfig, AnalysisResult, AudioMetadata  # noqa: E402
from .notes import parse_frequency  # noqa: E402
from .plotting import create_figure, draw_result  # noqa: E402
from .worker import analyze_in_process  # noqa: E402
from .backends import EstimatorConfig, availability  # noqa: E402


class VocalScopeCanvas(FigureCanvasGTK4Agg):
    """Count real GTK paint callbacks separately from Agg-buffer updates."""
    def __init__(self,figure):
        self.presented_frames=0;self.paint_seconds=deque(maxlen=4096)
        super().__init__(figure)

    def on_draw_event(self,widget,context):
        started=monotonic()
        result=super().on_draw_event(widget,context)
        self.presented_frames+=1;self.paint_seconds.append(monotonic()-started)
        return result


class VocalScopeWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, *, max_memory_mb: float = 1024.0):
        initial_config = AnalysisConfig(max_memory_mb=max_memory_mb)
        super().__init__(application=app, title="VocalScope", default_width=1100, default_height=800)
        self.source: Path | None = None
        self.result: AnalysisResult | None = None
        self.busy = False
        self.closed = False
        self.cancelled = Event()
        self.dialog_cancellable: Gio.Cancellable | None = None
        self.connect("close-request", self._on_close)
        self.style_manager = Adw.StyleManager.get_default()
        self.style_manager.connect("notify::dark", self._theme_changed)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(layout)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="VocalScope", subtitle="Vocal pitch and editable notes · Stage 3"))
        self.open_button = Gtk.Button(label="Open audio…", tooltip_text="Choose a local mono or stereo recording")
        self.open_button.connect("clicked", self._choose_file)
        header.pack_start(self.open_button)
        self.export_button = Gtk.Button(label="Export…", sensitive=False, tooltip_text="Export CSV, JSON and PNG to a folder")
        self.export_button.connect("clicked", self._choose_export)
        header.pack_end(self.export_button)
        self.analyze_button = Gtk.Button(label="Analyze", sensitive=False)
        self.analyze_button.add_css_class("suggested-action")
        self.analyze_button.connect("clicked", self._analyze)
        header.pack_end(self.analyze_button)
        layout.append(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=18, margin_end=18, margin_top=10, margin_bottom=12)
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_child(body);layout.append(scroll)
        self.file_label = Gtk.Label(label="No recording selected", xalign=0, selectable=True, wrap=True)
        body.append(self.file_label)
        backend_row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8)
        backend_row.append(Gtk.Label(label='Estimator'))
        self.estimator_choices=['pyin','yin']+(['crepe'] if availability()['crepe'] is None else [])
        self.estimator_selector=Gtk.DropDown.new_from_strings([{'pyin':'pYIN','yin':'YIN','crepe':'CREPE'}[x] for x in self.estimator_choices])
        backend_row.append(self.estimator_selector)
        backend_row.append(Gtk.Label(label='CREPE model'))
        self.model_selector=Gtk.DropDown.new_from_strings(['full','tiny'])
        self.model_selector.set_sensitive(False)
        backend_row.append(self.model_selector)
        backend_row.append(Gtk.Label(label='Voicing threshold'))
        self.voicing_entry=Gtk.Entry(text='Viterbi',width_chars=7,sensitive=False)
        self.voicing_entry.set_tooltip_text('YIN: normalized lag correlation; CREPE: periodicity. Scores are not calibrated pitch probabilities.')
        backend_row.append(self.voicing_entry)
        self.backend_controls=backend_row
        body.append(backend_row)
        if availability()['crepe'] is not None:
            body.append(Gtk.Label(label='CREPE unavailable: install the optional CPU neural dependencies.',xalign=0))
        self.parameter_summary = Gtk.Label(xalign=0, wrap=True)
        self.parameter_summary.add_css_class("dim-label")
        body.append(self.parameter_summary)
        self.settings = Gtk.Expander(label="Analysis parameters")
        grid = Gtk.Grid(column_spacing=16, row_spacing=8, margin_top=8, margin_bottom=8)
        self.settings.set_child(grid)
        self.controls: dict[str, Gtk.Entry | Gtk.SpinButton] = {}
        specifications = [
            ("fmin", "Minimum (Hz or note)", "C2"), ("fmax", "Maximum (Hz or note)", "D6"),
            ("sample_rate", "Analysis rate (Hz)", 22050), ("frame_length", "Frame (samples)", 2048),
            ("hop_length", "Hop (samples)", 512), ("resolution", "Pitch bins (semitones)", 0.1),
            ("switch_prob", "Voicing switch probability", 0.01), ("no_trough_prob", "No-trough probability", 0.001),
            ("max_transition_rate", "Transition (octaves/s)", 35.92), ("a4_hz", "A4 tuning (Hz)", 440.0),
            ("max_memory_mb", "Maximum DSP memory (MiB)", initial_config.max_memory_mb),
        ]
        for i, (key, title, default) in enumerate(specifications):
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            group.append(Gtk.Label(label=title, xalign=0))
            entry = Gtk.Entry(text=str(default), hexpand=True, width_chars=10)
            if key == "max_memory_mb":
                entry.set_tooltip_text("Positive, finite budget for estimated DSP working arrays, in MiB. Does not reserve memory or limit actual process RSS; excludes Python, libraries and JIT overhead. Applies to loading, analysis and note generation.")
            entry.connect("changed", self._parameters_changed)
            self.controls[key] = entry
            group.append(entry)
            grid.attach(group, i % 5, i // 5, 1, 1)
        body.append(self.settings)

        self.figure = create_figure(dark=self.style_manager.get_dark())
        self.canvas = VocalScopeCanvas(self.figure)
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas.set_size_request(500, 330)
        body.append(self.canvas)
        self.toolbar = NavigationToolbar2GTK4(self.canvas)
        body.append(self.toolbar)
        from .transcription.workspace import TranscriptionWorkspace
        self.transcription=TranscriptionWorkspace(self,body)
        body.set_vexpand(True)
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.spinner = Gtk.Spinner()
        status_row.append(self.spinner)
        self.status = Gtk.Label(label="Ready. Voicing probability describes voicing, not pitch correctness.", xalign=0, wrap=True, selectable=True)
        status_row.append(self.status)
        body.append(status_row)
        self.estimator_selector.connect('notify::selected',self._backend_changed)
        self.model_selector.connect('notify::selected',self._parameters_changed)
        self.voicing_entry.connect('changed',self._parameters_changed)
        self._parameters_changed()

    def _read_estimator(self) -> EstimatorConfig:
        identifier=self.estimator_choices[self.estimator_selector.get_selected()]
        kwargs={'estimator_id':identifier,'crepe_model':['full','tiny'][self.model_selector.get_selected()]}
        if identifier=='yin':kwargs['yin_voicing_threshold']=float(self.voicing_entry.get_text())
        if identifier=='crepe':kwargs['crepe_voicing_threshold']=float(self.voicing_entry.get_text())
        return EstimatorConfig(**kwargs)

    def _backend_changed(self,*_args):
        identifier=self.estimator_choices[self.estimator_selector.get_selected()]
        self.model_selector.set_sensitive(identifier=='crepe')
        self.voicing_entry.set_sensitive(identifier!='pyin')
        self.voicing_entry.set_text({'pyin':'Viterbi','yin':'0.6','crepe':'0.5'}[identifier])
        for name,entry in self.controls.items():
            classical=name in ('frame_length','hop_length','sample_rate')
            pyin_only=name in ('resolution','switch_prob','no_trough_prob','max_transition_rate')
            entry.set_sensitive(not (identifier=='crepe' and classical) and not (identifier!='pyin' and pyin_only))
        self._parameters_changed()

    def _read_config(self) -> AnalysisConfig:
        values = {name: control.get_text().strip() for name, control in self.controls.items()}
        identifier=self.estimator_choices[self.estimator_selector.get_selected()]
        defaults=AnalysisConfig()
        inactive=['resolution','switch_prob','no_trough_prob','max_transition_rate'] if identifier!='pyin' else []
        if identifier=='crepe':inactive+=['frame_length','hop_length','sample_rate']
        for name in inactive:values[name]=str(getattr(defaults,name))
        a4 = float(values["a4_hz"])
        return AnalysisConfig(
            fmin=parse_frequency(values.pop("fmin"), a4), fmax=parse_frequency(values.pop("fmax"), a4),
            **{k: int(v) if k in ("sample_rate", "frame_length", "hop_length") else float(v) for k, v in values.items()},
        )

    def _read_memory_budget(self) -> float:
        """Validate the current resource policy independently of cached F0 settings."""
        value = float(self.controls["max_memory_mb"].get_text().strip())
        return AnalysisConfig(max_memory_mb=value).max_memory_mb

    def _parameters_changed(self, *_args) -> None:
        if not hasattr(self, "parameter_summary"):
            return
        try:
            c = self._read_config()
            settings=self._read_estimator()
            text = (f"{settings.estimator_id} · {c.fmin:.2f}–{c.fmax:.2f} Hz · {c.sample_rate:,} Hz · frame {c.frame_length} ({1000*c.frame_length/c.sample_rate:.1f} ms) · hop {c.hop_length} ({1000*c.hop_length/c.sample_rate:.1f} ms) · no post-smoothing")
            if settings.estimator_id=='crepe':
                text=(f'crepe {settings.crepe_model} · CPU · {c.fmin:.2f}–{c.fmax:.2f} Hz · native 16 kHz · 1024-sample window (64 ms) · {settings.crepe_hop_length}-sample hop (10 ms default) · no post-smoothing')
            text += f" · DSP budget {c.max_memory_mb:g} MiB (estimated arrays, not allocated memory)"
            if self.result is not None and (c != self.result.config or asdict(settings)!=self.result.estimator_configuration):
                text += " · Parameters changed; displayed result uses previous settings."
            self.parameter_summary.set_text(text)
        except (ValueError, KeyError) as exc:
            self.parameter_summary.set_text(f"Invalid parameters: {exc}")

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy = busy
        self.open_button.set_sensitive(not busy)
        self.analyze_button.set_sensitive(not busy and self.source is not None)
        self.export_button.set_sensitive(not busy and self.result is not None)
        self.settings.set_sensitive(not busy)
        self.backend_controls.set_sensitive(not busy)
        self.spinner.set_spinning(busy)
        self.status.set_text(message)
        if hasattr(self,"transcription"):self.transcription.refresh()

    def _start_job(self, work: Callable, success: Callable, message: str) -> bool:
        if self.busy or self.closed:
            return False
        self._set_busy(True, message)

        def deliver(value, failure):
            if not self.closed:
                self._set_busy(False, "Ready")
                if failure is not None:
                    self.status.set_text(f"Failed: {failure}")
                else:
                    success(value)
            return GLib.SOURCE_REMOVE

        def worker():
            try:
                value = work()
            except Exception as exc:
                GLib.idle_add(deliver, None, f"{type(exc).__name__}: {exc}")
            else:
                GLib.idle_add(deliver, value, None)

        # A non-daemon coordinator lets close-triggered child cleanup finish
        # before interpreter exit, without blocking GTK's close callback.
        Thread(target=worker, name="vocalscope-worker", daemon=False).start()
        return True

    def _choose_file(self, *_args) -> None:
        if self.busy or self.closed or self.dialog_cancellable is not None:
            return
        dialog = Gtk.FileDialog(title="Open vocal recording", modal=True)
        supported = Gtk.FileFilter(name="Audio (WAV, FLAC, OGG)")
        for mime in ("audio/x-wav", "audio/wav", "audio/flac", "audio/ogg", "application/ogg"):
            supported.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(supported)
        everything = Gtk.FileFilter(name="All files (decoder support varies)")
        everything.add_pattern("*")
        filters.append(everything)
        dialog.set_filters(filters)
        self.dialog_cancellable = Gio.Cancellable()
        dialog.open(self, self.dialog_cancellable, self._file_selected)

    def _file_selected(self, dialog, response) -> None:
        try:
            selected = dialog.open_finish(response)
            if self.closed:
                return
            path = selected.get_path()
            if path is None:
                self.status.set_text("Choose a local file; remote URIs are unsupported.")
                return
            self.load_path(Path(path))
        except GLib.Error as exc:
            if not self.closed and not self._dialog_cancelled(exc):
                self.status.set_text(f"File chooser failed: {exc.message}")
        finally:
            self.dialog_cancellable = None
            if self.closed:
                GLib.idle_add(self.close)

    @staticmethod
    def _dialog_cancelled(error: GLib.Error) -> bool:
        return (any(error.matches(Gtk.dialog_error_quark(), code) for code in (Gtk.DialogError.DISMISSED, Gtk.DialogError.CANCELLED))
                or error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED))

    def load_path(self, path: Path) -> None:
        """Shared by the native chooser and GUI integration tests."""
        if self.busy or not self.transcription.guard():
            return
        try:
            config = self._read_config()
        except ValueError as exc:
            self.status.set_text(str(exc))
            return

        def loaded(metadata: AudioMetadata):
            self.source = path
            self.result = None
            self.transcription.project=None
            self.transcription.playback.audio_loaded(path)
            self.file_label.set_text(f"{metadata.filename} · {metadata.duration_seconds:.3f} s · {metadata.original_sample_rate:,} Hz · {metadata.channels} channel(s)")
            draw_result(self.figure, None, dark=self.style_manager.get_dark())
            self.canvas.draw_idle()
            self.toolbar.update()
            self._set_busy(False, "Loaded. " + " ".join(metadata.warnings))

        self._start_job(lambda: load_audio(path, config).metadata, loaded, "Loading audio…")

    def _analyze(self, *_args) -> None:
        if self.source is None or self.busy or not self.transcription.guard():
            return
        try:
            config = self._read_config()
            settings = self._read_estimator()
        except ValueError as exc:
            self.status.set_text(f"Invalid parameters: {exc}")
            return
        path = self.source

        def completed(result: AnalysisResult):
            self.result = result
            self.transcription.project=None
            self.file_label.set_text(f"{result.metadata.filename} · {result.metadata.duration_seconds:.3f} s · {result.metadata.original_sample_rate:,} Hz · {result.metadata.channels} channel(s)")
            draw_result(self.figure, result, dark=self.style_manager.get_dark())
            self.transcription.playback.decorate()
            self.canvas.draw_idle()
            self.toolbar.update()
            self._parameters_changed()
            self._set_busy(False, f"Complete · {result.estimator_id} · {len(result.voiced)} frames · {result.voiced.mean():.1%} voiced · inference {result.runtime_seconds:.2f} s, initialization {result.initialization_seconds:.2f} s. " + " ".join(result.warnings))

        self._start_job(lambda: analyze_in_process(path, config, self.cancelled, settings), completed, "Analyzing… Loading the selected estimator and tracking pitch.")

    def _choose_export(self, *_args) -> None:
        if self.busy or self.closed or self.result is None or self.dialog_cancellable is not None:
            return
        dialog = Gtk.FileDialog(title="Choose export folder (existing results are protected)", modal=True)
        self.dialog_cancellable = Gio.Cancellable()
        dialog.select_folder(self, self.dialog_cancellable, self._export_selected)

    def _export_selected(self, dialog, response) -> None:
        try:
            selected = dialog.select_folder_finish(response)
            if self.closed:
                return
            folder = selected.get_path()
            if folder is None:
                self.status.set_text("Choose a local export folder.")
                return
            self.export_to(Path(folder))
        except GLib.Error as exc:
            if not self.closed and not self._dialog_cancelled(exc):
                self.status.set_text(f"Export chooser failed: {exc.message}")
        finally:
            self.dialog_cancellable = None
            if self.closed:
                GLib.idle_add(self.close)

    def export_to(self, folder: Path) -> None:
        result = self.result
        if result is not None:
            self._start_job(lambda: export_bundle(result, folder), lambda paths: self.status.set_text(f"Exported CSV, JSON and PNG to {folder}"), "Exporting results…")

    def _theme_changed(self, *_args) -> None:
        if hasattr(self, "figure") and not self.closed:
            if self.transcription.project:self.transcription.draw()
            else:
                draw_result(self.figure, self.result, dark=self.style_manager.get_dark())
                self.transcription.playback.decorate()
            self.canvas.draw_idle()
            self.toolbar.update()

    def _on_close(self, *_args) -> bool:
        if self.closed:
            return self.dialog_cancellable is not None
        self.closed = True
        if hasattr(self,'transcription') and hasattr(self.transcription,'playback'):self.transcription.shutdown()
        self.cancelled.set()
        self.style_manager.disconnect_by_func(self._theme_changed)
        if self.dialog_cancellable is not None:
            # GTK 4.24.1 on this Wayland host segfaults when a FileDialog is
            # cancelled before presentation (also reproduced without this app).
            # Keep its parent alive through presentation and async completion.
            def dismiss_pending():
                if self.dialog_cancellable is not None:
                    self.dialog_cancellable.cancel()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(600,dismiss_pending)
            return True
        return False


class VocalScopeApplication(Adw.Application):
    def __init__(self, *, max_memory_mb: float = 1024.0):
        self.max_memory_mb = AnalysisConfig(max_memory_mb=max_memory_mb).max_memory_mb
        super().__init__(application_id="io.github.vocalscope.VocalScope", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self) -> None:
        window = self.get_active_window() or VocalScopeWindow(self, max_memory_mb=self.max_memory_mb)
        window.present()


def run(*, max_memory_mb: float = 1024.0) -> int:
    Gtk.init()
    if Gdk.Display.get_default() is None:
        raise ValueError("No graphical display available. Launch from a Wayland desktop, or use 'vocalscope analyze'.")
    if Gtk.get_minor_version() < 10:
        raise ValueError("GTK 4.10 or later is required for the native file chooser.")
    return VocalScopeApplication(max_memory_mb=max_memory_mb).run([])

