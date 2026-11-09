# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Luqman234
"""Real display integration; never counts an inaccessible desktop as a pass."""

from pathlib import Path
import os
import time

import pytest

pytestmark = [pytest.mark.gui,
              pytest.mark.filterwarnings('ignore:.*is deprecated.*:DeprecationWarning:matplotlib.backends'),
              pytest.mark.filterwarnings('ignore:.*deprecated.*:DeprecationWarning:gi')]


def test_native_window_worker_responsiveness_and_export(tmp_path, analyzed_case, record_testsuite_property):
    gi = pytest.importorskip("gi", reason="System PyGObject unavailable")
    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Gtk, Gdk, GLib
    except (ValueError, ImportError) as exc:
        pytest.skip(f"GTK4/libadwaita unavailable: {exc}")
    Gtk.init()
    if Gdk.Display.get_default() is None:
        pytest.skip("No accessible graphical display; physical GUI verification unavailable")
    display_type = Gdk.Display.get_default().__gtype__.name
    record_testsuite_property("gdk_display_type", display_type)
    if os.environ.get("GDK_BACKEND") == "wayland":
        assert "Wayland" in display_type
    from vocalscope.gui import VocalScopeApplication
    _, result = analyzed_case("sine_A4")
    application = VocalScopeApplication()
    application.register(None)
    application.activate()
    window = application.get_active_window()
    assert window is not None
    heartbeats = []

    def heartbeat():
        heartbeats.append(time.monotonic())
        return GLib.SOURCE_CONTINUE

    timer = GLib.timeout_add(20, heartbeat)

    def until(predicate, timeout=90):
        deadline = time.monotonic() + timeout
        context = GLib.MainContext.default()
        while not predicate() and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)
        assert predicate(), window.status.get_text()

    try:
        until(lambda: window.get_mapped())
        record_testsuite_property("native_window_mapped", "true")
        # Exercise native chooser setup/cancellation through the actual button.
        initial_status = window.status.get_text()
        window.open_button.emit("clicked")
        assert window.dialog_cancellable is not None
        # Let GTK present the native chooser before simulating dismissal.
        GLib.timeout_add(400,lambda:window.dialog_cancellable.cancel() if window.dialog_cancellable else None)
        until(lambda: window.dialog_cancellable is None)
        assert window.status.get_text() == initial_status
        window.load_path(Path(result.metadata.path))
        until(lambda: not window.busy)
        assert window.source is not None
        assert window.analyze_button.get_sensitive()
        before = len(heartbeats)
        window.analyze_button.emit("clicked")
        assert window.busy
        assert not window.open_button.get_sensitive()
        assert not window._start_job(lambda: None, lambda _: None, "must reject concurrent job")
        until(lambda: not window.busy)
        assert len(heartbeats) > before + 2
        record_testsuite_property("gtk_heartbeat_count", str(len(heartbeats) - before))
        assert window.result is not None
        assert "Complete" in window.status.get_text()
        complete_status = window.status.get_text()
        window.export_button.emit("clicked")
        assert window.dialog_cancellable is not None
        # Let GTK present the native chooser before simulating dismissal.
        GLib.timeout_add(400,lambda:window.dialog_cancellable.cancel() if window.dialog_cancellable else None)
        until(lambda: window.dialog_cancellable is None)
        assert window.status.get_text() == complete_status
        window.export_to(tmp_path)
        until(lambda: not window.busy)
        assert len(list(tmp_path.glob("*.json"))) == 1
        assert len(list(tmp_path.glob("*.csv"))) == 1
        assert len(list(tmp_path.glob("*.png"))) == 1
        # Installed backend selection uses the same process-isolated GUI path.
        for identifier in window.estimator_choices[1:]:
            window.estimator_selector.set_selected(window.estimator_choices.index(identifier))
            assert not window.controls['switch_prob'].get_sensitive()
            if identifier=='crepe':window.model_selector.set_selected(1)  # tiny CPU smoke
            assert window.controls['frame_length'].get_sensitive()==(identifier!='crepe')
            window.analyze_button.emit('clicked')
            until(lambda:not window.busy)
            assert window.result is not None
            assert window.result.estimator_id==identifier,window.status.get_text()
            assert ('correlation' if identifier=='yin' else 'periodicity') in window.figure.axes[1].get_ylabel()
            record_testsuite_property(f'{identifier}_gui_analysis','passed')
        window.load_path(tmp_path / "missing.wav")
        until(lambda: not window.busy)
        assert "Failed" in window.status.get_text()
        window.open_button.emit('clicked')
        assert window.dialog_cancellable is not None
        window.close()
        until(lambda:not window.get_mapped())
        assert window.closed and window.dialog_cancellable is None
        record_testsuite_property('close_while_chooser_pending','passed')
    finally:
        GLib.source_remove(timer)
        window.close()
        application.quit()

