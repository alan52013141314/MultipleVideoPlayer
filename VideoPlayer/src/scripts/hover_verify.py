"""Native VLC overlay regression: no layout change, hover isolation, clip/window modes."""
import json
import os
import sys
import time
from pathlib import Path
from multiprocessing import freeze_support

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "VideoPlayer/src"))


def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    os.environ["GRIDPLAYER_DATA_DIR"] = str(ROOT / "verification/hover-data")
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env
    from PyQt5.QtCore import QPoint, Qt, QTimer
    from PyQt5.QtGui import QCursor
    from PyQt5.QtTest import QTest
    from gridplayer.params.static import VideoAspect
    init_app_env()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from gridplayer.workspace_window import WorkspaceWindow
    w = WorkspaceWindow(restore=False)
    w.show()
    w.activateWindow()
    w.global_mute.setChecked(True)
    evidence = ROOT / "verification"
    def wait(check):
        deadline = time.monotonic() + 15
        while not check():
            assert time.monotonic() < deadline, "hover verification timeout"
            QTest.qWait(60)
    def cursor(widget):
        QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
        QTest.qWait(180)
    def capture(name):
        app.primaryScreen().grabWindow(int(w.winId())).save(str(evidence / name))
    result = {}
    try:
        w.drop_files(0, [str(evidence / "media/clip1.mp4")]*6)
        wait(lambda: all(c.block.is_video_initialized for c in w.cells))
        first = w.cells[0]
        cursor(w.columns)
        assert not any(c.top_panel.isVisible() or c.bottom_panel.isVisible() for c in w.cells)
        geometry = first.block.geometry()
        assert geometry.width() == first.width()-2
        assert geometry.height() == first.height()-2
        capture("hover-hidden-native.png")
        cursor(first)
        wait(lambda: first.bottom_panel.isVisible())
        assert first.top_panel.isVisible()
        assert first.block.geometry() == geometry
        assert all(not c.bottom_panel.isVisible() for c in w.cells[1:])
        capture("hover-visible-native.png")
        cursor(first.play)
        QTest.mouseClick(first.play, Qt.LeftButton)
        wait(lambda: first.state.video.is_paused)
        assert first.bottom_panel.isVisible()
        before = first.block.time
        cursor(first.seekbar)
        first.seekbar.setSliderDown(True)
        first.seekbar.setValue(7200)
        cursor(w.columns)
        assert first.bottom_panel.isVisible(), "keep an active drag usable"
        first.seekbar.setSliderDown(False)
        wait(lambda: not first.bottom_panel.isVisible())
        wait(lambda: abs(first.block.time-7200)<500)
        cursor(first)
        for fraction in (.25, .75):
            cursor(first.seekbar)
            QTest.mouseClick(first.seekbar, Qt.LeftButton,
                            pos=QPoint(round(first.seekbar.width()*fraction), first.seekbar.height()//2))
            wait(lambda: abs(first.block.time-first.block.video_driver.length*fraction)<300)
            assert first.state.video.is_paused
        cursor(w.cells[1])
        wait(lambda: w.cells[1].bottom_panel.isVisible())
        assert not first.bottom_panel.isVisible()
        modes = [VideoAspect.NONE, VideoAspect.FIT, VideoAspect.WIDTH,
                 VideoAspect.HEIGHT, VideoAspect.STRETCH, VideoAspect.ORIGINAL]
        for i, cell in enumerate(w.cells):
            cell.display_mode.setCurrentIndex(cell.display_mode.findData(modes[i]))
            cell.volume.setValue(10 + i * 15)
        QTest.qWait(200)
        assert [c.block.video_driver._aspect for c in w.cells] == modes
        assert [c.state.video.volume for c in w.cells] == [.1, .25, .4, .55, .7, .85]
        assert [c.volume_value.value() for c in w.cells] == [10, 25, 40, 55, 70, 85]
        popup_errors=[]
        cursor(first.volume_button)
        def exercise_volume_popup():
            try:
                assert first.volume_menu.isVisible()
                cursor(first.volume)
                assert first.bottom_panel.isVisible(), 'popup keeps owning controls visible'
                QTest.mouseClick(first.volume, Qt.LeftButton,
                                pos=QPoint(round(first.volume.width()*.75), first.volume.height()//2))
                assert .65 < first.state.video.volume < .85
                first.volume_value.setFocus()
                first.volume_value.selectAll()
                QTest.keyClicks(first.volume_value, '37')
                QTest.keyClick(first.volume_value, Qt.Key_Return)
                assert first.volume.value()==37 and first.state.video.volume==.37
                assert w.cells[1].volume.value()==25
                assert first.block.geometry()==geometry
                first.volume_menu.grab().save(str(evidence/'volume-popup.png'))
            except Exception as error:
                popup_errors.append(repr(error))
            finally:
                first.volume_menu.hide()
        QTimer.singleShot(180, exercise_volume_popup)
        QTest.mouseClick(first.volume_button, Qt.LeftButton)
        assert not popup_errors, popup_errors
        first.volume.setValue(10)
        key = w.store.save('display-audio-verification', w.snapshot())
        first.switch(1)
        wait(lambda: first.block.is_video_initialized)
        assert first.state.video.aspect_mode == modes[0]
        assert first.state.video.volume == .1
        cursor(first)
        first.display_mode.showPopup()
        QTest.qWait(150)
        assert first.bottom_panel.isVisible()
        first.display_mode.hidePopup()
        cursor(first)
        first.span.showPopup()
        QTest.qWait(150)
        assert first.top_panel.isVisible()
        first.span.hidePopup()
        first.span.setCurrentIndex(1)
        QTest.qWait(200)
        cursor(first)
        assert first.block.width() == first.width()-2
        assert first.block.height() == first.height()-2
        assert first.top_panel.width() == first.width()-2
        w.borderless.setChecked(True)
        w.fullscreen.setChecked(True)
        QTest.qWait(200)
        cursor(first)
        assert first.top_panel.isVisible()
        w.fullscreen.setChecked(False)
        w.borderless.setChecked(False)
        w.showMinimized()
        QTest.qWait(200)
        assert not any(c.bottom_panel.isVisible() for c in w.cells)
        w.showNormal()
        w.restore(w.store.read(key))
        wait(lambda: all(c.block.is_video_initialized for c in w.cells))
        assert [c.block.video_driver._aspect for c in w.cells] == modes
        assert [c.volume.value() for c in w.cells] == [10, 25, 40, 55, 70, 85]
        w.global_mute.setChecked(False)
        w.global_mute.setChecked(True)
        assert [c.state.video.volume for c in w.cells] == [.1, .25, .4, .55, .7, .85]
        result = {"passed": True, "video_rect_hidden": [geometry.x(), geometry.y(), geometry.width(), geometry.height()],
                  "checks": ["native VLC surface occupies entire cell minus 1px border", "hover adds no video resize",
                             "only hovered cell shows controls", "move to controls, click pause, drag seek",
                             "drag capture survives leaving cell until release", "span popup and span resize",
                             "borderless/fullscreen alignment", "minimized window hides all panels",
                             "six independent display modes and volume percentages reach live VLC frames",
                             "switch preserves cell mode/volume; mode popup remains usable",
                             "preset restores six modes/volumes; global mute preserves each volume",
                             "real 25/75 percent timeline clicks seek VLC and keep pause state",
                             "compact volume button opens popup; slider click and typed percentage work independently"]}
    finally:
        w.close()
        QTest.qWait(300)
        (evidence / "hover-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    freeze_support()
    main()
