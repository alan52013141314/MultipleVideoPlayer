"""Exercise PR-007 against real Qt controls and libVLC, using isolated test settings."""
import json
import os
import sys
import time
from multiprocessing import freeze_support
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'VideoPlayer/src'))


def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    software = '--software' in sys.argv
    data = ROOT / 'verification' / ('interaction-sw' if software else 'interaction-hw')
    data.mkdir(parents=True, exist_ok=True)
    os.environ['GRIDPLAYER_DATA_DIR'] = str(data)
    from gridplayer.main.init_app_env import init_app_env
    init_app_env()
    from gridplayer.main.init_app import init_app
    app = init_app()
    from gridplayer.settings import Settings
    from gridplayer.params.static import VideoAspect as A, VideoDriver
    Settings().set('player/video_driver', VideoDriver.VLC_SW if software else VideoDriver.VLC_HW)
    from gridplayer.params import env
    from gridplayer.utils.libvlc import init_vlc
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from gridplayer.workspace_window import WorkspaceWindow
    from PyQt5.QtCore import Qt, QEvent, QPoint, QPointF, QSettings, QTimer
    from PyQt5.QtGui import QCursor, QMouseEvent, QWheelEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QStyle, QStyleOptionSlider, QToolTip, QDoubleSpinBox, QDialogButtonBox

    def wait(condition):
        deadline = time.monotonic() + 15
        while not condition():
            assert time.monotonic() < deadline, 'interaction timed out'
            QTest.qWait(30)

    def move(widget, point, buttons=Qt.NoButton):
        app.sendEvent(widget, QMouseEvent(QEvent.MouseMove, QPointF(point),
                      QPointF(widget.mapToGlobal(point)), Qt.NoButton, buttons, Qt.NoModifier))

    def cursor(widget):
        QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
        QTest.qWait(180)

    w = WorkspaceWindow(data_directory=data, restore=False)
    result = {'passed': False, 'backend': 'software' if software else 'hardware'}
    try:
        w.show()
        w.activateWindow()
        w.global_mute.setChecked(True)
        w.drop_files(0, [str(ROOT/'verification/media/clip1.mp4')]*2)
        # Replace a still-initializing player, as with startup restore + CLI files.
        w.drop_files(0, [str(ROOT/'verification/media/clip1.mp4')])
        wait(lambda: all(c.block and c.block.is_video_initialized for c in w.cells[:2]))
        assert all(c.block.video_driver.video_surface.isVisible() for c in w.cells[:2])
        first, second = w.cells[:2]
        for cell in (first, second):
            cell.block.set_pause(True)
        wait(lambda: first.state.video.is_paused and second.state.video.is_paused)
        QTest.qWait(250)
        first.block.user_seek(1000)
        second.block.user_seek(2000)
        QTest.qWait(200)
        cursor(w.add)
        w.add.setFocus()
        w.last_hovered_cell = None
        w.seek_step.setValue(.5)
        before = first.block.time
        QTest.keyClick(w.add, Qt.Key_Right)
        assert abs(first.block.time - (before + 500)) < 60
        cursor(second)
        assert w.last_hovered_cell is second
        cursor(w.add)
        before = second.block.time
        QTest.keyClick(w.add, Qt.Key_Left)
        assert abs(second.block.time - (before - 500)) < 60
        positions = [c.block.time for c in (first, second)]
        w.seek_step.setFocus()
        QTest.keyClick(w.seek_step, Qt.Key_Right)
        assert [c.block.time for c in (first, second)] == positions
        assert float(QSettings(str(data/'workspace.ini'),QSettings.IniFormat).value('seek_seconds')) == .5
        w.add.setFocus()

        first.block.set_loop_start_time(2000)
        first.block.set_loop_end_time(4000)
        first.block.user_seek(3000)
        first.update_markers()
        cursor(first)
        wait(lambda: first.bottom_panel.isVisible())
        slider = first.seekbar
        option = QStyleOptionSlider()
        slider.initStyleOption(option)
        handle = slider.style().subControlRect(QStyle.CC_Slider,option,QStyle.SC_SliderHandle,slider)
        decoder_times = []
        first.block.video_driver.time_changed.connect(decoder_times.append)
        QTest.mousePress(slider,Qt.LeftButton,pos=handle.center())
        move(slider,QPoint(round(slider.width()*.75),slider.height()//2),Qt.LeftButton)
        QTest.qWait(140)
        assert slider.isSliderDown() and first.block.scrubbing
        assert first.block.time > 7500 and first.block.loop_suspended
        assert QToolTip.text().startswith('00:00:') and '.' in QToolTip.text()
        target = slider.value()
        QTest.mouseRelease(slider,Qt.LeftButton,pos=QPoint(round(slider.width()*.75),slider.height()//2))
        assert not first.block.scrubbing and not slider.isSliderDown()
        assert first.state.loop_suspended and first.state.video.is_paused
        # Paused libVLC may not emit TimeChanged until playback resumes.
        first.block.set_pause(False)
        wait(lambda: any(abs(t-target)<700 for t in decoder_times))
        first.block.set_pause(True)
        wait(lambda: first.state.video.is_paused)
        assert (first.state.video.loop_start,first.state.video.loop_end)==(2000,4000)
        QTest.mouseClick(first.back_to_loop,Qt.LeftButton)
        assert not first.block.loop_suspended and first.block.time==2000
        assert first.state.video.is_paused
        QTest.mouseClick(slider,Qt.LeftButton,pos=QPoint(round(slider.width()*.25),slider.height()//2))
        assert not first.block.loop_suspended

        # Native surface is enlarged before clipping; pan can reveal the complete source.
        first.display_mode.setCurrentIndex(first.display_mode.findData(A.HEIGHT))
        frame = first.block.video_driver
        QTest.qWait(150)
        assert frame.workspace_video_rect().width() > frame.width()
        geometry = first.block.geometry()
        QTest.mousePress(first.block,Qt.MiddleButton,pos=QPoint(160,100))
        move(first.block,QPoint(230,100),Qt.MiddleButton)
        QTest.mouseRelease(first.block,Qt.MiddleButton,pos=QPoint(230,100))
        assert frame._pan[0] > 0 and frame._pan[1] == 0
        frame.pan_by(100000,100000)
        assert frame.workspace_video_rect().x()==0
        assert first.block.geometry()==geometry
        first.display_mode.setCurrentIndex(first.display_mode.findData(A.NONE))
        assert frame._pan == (0,0)
        first.block.user_seek(7000)
        first.update_markers()
        state=w.snapshot()
        assert state.cells[0].loop_suspended
        w.restore(state)
        wait(lambda: w.cells[0].block and w.cells[0].block.is_video_initialized)
        wait(lambda: not getattr(w.cells[0],'frame_busy',False))
        assert w.cells[0].block.loop_suspended
        assert w.cells[0].state.video.current_position>=6500
        assert w.cells[0].block.video_driver._pan==(0,0)
        first=w.cells[0]
        frame=first.block.video_driver
        first.clear_markers()
        first.block.user_seek(3000)
        first.display_mode.setCurrentIndex(first.display_mode.findData(A.HEIGHT))
        point=QPoint(frame.width()//3,frame.height()//3)
        before=frame.workspace_video_rect()
        u=(point.x()-before.x())/before.width()
        v=(point.y()-before.y())/before.height()
        wheel=QWheelEvent(QPointF(point),QPointF(first.block.mapToGlobal(point)),QPoint(),QPoint(0,120),
                          Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        app.sendEvent(first.block,wheel)
        after=frame.workspace_video_rect()
        assert abs(after.x()+u*after.width()-point.x())<=1.5
        assert abs(after.y()+v*after.height()-point.y())<=1.5
        assert abs(first.state.video.scale-1.1)<.001
        assert w.cells[1].state.video.scale==1
        frame.pan_by(50,20)
        center=first.state.view_center
        zoom=first.state.video.scale
        players=[c.block for c in w.cells]
        w.focus_cell(first)
        QTest.qWait(100)
        assert first.isVisible() and not w.cells[1].isVisible()
        w.escape_view()
        QTest.qWait(100)
        assert w.cells[1].isVisible() and players==[c.block for c in w.cells]
        snapshot=w.snapshot()
        w.restore(snapshot)
        wait(lambda:w.cells[0].block.is_video_initialized)
        wait(lambda:not getattr(w.cells[0],'frame_busy',False))
        first=w.cells[0]
        frame=first.block.video_driver
        assert abs(frame._scale-zoom)<.001
        assert all(abs(a-b)<.01 for a,b in zip(frame._view_center,center))
        first.reset_view()
        assert first.state.video.scale==1 and first.state.view_center==(.5,.5)
        first.state.video.loop_start=2000
        first.state.video.loop_end=4000
        first.update_markers()
        slider=first.seekbar
        original_time=first.block.time
        QTest.mousePress(slider,Qt.LeftButton,pos=QPoint(slider.marker_x(2000),2))
        move(slider,QPoint(slider.marker_x(3000),2),Qt.LeftButton)
        QTest.mouseRelease(slider,Qt.LeftButton,pos=QPoint(slider.marker_x(3000),2))
        assert 2800<first.state.video.loop_start<3200
        assert first.block.time==original_time
        dialog_checks=[]
        def fill_ab():
            dialog=app.activeModalWidget()
            fields=dialog.findChildren(QDoubleSpinBox)
            buttons=dialog.findChild(QDialogButtonBox)
            fields[0].setValue(5)
            fields[1].setValue(4)
            dialog_checks.append(not buttons.button(QDialogButtonBox.Ok).isEnabled())
            fields[0].setValue(1.125)
            fields[1].setValue(4.375)
            dialog_checks.append(buttons.button(QDialogButtonBox.Ok).isEnabled())
            buttons.button(QDialogButtonBox.Ok).click()
        QTimer.singleShot(100,fill_ab)
        first.edit_markers()
        assert dialog_checks==[True,True]
        assert (first.state.video.loop_start,first.state.video.loop_end)==(1125,4375)
        first.clear_markers()
        first.block.user_seek(3000)
        first.step_frame(1)
        wait(lambda:not first.frame_busy)
        assert frame.exact_frame.isVisible() and first.state.video.is_paused
        forward=first.block.frame_seconds
        first.step_frame(-1)
        wait(lambda:not first.frame_busy)
        assert first.block.frame_seconds<forward
        first.step_frame(1)
        wait(lambda:not first.frame_busy)
        assert abs(first.block.frame_seconds-forward)<.00001
        first.block.play_pause()
        wait(lambda:not first.state.video.is_paused)
        assert not frame.exact_frame.isVisible()
        result.update(passed=True, version=w.windowTitle(), checks=[
            'first-cell keyboard fallback; last hovered target after pointer leaves',
            'fractional step saved; numeric input arrow editing does not seek',
            'held handle previews real VLC seeks; tooltip includes milliseconds',
            'outside AB suspends; back button returns to A paused; inside AB resumes',
            'middle drag pans enlarged image; clamps at image edge; mode resets',
            'preset restores suspended loop and out-of-loop position',
            'PR008 cursor anchored wheel zoom; independent cells; saved view center and scale',
            'PR008 focus/return preserves players; marker drag preserves playback position',
            'PR008 exact decoded frame next/back/next round trip and playback resume'])
    finally:
        w.close()
        QTest.qWait(300)
        (ROOT/'verification'/f'interaction-{result["backend"]}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    freeze_support()
    main()
