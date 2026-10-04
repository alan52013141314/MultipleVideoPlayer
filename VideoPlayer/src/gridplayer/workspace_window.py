"""Desktop controls around upstream VideoBlock and its VLC process manager."""
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QEvent, QSettings, pyqtSignal, QObject, QRunnable, QThreadPool
from PyQt5.QtGui import QKeySequence, QCursor, QRegion, QImage, QTransform
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QShortcut, QSizePolicy, QSpinBox, QVBoxLayout, QWidget, QFileDialog,
    QToolButton, QMenu, QWidgetAction, QDoubleSpinBox, QAbstractSpinBox, QLineEdit, QTextEdit, QPlainTextEdit,
    QDialog, QDialogButtonBox, QFormLayout,
)

from gridplayer.models.video import Video
from gridplayer.params.static import VideoAspect
from gridplayer.player.manager import Context, Commands
from gridplayer.player.managers.video_driver import VideoDriverManager
from gridplayer.utils.app_dir import get_app_data_dir
from gridplayer.widgets.video_block import VideoBlock
from gridplayer.widgets.click_slider import ClickSlider
from gridplayer.widgets.marker_slider import MarkerSlider
from gridplayer.workspace_version import VERSION
from gridplayer.workspace_state import CellState, WorkspaceState, PresetStore, placement, adjacent_video, scan_folder, folder_videos


def clock(ms):
    if ms is None:
        return "—"
    seconds = max(0, ms) // 1000
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def button(text, callback, tooltip=None):
    widget = QPushButton(text)
    widget.setToolTip(tooltip or text)
    widget.clicked.connect(callback)
    return widget


class ElidingLabel(QLabel):
    def setText(self, text):
        self.full_text=text
        super().setText(self.fontMetrics().elidedText(text,Qt.ElideRight,max(1,self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(getattr(self,'full_text',''))


class WorkspaceBlock(VideoBlock):
    ready = pyqtSignal()
    notice = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        self.global_muted = False
        self.loop_suspended = False
        self.scrubbing = False
        self._pan_position = None
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
        self.video_driver.enable_workspace_pan()

    def init_overlay(self):
        # The cell owns hover controls above the native VLC video surface.
        overlay = QWidget(self)
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        return overlay

    def show_overlay(self):
        pass

    @property
    def loop_enabled(self):
        v = self.video_params
        return (v is not None and v.loop_start is not None and v.loop_end is not None
                and not self.loop_suspended and not self.scrubbing)

    def user_seek(self, target):
        if not self.is_video_initialized:
            return
        self.leave_frame_preview()
        target = max(0, min(round(target), max(0, self.video_driver.length - 1)))
        v = self.video_params
        if v.loop_start is not None and v.loop_end is not None:
            self.loop_suspended = not v.loop_start <= target <= v.loop_end
        self.video_driver.set_time(target)
        self.time = target

    def leave_frame_preview(self):
        self.frame_request = None
        if getattr(self,'frame_preview_active',False):
            self.frame_preview_active=False
            self.video_driver.clear_exact_frame()

    def play_pause(self):
        self.leave_frame_preview()
        super().play_pause()

    def time_changed(self, new_time):
        # Decoder callbacks from an earlier seek must not snap a held slider back.
        if not self.scrubbing and not getattr(self, 'frame_preview_active', False):
            super().time_changed(new_time)

    def wheelEvent(self, event):
        if self.is_video_initialized and event.angleDelta().y():
            self.video_driver.zoom_at(self.video_driver.mapFromGlobal(event.globalPos()),
                                      1.1 ** max(-20,min(20,event.angleDelta().y()/120)))
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_position = event.globalPos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_position is not None:
            delta = event.globalPos() - self._pan_position
            self._pan_position = event.globalPos()
            self.video_driver.pan_by(delta.x(), delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._pan_position is not None:
            self._pan_position = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @property
    def loop_start(self):
        return self.video_params.loop_start if self.loop_enabled else 0

    @property
    def loop_end(self):
        if self.loop_enabled:
            return self.video_params.loop_end
        return max(0, self.video_driver.length - 100)

    def set_muted(self, muted):
        if self.video_params is None:
            return
        self.video_params.is_muted = muted
        if self.is_video_initialized:
            self.video_driver.audio_set_mute(muted or self.global_muted)
        self.is_muted_change.emit(muted)

    def load_video_finish(self):
        v = self.video_params
        duration = self.video_driver.length
        invalid = any(t is not None and not 0 <= t <= duration for t in (v.loop_start, v.loop_end))
        invalid |= v.loop_start is not None and v.loop_end is not None and v.loop_start >= v.loop_end
        if invalid:
            v.loop_start = v.loop_end = None
            self.notice.emit("來源長度已變更或區間無效，已停用此格 AB；已存 preset 保持不變。")
        v.current_position = min(max(v.current_position, 0), max(0, duration - 100))
        super().load_video_finish()
        self.ready.emit()

    def cleanup(self):
        self._reload_timer.stop()
        super().cleanup()


class ControlPanel(QFrame):
    """Owned tool window, as in upstream OverlayBlockFloating, above VLC's HWND."""
    def __init__(self, cell):
        super().__init__(cell, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("controlPanel")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        self.parent().dragEnterEvent(event)

    def dropEvent(self, event):
        self.parent().dropEvent(event)


class FolderScanSignals(QObject):
    finished = pyqtSignal(object, object, object, str)


class FolderScan(QRunnable):
    def __init__(self, cell, request, directory):
        super().__init__()
        self.cell, self.request, self.directory = cell, request, directory
        self.signals = FolderScanSignals()

    def run(self):
        try:
            paths, error = scan_folder(self.directory), ""
        except OSError as exc:
            paths, error = [], str(exc)
        self.signals.finished.emit(self.cell, self.request, paths, error)


class FrameSignals(QObject):
    finished = pyqtSignal(object, object, object, str)


class FrameJob(QRunnable):
    def __init__(self, cell, request, path, seconds, direction, block):
        super().__init__()
        self.cell,self.request,self.path,self.seconds,self.direction,self.block=cell,request,path,seconds,direction,block
        self.signals=FrameSignals()

    def run(self):
        try:
            from gridplayer.utils.frame_step import adjacent_frame
            result=adjacent_frame(self.path,self.seconds,self.direction,
                                  lambda: self.block.frame_request is not self.request)
            error=''
        except Exception as exc:
            result,error=None,str(exc)
        self.signals.finished.emit(self.cell,self.request,result,error)


class VideoCell(QFrame):
    def __init__(self, owner, state):
        super().__init__()
        self.owner = owner
        self.state = state
        self.block = None
        self.drop_request = None
        self.setObjectName("videoCell")
        self.setAcceptDrops(True)
        self.setMinimumSize(260, 210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.surface = QVBoxLayout(self)
        self.surface.setContentsMargins(0, 0, 0, 0)
        self.surface.setSpacing(0)
        self.top_panel = ControlPanel(self)
        self.bottom_panel = ControlPanel(self)
        heading = QHBoxLayout(self.top_panel)
        heading.setContentsMargins(5, 4, 5, 4)
        heading.setSpacing(4)
        self.title = QLabel()
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading.addWidget(self.title, 1)
        self.focus_button = button('⛶', lambda: owner.focus_cell(self), '只看此格／返回網格')
        self.focus_button.setFixedWidth(25)
        heading.addWidget(self.focus_button)
        self.tools_button = QToolButton()
        self.tools_button.setText('⋯')
        self.tools_button.setToolTip('逐格、AB 時間')
        self.tools_button.setPopupMode(QToolButton.InstantPopup)
        self.tools_menu = QMenu(self.tools_button)
        self.tools_button.setMenu(self.tools_menu)
        self.step_back = self.tools_menu.addAction('上一格（暫停）', lambda: self.step_frame(-1))
        self.step_next = self.tools_menu.addAction('下一格（暫停）', lambda: self.step_frame(1))
        self.edit_ab = self.tools_menu.addAction('輸入 A／B 時間…', self.edit_markers)
        heading.addWidget(self.tools_button)
        self.span = QComboBox()
        self.span.addItems(["1×1", "橫跨 2 欄", "縱跨 2 列", "2×2"])
        self.span.setCurrentIndex({(1,1):0, (1,2):1, (2,1):2, (2,2):3}[state.rows, state.cols])
        self.span.currentIndexChanged.connect(self.set_span)
        heading.addWidget(self.span)
        self.remove_button = button("×", lambda: owner.remove_cell(self), "移除此格")
        self.remove_button.setFixedWidth(25)
        heading.addWidget(self.remove_button)
        self.placeholder = button("拖入影片／開啟檔案", self.choose_file)
        self.placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.surface.addWidget(self.placeholder)
        layout = QVBoxLayout(self.bottom_panel)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(3)
        self.seekbar = MarkerSlider(Qt.Horizontal)
        self.seekbar.marker_moved.connect(self.move_marker)
        self.seekbar.setToolTip("點擊跳至該位置，或拖曳滑桿定位")
        self.seekbar.setRange(0, 10000)
        self.seekbar.setEnabled(False)
        self.seekbar.value_text = lambda value: f"{clock(value)}.{value % 1000:03}"
        self.seekbar.sliderPressed.connect(self.begin_seek)
        self.seekbar.valueChanged.connect(self.preview_seek)
        self.seekbar.sliderReleased.connect(self.seek)
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self.commit_seek)
        layout.addWidget(self.seekbar)
        controls = QHBoxLayout()
        controls.setSpacing(3)
        self.previous = button("⏮", lambda: self.switch(-1), "來源資料夾上一條")
        self.play = button("▶", self.play_pause, "播放／暫停")
        self.next = button("⏭", lambda: self.switch(1), "來源資料夾下一條")
        self.head = button("A", lambda: self.mark(True), "設 head：目前位置")
        self.tail = button("B", lambda: self.mark(False), "設 tail：目前位置")
        self.clear = button("清除", self.clear_markers, "清除 AB 標記")
        for control in (self.previous, self.play, self.next, self.head, self.tail, self.clear):
            control.setMinimumWidth(25)
            controls.addWidget(control)
        self.volume_button = QToolButton()
        self.volume_button.setText("音量 100%")
        self.volume_button.setToolTip("此格獨立音量；點開調節")
        self.volume_button.setPopupMode(QToolButton.InstantPopup)
        self.volume_menu = QMenu(self.volume_button)
        self.volume_button.setMenu(self.volume_menu)
        controls.addWidget(self.volume_button)
        layout.addLayout(controls)
        self.volume_controls = QWidget()
        self.volume_controls.setMinimumWidth(245)
        audio = QHBoxLayout(self.volume_controls)
        audio.setContentsMargins(8, 8, 8, 8)
        self.mute = QCheckBox("靜音")
        self.mute.toggled.connect(self.set_mute)
        self.volume = ClickSlider(Qt.Horizontal)
        self.volume.setMinimumWidth(80)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setToolTip("只調整此格音量")
        self.volume.setAccessibleName("此格音量")
        self.volume.valueChanged.connect(self.set_volume)
        self.volume_value = QSpinBox()
        self.volume_value.setRange(0, 100)
        self.volume_value.setValue(100)
        self.volume_value.setSuffix("%")
        self.volume_value.setFixedWidth(65)
        self.volume_value.setToolTip("直接輸入此格音量百分比")
        self.volume_value.valueChanged.connect(self.volume.setValue)
        self.time_label = ElidingLabel("00:00:00 / 00:00:00")
        audio.addWidget(self.volume, 1)
        audio.addWidget(self.volume_value)
        audio.addWidget(self.mute)
        volume_action = QWidgetAction(self.volume_menu)
        volume_action.setDefaultWidget(self.volume_controls)
        self.volume_menu.addAction(volume_action)
        view = QHBoxLayout()
        view.addWidget(QLabel("畫面"))
        self.display_mode = QComboBox()
        for label, mode in (
            ("Fit · 完整顯示", VideoAspect.NONE),
            ("Fill · 填滿裁切", VideoAspect.FIT),
            ("符合寬度", VideoAspect.WIDTH),
            ("符合高度", VideoAspect.HEIGHT),
            ("Stretch · 拉伸", VideoAspect.STRETCH),
            ("1:1 · 原始像素", VideoAspect.ORIGINAL),
        ):
            self.display_mode.addItem(label, mode)
        self.display_mode.setToolTip("此格獨立設定；換片沿用，並隨 preset 保存")
        self.display_mode.setMinimumWidth(0)
        self.display_mode.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.display_mode.currentIndexChanged.connect(self.set_display_mode)
        view.addWidget(self.display_mode, 1)
        self.zoom_label = QLabel('1.00×')
        view.addWidget(self.zoom_label)
        self.reset_button = button('↺', self.reset_view, '重置視圖：1 倍並置中')
        self.reset_button.setFixedWidth(25)
        view.addWidget(self.reset_button)
        layout.addLayout(view)
        self.markers = ElidingLabel("A —   B —")
        self.markers.setMinimumWidth(0)
        self.markers.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.time_label.setMinimumWidth(0)
        self.time_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        loop_row = QHBoxLayout()
        loop_row.addWidget(self.time_label, 1)
        loop_row.addWidget(self.markers, 1)
        self.back_to_loop = button("回到循環", self.resume_loop, "Back to looping：回到 A 並恢復區間循環")
        self.back_to_loop.setText('↻')
        self.back_to_loop.setFixedWidth(25)
        loop_row.addWidget(self.back_to_loop)
        layout.addLayout(loop_row)
        self.refresh()
        if state.video is not None:
            self.load(state.video, paused=True)

    def update_overlay(self):
        popup = (self.span.view().isVisible() or self.display_mode.view().isVisible()
                 or self.volume_menu.isVisible() or self.tools_menu.isVisible())
        dragging = self.seekbar.isSliderDown() or self.volume.isSliderDown() or self.seekbar.marker_drag is not None
        active = self.owner.isActiveWindow() or QApplication.activeWindow() in (self.top_panel, self.bottom_panel)
        cell_rect = QRect(self.mapToGlobal(QPoint()), self.size())
        viewport = self.owner.viewport
        clip = cell_rect.intersected(QRect(viewport.mapToGlobal(QPoint()), viewport.size()))
        hovered = clip.contains(QCursor.pos())
        if hovered and active:
            self.owner.last_hovered_cell = self
        visible = (self.isVisible() and not self.owner.isMinimized() and
                   (active or popup) and not QApplication.activeModalWidget() and
                   (hovered or popup or dragging))
        self.compact_info()
        for panel, at_bottom in ((self.top_panel, False), (self.bottom_panel, True)):
            if not visible or clip.isEmpty():
                panel.hide()
                continue
            height = panel.sizeHint().height()
            position = cell_rect.topLeft() + QPoint(1, self.height()-height-1 if at_bottom else 1)
            rect = QRect(position, panel.sizeHint())
            rect.setWidth(self.width()-2)
            panel.setGeometry(rect)
            mask_rect = rect.intersected(clip).translated(-rect.topLeft())
            if mask_rect.isEmpty():
                panel.hide()
                continue
            panel.setMask(QRegion(mask_rect))
            if not panel.isVisible():
                panel.show()
                panel.raise_()

    def hideEvent(self, event):
        self.volume_menu.hide()
        self.top_panel.hide()
        self.bottom_panel.hide()
        super().hideEvent(event)

    def refresh(self):
        video = self.state.video
        name = Path(str(video.uri)).name if video else "空格"
        index = self.owner.cells.index(self) + 1 if self in self.owner.cells else len(self.owner.cells) + 1
        self.title.setText(f"{index:02}  {name}")
        if video and self.state.playlist:
            paths = [Path(p) for p in self.state.playlist]
            if Path(str(video.uri)) in paths:
                self.title.setText(f"{index:02}  {name}  ·  {paths.index(Path(str(video.uri)))+1}/{len(paths)}")
        self.title.setToolTip(str(video.uri) if video else "拖入本機影片")
        ready = self.block is not None and self.block.is_video_initialized and not self.block._is_error
        for action in (self.step_back, self.step_next):
            action.setEnabled(bool(ready and video.is_paused and not getattr(self,'frame_busy',False)))
        self.edit_ab.setEnabled(ready)
        for control in (self.play, self.head, self.tail, self.seekbar):
            control.setEnabled(ready)
        if ready:
            self.seekbar.setMaximum(max(1, self.block.video_driver.length - 1))
        self.clear.setEnabled(video is not None)
        for control, direction in ((self.previous, -1), (self.next, 1)):
            try:
                target = adjacent_video(video.uri, direction, self.state.playlist) if video else None
            except OSError:
                target = None
            control.setEnabled(target is not None)
        if video:
            self.mute.blockSignals(True)
            self.mute.setChecked(video.is_muted)
            self.mute.blockSignals(False)
            self.volume.blockSignals(True)
            self.volume.setValue(round(video.volume * 100))
            self.volume.blockSignals(False)
            self.volume_value.blockSignals(True)
            self.volume_value.setValue(self.volume.value())
            self.volume_value.blockSignals(False)
            self.update_volume_button()
            self.display_mode.blockSignals(True)
            self.display_mode.setCurrentIndex(self.display_mode.findData(video.aspect_mode))
            self.display_mode.blockSignals(False)
            self.play.setText("▶" if video.is_paused else "Ⅱ")
        self.update_markers()

    def update_markers(self):
        v = self.state.video
        enabled = v and v.loop_start is not None and v.loop_end is not None
        suspended = self.block.loop_suspended if self.block else self.state.loop_suspended
        self.state.loop_suspended = suspended
        self.back_to_loop.setEnabled(bool(enabled and self.block and self.block.is_video_initialized))
        self.markers.setText(f"A {clock(v.loop_start if v else None)}   B {clock(v.loop_end if v else None)}" + ("   暫離循環" if enabled and suspended else "   ↻" if enabled else ""))
        self.seekbar.set_markers(v.loop_start if v else None,v.loop_end if v else None,suspended)
        self.compact_info()

    def compact_info(self):
        v=self.state.video
        a,b=(v.loop_start,v.loop_end) if v else (None,None)
        exact=lambda t: '—' if t is None else f'{clock(t)}.{t%1000:03}'
        duration=self.block.video_driver.length if self.block and self.block.is_video_initialized else 0
        time=f'{clock(v.current_position if v else 0)} / {clock(duration)}'
        length=f'  Δ {exact(b-a)}' if a is not None and b is not None else ''
        markers=f'A {exact(a)}  B {exact(b)}{length}'
        if a is not None and b is not None:
            markers += ' 暫離' if self.state.loop_suspended else ' ↻'
        self.time_label.setToolTip(f'{exact(v.current_position if v else 0)} / {exact(duration)}')
        self.markers.setToolTip(markers+'；⋯ 可直接輸入 AB 時間')
        short=lambda t: '—' if t is None else (f'{t/1000:g}' if t<60000 else clock(t).lstrip('0').lstrip(':'))
        if self.width()<500:
            time=f'{clock(v.current_position if v else 0)[3:] if (v.current_position if v else 0)<3600000 else clock(v.current_position)} / {clock(duration)[3:] if duration<3600000 else clock(duration)}'
            markers=f'A{short(a)} B{short(b)}'+(f' Δ{short(b-a)}s' if a is not None and b is not None else '')
        self.time_label.setText(time)
        self.markers.setText(markers)
        self.back_to_loop.setText('↩' if self.state.loop_suspended else '↻')

    def sync_view(self):
        if self.block and self.block.is_video_initialized:
            frame=self.block.video_driver
            self.state.video.scale=frame._scale
            self.state.view_center=frame._view_center
            self.zoom_label.setText(f'{frame._scale:.2f}×')

    def restore_view(self):
        if self.block:
            self.block.video_driver.set_view_center(self.state.view_center)
            self.sync_view()
            # A resized native VLC surface can remain black when start-paused.
            # Decode the saved frame without advancing it, after restoring geometry.
            if self.state.video.is_paused:
                self.step_frame(0)

    def reset_view(self):
        if self.block:
            self.block.video_driver.reset_view()

    def step_frame(self, direction):
        if not self.block or not self.block.is_video_initialized or not self.state.video.is_paused or getattr(self,'frame_busy',False):
            return
        if self.block.video_driver.media.is_audio_only:
            self.owner.notify('此來源沒有影片影格')
            return
        self.frame_busy=True
        request=object()
        self.block.frame_request=request
        self.block.frame_preview_active=True
        seconds=getattr(self.block,'frame_seconds',self.block.time/1000) if self.block.video_driver.exact_frame.isVisible() else self.block.time/1000
        job=FrameJob(self,request,str(self.state.video.uri),seconds,direction,self.block)
        job.signals.finished.connect(self.owner.frame_finished)
        self.owner.frame_jobs[request]=job
        self.owner.folder_pool.start(job)
        self.refresh()
        self.owner.notify('正在解碼相鄰影格…')

    def move_marker(self, name, value):
        if not self.block or not self.block.is_video_initialized:
            return
        v=self.state.video
        if name=='A':
            v.loop_start=max(0,min(value,v.loop_end-1 if v.loop_end is not None else self.block.video_driver.length-1))
        else:
            v.loop_end=min(self.block.video_driver.length,max(value,(v.loop_start or 0)+1))
        self.block.loop_suspended=not (v.loop_start is not None and v.loop_end is not None and v.loop_start<=self.block.time<=v.loop_end)
        self.update_markers()

    def edit_markers(self):
        if not self.block or not self.block.is_video_initialized:
            return
        dialog=QDialog(self.owner)
        dialog.setWindowTitle('A／B 時間（秒，可輸入小數）')
        form=QFormLayout(dialog)
        fields=[]
        for title,value in (('A',self.state.video.loop_start),('B',self.state.video.loop_end)):
            field=QDoubleSpinBox()
            field.setDecimals(3)
            field.setRange(0,self.block.video_driver.length/1000)
            field.setValue((value if value is not None else (0 if title=='A' else self.block.video_driver.length))/1000)
            form.addRow(title,field)
            fields.append(field)
        length=QLabel()
        def changed():
            delta=fields[1].value()-fields[0].value()
            length.setText(f'區間長度：{delta:.3f} 秒' if delta>0 else 'A 必須小於 B')
            buttons.button(QDialogButtonBox.Ok).setEnabled(delta>0)
        form.addRow(length)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        for field in fields:
            field.valueChanged.connect(changed)
        changed()
        if dialog.exec_()==QDialog.Accepted:
            self.state.video.loop_start,self.state.video.loop_end=[round(f.value()*1000) for f in fields]
            self.block.loop_suspended=not self.state.video.loop_start<=self.block.time<=self.state.video.loop_end
            self.update_markers()

    def set_span(self, index):
        self.state.rows, self.state.cols = [(1,1), (1,2), (2,1), (2,2)][index]
        self.owner.relayout()

    def choose_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "選擇影片", "", "影片 (*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.wmv *.ts);;所有檔案 (*)")
        if paths:
            self.owner.drop_files(self.owner.cells.index(self), paths)

    def load(self, video, paused=False):
        same_source = self.state.video is not None and str(self.state.video.uri) == str(video.uri)
        if not same_source:
            self.state.loop_suspended = False
            self.state.view_center = (0.5, 0.5)
        self.dispose()
        self.state.video = video.model_copy(deep=True)
        v = self.state.video
        v.is_paused = paused
        path = Path(str(v.uri))
        if not path.is_file():
            self.placeholder.setText("找不到來源（保留 preset 資料）\n開啟另一部影片")
            self.placeholder.show()
            self.refresh()
            return
        v.uri = path.resolve()
        self.placeholder.hide()
        self.block = WorkspaceBlock(video_driver=self.owner.driver.video_driver(), context=self.owner.context, parent=self)
        self.block.setAttribute(Qt.WA_DeleteOnClose)
        self.block.global_muted = self.owner.global_mute.isChecked()
        self.block.loop_suspended = self.state.loop_suspended
        self.surface.addWidget(self.block)
        self.block.time_change.connect(self.update_time)
        self.block.is_paused_change.connect(self.update_play)
        self.block.ready.connect(self.refresh)
        self.block.ready.connect(self.restore_view)
        self.block.video_driver.view_changed.connect(self.sync_view)
        self.block.notice.connect(self.owner.notify)
        self.block.video_driver.error.connect(lambda message: self.owner.notify(f"影片讀取失敗：{path.name} — {message}"))
        self.block.set_video(v)
        self.block.show()
        self.refresh()

    def dispose(self):
        self.frame_busy=False
        self.seek_timer.stop()
        self.volume_menu.hide()
        self.top_panel.hide()
        self.bottom_panel.hide()
        if self.block is not None:
            block, self.block = self.block, None
            block.frame_request=None
            # Disconnect state updates before any replacement can receive late events.
            block.time_change.disconnect(self.update_time)
            block.is_paused_change.disconnect(self.update_play)
            block.ready.disconnect(self.refresh)
            self.surface.removeWidget(block)
            block.close_silently()
        self.placeholder.show()

    def update_time(self, time, duration):
        if not self.seekbar.isSliderDown():
            self.seekbar.setMaximum(max(1, duration - 1))
            self.seekbar.setValue(time)
        self.time_label.setText(f"{clock(time)} / {clock(duration)}")
        self.compact_info()

    def update_play(self, paused):
        self.play.setText("▶" if paused else "Ⅱ")
        self.refresh()

    def play_pause(self):
        if self.block and self.block.is_video_initialized:
            self.block.play_pause()

    def begin_seek(self):
        if self.block:
            self.block.scrubbing = True

    def preview_seek(self):
        if self.seekbar.isSliderDown() and not self.seek_timer.isActive():
            self.seek_timer.start(50)

    def commit_seek(self):
        if self.block and self.block.is_video_initialized:
            self.block.user_seek(self.seekbar.value())
            self.update_markers()

    def seek(self):
        self.seek_timer.stop()
        self.commit_seek()
        if self.block:
            self.block.scrubbing = False

    def resume_loop(self):
        if self.block and self.state.video.loop_start is not None and self.state.video.loop_end is not None:
            self.block.user_seek(self.state.video.loop_start)
            self.update_markers()

    def switch(self, direction):
        if not self.state.video:
            return
        try:
            path = adjacent_video(self.state.video.uri, direction, self.state.playlist)
            if path is not None:
                self.load(Video(uri=path, volume=self.volume.value()/100, is_muted=self.mute.isChecked(),
                                aspect_mode=self.display_mode.currentData()))
            self.refresh()
        except OSError as error:
            self.owner.notify(str(error))

    def mark(self, head):
        if not self.block or not self.block.is_video_initialized:
            return
        v = self.state.video
        position = self.block.time
        if (head and v.loop_end is not None and position >= v.loop_end) or (not head and v.loop_start is not None and position <= v.loop_start):
            self.owner.notify("AB 無效：head 必須小於 tail，請清除後重新設定。")
            return
        if head:
            self.block.set_loop_start_time(position)
        else:
            self.block.set_loop_end_time(position)
        self.block.loop_suspended = False
        self.update_markers()

    def clear_markers(self):
        self.state.loop_suspended = False
        if self.block:
            self.block.loop_suspended = False
        if self.state.video:
            self.state.video.loop_start = self.state.video.loop_end = None
        self.update_markers()

    def set_mute(self, muted):
        if self.state.video:
            self.state.video.is_muted = muted
        if self.block:
            self.block.set_muted(muted)
        self.update_volume_button()

    def set_volume(self, value):
        self.volume_value.blockSignals(True)
        self.volume_value.setValue(value)
        self.volume_value.blockSignals(False)
        if self.state.video:
            self.state.video.volume = value / 100
        if self.block and self.block.is_video_initialized:
            self.block.set_volume(value / 100)
        self.update_volume_button()

    def update_volume_button(self):
        self.volume_button.setText("靜音" if self.mute.isChecked() else f"音量 {self.volume.value()}%")
        self.volume_button.setToolTip(f"此格音量 {self.volume.value()}%；點開調節滑桿、百分比或靜音")

    def set_display_mode(self, _index):
        mode = self.display_mode.currentData()
        if self.state.video:
            self.state.video.aspect_mode = mode
        if self.block and self.block.is_video_initialized:
            self.block.set_aspect(mode)
            self.reset_view()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.owner.drop_files(self.owner.cells.index(self), [u.toLocalFile() for u in event.mimeData().urls()])
        event.acceptProposedAction()


class WorkspaceWindow(QMainWindow):
    def __init__(self, data_directory=None, restore=True):
        super().__init__()
        self.setWindowTitle(f"GridPlayer — 多格影片工具 | {VERSION}")
        self.resize(1280, 800)
        self.context = Context()
        self.context.commands = Commands()
        self.context.commands.warning = self.notify
        self.context.is_disable_click_pause = False
        self.context.is_disable_wheel_seek = True
        self.driver = VideoDriverManager(context=self.context, parent=self)
        data_root = data_directory or get_app_data_dir()
        data_root.mkdir(parents=True, exist_ok=True)
        self.preferences = QSettings(str(data_root / "workspace.ini"), QSettings.IniFormat)
        self.store = PresetStore(data_root / "presets")
        self.last_hovered_cell = None
        self.focused_cell = None
        self.frame_jobs = {}
        self.cells = []
        self.folder_pool = QThreadPool(self)
        self.folder_pool.setMaxThreadCount(2)
        self.folder_jobs = {}
        self._closing = False
        self._normal_geometry = self.geometry()
        outer = QWidget()
        self.setCentralWidget(outer)
        root = QVBoxLayout(outer)
        root.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        label = QLabel("GRIDPLAYER   /   本機影片")
        label.setStyleSheet("font-weight:700; color:#8ed7ce")
        top.addWidget(label)
        top.addStretch()
        self.add = button("＋ 新增格", self.add_cell)
        top.addWidget(self.add)
        top.addWidget(QLabel("欄數"))
        self.columns = QComboBox()
        self.columns.addItems(["2", "3", "4"])
        self.columns.setCurrentText("3")
        self.columns.currentIndexChanged.connect(self.relayout)
        top.addWidget(self.columns)
        self.global_mute = QCheckBox("全部靜音")
        self.global_mute.toggled.connect(self.apply_global_mute)
        top.addWidget(self.global_mute)
        self.borderless = QCheckBox("無邊框")
        self.borderless.toggled.connect(self.set_borderless)
        top.addWidget(self.borderless)
        self.fullscreen = QCheckBox("全螢幕 F11")
        self.fullscreen.toggled.connect(self.set_fullscreen)
        top.addWidget(self.fullscreen)
        top.addWidget(button("關閉", self.close))
        root.addLayout(top)
        presets = QHBoxLayout()
        presets.addWidget(QLabel("Preset"))
        self.presets = QComboBox()
        self.presets.setMinimumWidth(220)
        presets.addWidget(self.presets)
        presets.addWidget(button("載入", self.load_selected))
        presets.addWidget(button("另存新名稱", self.save_as))
        presets.addWidget(button("更新選定項目", self.update_selected))
        presets.addStretch()
        presets.addWidget(QLabel("← / → 跳轉"))
        self.seek_step = QDoubleSpinBox()
        self.seek_step.setDecimals(3)
        self.seek_step.setRange(0.001, 86400)
        self.seek_step.setSuffix(" 秒")
        try:
            step = float(self.preferences.value("seek_seconds", 5))
        except (ValueError, TypeError):
            step = 5
        self.seek_step.setValue(step)
        self.seek_step.valueChanged.connect(self.save_seek_step)
        presets.addWidget(self.seek_step)
        self.count_label = QLabel()
        presets.addWidget(self.count_label)
        root.addLayout(presets)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.viewport = scroll.viewport()
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        scroll.setWidget(self.grid_widget)
        root.addWidget(scroll, 1)
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#161b23; color:#e3e9f1; font-family:'Microsoft JhengHei UI'; font-size:12px; }
            QFrame#videoCell { background:#202833; border:1px solid #354252; border-radius:5px; }
            QFrame#controlPanel { background:#202833; border:1px solid #435367; }
            QPushButton, QComboBox, QToolButton { background:#2b3848; border:1px solid #435367; border-radius:3px; padding:4px; }
            QPushButton:hover, QToolButton:hover { background:#3b5367; }
            QPushButton:disabled { color:#677480; background:#222a34; }
            QSlider::groove:horizontal { background:#3a495b; height:4px; }
            QSlider::handle:horizontal { background:#86d8cd; width:10px; margin:-4px 0; border-radius:4px; }
            QScrollArea { border:0; }
        """)
        QShortcut(QKeySequence("F11"), self, activated=lambda: self.fullscreen.toggle())
        QShortcut(QKeySequence("Escape"), self, activated=self.escape_view)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_as)
        self.refresh_presets()
        if restore and self.store._path("last").exists():
            try:
                self.restore(self.store.read("last"))
                self.presets.setCurrentIndex(self.presets.findData("last"))
                self.notify("已恢復上一次；各格暫停，按 ▶ 開始播放。")
            except (ValueError, OSError, KeyError) as error:
                self.notify(f"上一次無法載入，原檔保留：{error}")
                self._restore_failed = True
        if not self.cells:
            for _ in range(6):
                self.add_cell()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_cells)
        self._refresh_timer.start(2500)
        # One bounded timer also handles native VLC surfaces that do not send Qt enter events.
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self.update_overlays)
        self._hover_timer.start(60)
        QApplication.instance().installEventFilter(self)

    def save_seek_step(self, value):
        self.preferences.setValue("seek_seconds", value)
        self.preferences.sync()

    def eventFilter(self, watched, event):
        if self._closing or not isinstance(watched, QWidget):
            return False
        belongs = watched is self or self.isAncestorOf(watched)
        if not belongs or QApplication.activeModalWidget():
            return False
        if event.type() in (QEvent.MouseMove, QEvent.Enter):
            self.update_overlays()
        if event.type() not in (QEvent.KeyPress, QEvent.ShortcutOverride):
            return False
        if event.key() not in (Qt.Key_Left, Qt.Key_Right) or event.modifiers() != Qt.NoModifier:
            return False
        focus = QApplication.focusWidget()
        while focus is not None and focus is not self:
            if isinstance(focus, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox)):
                return False
            focus = focus.parentWidget()
        event.accept()
        if event.type() == QEvent.KeyPress:
            self.seek_active_cell(-1 if event.key() == Qt.Key_Left else 1)
        return True

    def seek_active_cell(self, direction):
        cell = self.last_hovered_cell if self.last_hovered_cell in self.cells else (self.cells[0] if self.cells else None)
        if cell and cell.block and cell.block.is_video_initialized:
            cell.block.user_seek(cell.block.time + round(direction * self.seek_step.value() * 1000))
            cell.update_markers()

    def update_overlays(self):
        for cell in self.cells:
            cell.update_overlay()

    def notify(self, message):
        self.statusBar().showMessage(message, 15000)

    def refresh_cells(self):
        for cell in self.cells:
            cell.refresh()

    def add_cell(self, checked=False, state=None):
        if len(self.cells) >= 12:
            self.notify("最多 12 格")
            return
        self.cells.append(VideoCell(self, state or CellState()))
        self.relayout()

    def remove_cell(self, cell):
        if len(self.cells) <= 1:
            return
        if self.focused_cell is cell:
            self.focused_cell = None
        cell.dispose()
        self.grid.removeWidget(cell)
        self.cells.remove(cell)
        cell.deleteLater()
        self.relayout()

    def relayout(self, *_):
        if not hasattr(self, "grid"):
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for row in range(self.grid.rowCount()):
            self.grid.setRowStretch(row, 0)
        for col in range(self.grid.columnCount()):
            self.grid.setColumnStretch(col, 0)
        if self.focused_cell in self.cells:
            for cell in self.cells:
                cell.setVisible(cell is self.focused_cell)
                cell.focus_button.setText('↩' if cell is self.focused_cell else '⛶')
            self.grid.addWidget(self.focused_cell,0,0)
            self.grid.setRowStretch(0,1)
            self.grid.setColumnStretch(0,1)
            return
        for cell, area in zip(self.cells, placement([c.state for c in self.cells], int(self.columns.currentText()))):
            cell.show()
            cell.focus_button.setText('⛶')
            self.grid.addWidget(cell, *area)
            for row in range(area[0], area[0]+area[2]):
                self.grid.setRowStretch(row, 1)
            for col in range(area[1], area[1]+area[3]):
                self.grid.setColumnStretch(col, 1)
            cell.refresh()
        self.add.setEnabled(len(self.cells) < 12)
        self.count_label.setText(f"{len(self.cells)} / 12 格  ·  拖入影片即可播放")

    def focus_cell(self, cell):
        self.focused_cell = None if self.focused_cell is cell else cell
        self.relayout()

    def escape_view(self):
        if self.focused_cell:
            self.focused_cell = None
            self.relayout()
        else:
            self.fullscreen.setChecked(False)

    def drop_files(self, start, paths):
        paths = [Path(p).resolve() for p in paths]
        if any(not p.exists() or not (p.is_file() or p.is_dir()) for p in paths):
            self.notify("請拖入存在的本機影片或資料夾。")
            return
        available = len(self.cells) - start
        for cell, path in zip(self.cells[start:], paths):
            request = object()
            cell.drop_request = request
            if path.is_dir():
                job = FolderScan(cell, request, path)
                job.signals.finished.connect(self.folder_scan_finished)
                self.folder_jobs[request] = job
                self.notify(f"正在找出資料夾影片：{path.name}")
                self.folder_pool.start(job)
            else:
                try:
                    playlist = folder_videos(path)
                except OSError as error:
                    self.notify(f"無法讀取來源資料夾：{error}")
                    continue
                self.load_source(cell, path, playlist, None)
        if len(paths) > available:
            self.notify(f"已接受 {available} 個來源；另 {len(paths)-available} 個超出格數，未載入。")

    def load_source(self, cell, path, playlist, source_folder):
        cell.state.playlist = [str(p) for p in playlist]
        cell.state.source_folder = str(source_folder) if source_folder else None
        cell.load(Video(uri=path, is_muted=cell.mute.isChecked(), volume=cell.volume.value()/100,
                        aspect_mode=cell.display_mode.currentData()))

    def folder_scan_finished(self, cell, request, paths, error):
        job = self.folder_jobs.pop(request, None)
        if self._closing or cell not in self.cells or cell.drop_request is not request:
            return
        if error:
            self.notify(f"讀取資料夾失敗，原影片保留：{error}")
        elif not paths:
            self.notify("資料夾及子資料夾沒有影片，原影片保留。")
        else:
            self.load_source(cell, paths[0], paths, job.directory)
            self.notify(f"已載入資料夾清單，共 {len(paths)} 部影片；前後切換可首尾循環。")

    def frame_finished(self, cell, request, result, error):
        job=self.frame_jobs.pop(request,None)
        if self._closing or cell not in self.cells or cell.block is not (job.block if job else None):
            return
        cell.frame_busy=False
        cell.refresh()
        if cell.block.frame_request is not request:
            return
        if error or result is None:
            cell.block.frame_preview_active=cell.block.video_driver.exact_frame.isVisible()
            self.notify('無法逐格解碼：'+error)
            return
        seconds,width,height,stride,data,rotation=result
        image=QImage(data,width,height,stride,QImage.Format_RGB888).copy()
        if rotation:
            image=image.transformed(QTransform().rotate(-rotation))
        block=cell.block
        block.frame_seconds=seconds
        target=max(0,round(seconds*1000))
        block.video_driver.set_time(target)
        block.time=target
        v=cell.state.video
        if v.loop_start is not None and v.loop_end is not None:
            block.loop_suspended=not v.loop_start<=target<=v.loop_end
        block.video_driver.show_exact_frame(image)
        cell.update_markers()
        self.notify(f'影格時間 {clock(target)}.{target%1000:03}；保持暫停')

    def apply_global_mute(self, muted):
        for cell in self.cells:
            if cell.block:
                cell.block.global_muted = muted
                cell.block.set_muted(cell.state.video.is_muted)

    def set_borderless(self, enabled):
        full = self.isFullScreen()
        geometry = self.geometry()
        self.setWindowFlag(Qt.FramelessWindowHint, enabled)
        if full:
            self.showFullScreen()
        else:
            self.showNormal()
            self.setGeometry(geometry)

    def set_fullscreen(self, enabled):
        if enabled:
            self._normal_geometry = self.geometry()
            self.showFullScreen()
        else:
            self.showNormal()
            self.setGeometry(self._normal_geometry)

    def snapshot(self):
        rectangle = self._normal_geometry if self.isFullScreen() else self.geometry()
        return WorkspaceState(cells=[cell.state.model_copy(deep=True) for cell in self.cells],
                              columns=int(self.columns.currentText()), geometry=[rectangle.x(), rectangle.y(), rectangle.width(), rectangle.height()],
                              borderless=self.borderless.isChecked(), fullscreen=self.fullscreen.isChecked(), muted=self.global_mute.isChecked())

    def restore(self, state):
        # Validate fully before removing any live media.
        state = WorkspaceState.model_validate(state.model_dump())
        self.focused_cell = None
        for cell in self.cells:
            cell.dispose()
            self.grid.removeWidget(cell)
            cell.deleteLater()
        self.cells.clear()
        # A full preset replaces every media surface. Let the old VLC processes
        # exit before allocating players, avoiding reuse of a terminating instance.
        self.driver.cleanup()
        self.columns.setCurrentText(str(state.columns))
        self.global_mute.setChecked(state.muted)
        for entry in state.cells:
            self.add_cell(state=entry.model_copy(deep=True))
        self.fullscreen.setChecked(False)
        self.borderless.setChecked(state.borderless)
        screen = QApplication.primaryScreen().availableGeometry()
        x, y, width, height = state.geometry
        width, height = max(700, min(width, screen.width())), max(480, min(height, screen.height()))
        self.setGeometry(max(screen.x(), min(x, screen.right()-width)), max(screen.y(), min(y, screen.bottom()-height)), width, height)
        self.fullscreen.setChecked(state.fullscreen)

    def refresh_presets(self, select=None):
        select = select or self.presets.currentData()
        self.presets.clear()
        for key, name in self.store.list():
            self.presets.addItem(name, key)
        index = self.presets.findData(select)
        if index >= 0:
            self.presets.setCurrentIndex(index)

    def save_as(self):
        name, accepted = QInputDialog.getText(self, "另存 preset", "名稱（「上一次」保留供自動保存）")
        if not accepted:
            return
        if any(n == name.strip() for _, n in self.store.list()):
            self.notify("名稱已存在，請選擇「更新選定項目」。")
            return
        try:
            key = self.store.save(name, self.snapshot())
            self.refresh_presets(key)
            self.notify("已另存 preset")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "保存失敗", str(error))

    def update_selected(self):
        key = self.presets.currentData()
        if not key or key == "last":
            self.notify("請選擇自訂 preset；「上一次」於關閉時自動保存。")
            return
        if QMessageBox.question(self, "更新 preset", f"以目前狀態覆蓋「{self.presets.currentText()}」？") != QMessageBox.Yes:
            return
        try:
            self.store.save(self.presets.currentText(), self.snapshot(), key)
            self.notify("已更新選定 preset")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "保存失敗", str(error))

    def load_selected(self):
        key = self.presets.currentData()
        if not key:
            return
        try:
            self.restore(self.store.read(key))
            self.notify("已載入；各格暫停。")
        except (ValueError, OSError, KeyError) as error:
            QMessageBox.warning(self, "載入失敗（原狀保留）", str(error))

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        try:
            # Keep a corrupt last snapshot recoverable rather than replacing it silently.
            if getattr(self, "_restore_failed", False):
                original = self.store._path("last")
                if original.exists():
                    from uuid import uuid4
                    original.rename(original.with_suffix(f".unreadable-{uuid4().hex}.json.bak"))
            self.store.save("上一次", self.snapshot(), "last")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "無法保存上一次", f"{error}\n程式保持開啟，請確認資料夾可寫入後再關閉。")
            event.ignore()
            return
        self._closing = True
        QApplication.instance().removeEventFilter(self)
        self._refresh_timer.stop()
        self._hover_timer.stop()
        for cell in self.cells:
            cell.dispose()
        self.driver.cleanup()
        event.accept()
