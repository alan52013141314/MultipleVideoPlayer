"""Run the agreed 12-cell, 60-second smoke against real VLC, no server."""
import json
import os
import sys
import time
from pathlib import Path
from multiprocessing import freeze_support

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "VideoPlayer" / "src"))


def main():
    import psutil
    from workspace_launcher import prepare_environment
    prepare_environment()
    evidence = ROOT / "verification"
    evidence.mkdir(exist_ok=True)
    os.environ["GRIDPLAYER_DATA_DIR"] = str(evidence / "player-data")
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.main.init_log import init_log
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env
    init_app_env()
    init_log()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from PyQt5.QtCore import Qt, QMimeData, QUrl, QPointF, QPoint
    from PyQt5.QtGui import QDropEvent, QDragEnterEvent
    from PyQt5.QtTest import QTest
    from gridplayer.workspace_window import WorkspaceWindow

    def wait_until(test, timeout=25000):
        deadline = time.monotonic() + timeout / 1000
        while not test():
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for playback state")
            QTest.qWait(50)

    def memory():
        process = psutil.Process()
        return round(sum(p.memory_info().rss for p in [process] + process.children(recursive=True) if p.is_running()) / 1024**2, 1)

    result = {"vlc": env.VLC_VERSION, "material": "synthetic 1280x720 30fps H.264/AAC", "checks": []}
    w = WorkspaceWindow(restore=False)
    w.show()
    try:
        assert len(w.cells) == 6
        app.processEvents()
        w.grab().save(str(evidence / "player-six.png"))
        for _ in range(6):
            w.add_cell()
        assert len(w.cells) == 12 and not w.add.isEnabled()
        w.columns.setCurrentText("4")
        w.resize(1450, 930)
        paths = [str(evidence / "media" / "clip1.mp4")] * 12
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        QApplication = type(app)
        enter = QDragEnterEvent(QPoint(20, 20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(w.cells[0], enter)
        drop = QDropEvent(QPointF(20,20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(w.cells[0], drop)
        assert drop.isAccepted()
        wait_until(lambda: all(c.block and c.block.is_video_initialized for c in w.cells))
        wait_until(lambda: all(c.block.time > 500 for c in w.cells))
        started = time.monotonic()
        result["memory_start_mib"] = memory()
        result["checks"].append("6 defaults, 12 cells, multi-file Qt drop, real VLC playback")
        w.grab().save(str(evidence / "player-twelve.png"))
        first = w.cells[0]
        original_blocks = [c.block for c in w.cells]
        first.span.setCurrentIndex(1)
        w.cells[1].span.setCurrentIndex(2)
        assert [c.block for c in w.cells] == original_blocks
        QTest.qWait(400)
        w.grab().save(str(evidence / "player-spans.png"))
        first.span.setCurrentIndex(0)
        w.cells[1].span.setCurrentIndex(0)
        w.borderless.setChecked(True)
        w.fullscreen.setChecked(True)
        QTest.qWait(250)
        w.fullscreen.setChecked(False)
        assert bool(w.windowFlags() & Qt.FramelessWindowHint)
        w.borderless.setChecked(False)
        result["checks"].append("horizontal/vertical spans reuse players; independent borderless/fullscreen")
        first.volume.setValue(37)
        first.mute.setChecked(False)
        w.global_mute.setChecked(True)
        assert first.state.video.volume == .37 and not first.state.video.is_muted
        w.global_mute.setChecked(False)
        assert not first.block.global_muted and first.state.video.volume == .37
        # Keep the smoke quiet without overwriting individual preferences.
        w.global_mute.setChecked(True)
        first.seekbar.setValue(2000)
        first.seekbar.sliderReleased.emit()
        wait_until(lambda: first.block.time >= 2000)
        first.play.click()
        wait_until(lambda: first.state.video.is_paused)
        first.block.seek(1000)
        first.head.click()
        first.block.seek(3000)
        first.tail.click()
        assert first.state.video.loop_start == 1000 and first.state.video.loop_end == 3000
        samples = []
        first.block.time_change.connect(lambda t, d: samples.append(t))
        QTest.qWait(600)
        first.play.click()
        wait_until(lambda: any(a > b + 700 for a,b in zip(samples, samples[1:])), 12000)
        first.clear.click()
        assert first.state.video.loop_start is None and first.state.video.loop_end is None
        result["checks"].append("seek, pause/play, AB loop observed, clear, per-cell volume/global mute")
        # Exactly five source-folder switches, including previous and next.
        for direction in (1, 1, -1, 1, -1):
            old = first.block
            first.switch(direction)
            assert first.block is not old
            wait_until(lambda: first.block.is_video_initialized)
            assert first.state.video.loop_start is None and first.state.video.loop_end is None
            assert w.cells[1].block is original_blocks[1]
        result["switches"] = 5
        result["memory_after_switches_mib"] = memory()
        first.block.seek(1000)
        first.head.click()
        first.block.seek(3500)
        first.tail.click()
        a = w.store.save("測試 A", w.snapshot())
        first.volume.setValue(64)
        b = w.store.save("測試 B", w.snapshot())
        a_bytes = w.store._path(a).read_bytes()
        b_bytes = w.store._path(b).read_bytes()
        while time.monotonic() - started < 60:
            QTest.qWait(250)
            assert all(c.block and not c.block._is_error for c in w.cells)
        result["play_seconds"] = round(time.monotonic() - started, 1)
        result["memory_end_mib"] = memory()
        result["checks"].append("12-cell one-minute playback; no player errors")
        for key, volume in ((a,.37), (b,.64)):
            w.restore(w.store.read(key))
            wait_until(lambda: all(c.block and c.block.is_video_initialized for c in w.cells))
            assert w.cells[0].state.video.volume == volume
            assert all(c.state.video.is_paused for c in w.cells)
        w.cells[0].volume.setValue(52)
        w.close()
        QTest.qWait(400)
        assert w.store._path(a).read_bytes() == a_bytes
        assert w.store._path(b).read_bytes() == b_bytes
        assert w.store.read("last").cells[0].video.volume == .52
        w = WorkspaceWindow()
        w.show()
        wait_until(lambda: all(c.block and c.block.is_video_initialized for c in w.cells))
        assert w.cells[0].state.video.volume == .52
        assert all(c.state.video.is_paused for c in w.cells)
        result["checks"].append("two named presets restore; close overwrites last only; reopen paused")
        result["passed"] = True
    finally:
        w.close()
        QTest.qWait(400)
        (evidence / "player-smoke.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    freeze_support()
    main()
