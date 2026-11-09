# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Exercise the real CLI -> GTK -> isolated DSP -> editable-project path."""

from pathlib import Path
import time

import numpy as np
import pytest


@pytest.mark.gui
@pytest.mark.parametrize("initial", [1024, 2048])
def test_native_cli_memory_setting_analysis_and_transcription(
        initial, tmp_path, analyzed_case, monkeypatch, record_testsuite_property):
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Gdk, GLib
    Gtk.init()
    if Gdk.Display.get_default() is None:
        pytest.skip("Native memory-setting verification requires a graphical display")

    from vocalscope.cli import main
    from vocalscope.gui import VocalScopeApplication
    from vocalscope.transcription.serialization import load_project

    _, reference = analyzed_case("sine_A4")
    initialize = VocalScopeApplication.__init__
    failures = []
    completed = []
    windows = []
    beats = []
    deadline = time.monotonic() + 90

    def scenario(w):
        yield lambda: w.get_mapped()
        assert w._read_config().max_memory_mb == initial
        assert w._read_memory_budget() == initial
        w.settings.set_expanded(True)
        control = w.controls["max_memory_mb"]
        assert "not" in control.get_tooltip_text().lower()
        for value in ("0", "-1", "nan", "inf", "bad"):
            control.set_text(value)
            assert "Invalid parameters" in w.parameter_summary.get_text()
            with pytest.raises(ValueError):
                w._read_config()
        control.set_text("1")
        w.load_path(Path(reference.metadata.path))
        yield lambda: not w.busy
        assert w.source is None
        assert "Maximum DSP memory (MiB)" in w.status.get_text()
        control.set_text("2048")
        assert "DSP budget 2048 MiB" in w.parameter_summary.get_text()
        w.load_path(Path(reference.metadata.path))
        yield lambda: not w.busy
        assert w.source is not None
        before = len(beats)
        w.analyze_button.emit("clicked")
        assert w.busy and not w.settings.get_sensitive()
        yield lambda: not w.busy
        assert len(beats) > before + 2
        assert w.result is not None, w.status.get_text()
        assert w.result.config.max_memory_mb == 2048
        acoustic = w.result
        contour = acoustic.f0_hz.copy()
        control.set_text("1")
        w.analyze_button.emit("clicked")
        yield lambda: not w.busy
        assert "configured budget is 1 MiB" in w.status.get_text()
        assert w.result is acoustic

        # Current budget governs source reload for cached-pitch note generation.
        ws = w.transcription
        control.set_text("bad")
        ws.generate.emit("clicked")
        assert not w.busy and "Invalid parameters" in w.status.get_text()
        control.set_text("1")
        ws.generate.emit("clicked")
        yield lambda: not w.busy
        assert ws.project is None
        assert "Maximum DSP memory (MiB)" in w.status.get_text()
        control.set_text("3072")
        ws.generate.emit("clicked")
        assert w.busy
        yield lambda: not w.busy
        assert ws.project is not None, w.status.get_text()
        assert len(ws.project.notes) == 1
        assert ws.project.timings["dsp_resource_policy"]["max_memory_mb"] == 3072
        assert ws.project.acoustic.config.max_memory_mb == 2048
        np.testing.assert_array_equal(ws.project.acoustic.f0_hz, contour)
        saved = tmp_path / f"memory-{initial}.notes.json"
        ws.save_to(saved)
        yield lambda: not w.busy
        assert load_project(saved).timings["dsp_resource_policy"]["max_memory_mb"] == 3072
        ws.load_from(saved)
        yield lambda: not w.busy
        assert w._read_config().max_memory_mb == 3072
        assert ws.project.acoustic.config.max_memory_mb == 2048
        assert w.settings.get_sensitive()
        record_testsuite_property(f"memory_{initial}_display", Gdk.Display.get_default().__gtype__.name)
        record_testsuite_property(f"memory_{initial}_analysis_budget_mib", "2048")
        record_testsuite_property(f"memory_{initial}_note_worker_budget_mib", "3072")
        record_testsuite_property(f"memory_{initial}_heartbeat_count", str(len(beats)))
        completed.append(True)

    def activated(app):
        w = app.get_active_window()
        windows.append(w)
        steps = scenario(w)
        waiting = None

        def tick():
            nonlocal waiting
            beats.append(time.monotonic())
            try:
                assert time.monotonic() < deadline, w.status.get_text()
                if waiting is not None and not waiting():
                    return GLib.SOURCE_CONTINUE
                waiting = next(steps)
            except StopIteration:
                w.close(); app.quit()
                return GLib.SOURCE_REMOVE
            except BaseException as exc:
                failures.append(exc)
                w.close(); app.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(20, tick)
        return GLib.SOURCE_REMOVE

    def initialized(app, **kwargs):
        initialize(app, **kwargs)
        # Other native tests register applications without running/unregistering
        # them. Isolate this in-process CLI run from their retained D-Bus IDs.
        app.set_application_id(f"io.github.vocalscope.MemoryBudgetTest{initial}")
        app.connect("activate", lambda current: GLib.idle_add(activated, current))

    # GI registers vfuncs when the class is defined; use a normal activate
    # signal plus an idle callback rather than monkeypatching do_activate.
    monkeypatch.setattr(VocalScopeApplication, "__init__", initialized)
    timed_out = []

    def timeout():
        timed_out.append(True)
        for w in windows:
            w.close()
        from gi.repository import Gio
        app = Gio.Application.get_default()
        if app is not None:
            app.quit()
        return GLib.SOURCE_REMOVE

    watchdog = GLib.timeout_add_seconds(95, timeout)
    try:
        arguments = ["gui"] if initial == 1024 else ["gui", "--max-memory-mb", str(initial)]
        assert main(arguments) == 0
        assert not timed_out, "Native scenario did not finish within 95 seconds"
        if failures:
            raise failures[0]
        assert completed == [True]
        assert windows and all(w.closed for w in windows)
    finally:
        if GLib.MainContext.default().find_source_by_id(watchdog) is not None:
            GLib.source_remove(watchdog)
        for w in windows:
            w.close()
