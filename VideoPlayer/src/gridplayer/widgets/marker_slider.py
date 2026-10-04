"""AB handles have separate lanes from the playback handle."""
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import QStyle, QStyleOptionSlider, QToolTip
from gridplayer.widgets.click_slider import ClickSlider


class MarkerSlider(ClickSlider):
    marker_moved = pyqtSignal(str, int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.a = self.b = None
        self.suspended = False
        self.marker_drag = None
        self.setMinimumHeight(30)

    def marker_x(self, value):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        return groove.x()+handle.width()//2+QStyle.sliderPositionFromValue(
            self.minimum(), self.maximum(), value, max(1, groove.width()-handle.width()), option.upsideDown)

    def set_markers(self, a, b, suspended):
        self.a, self.b, self.suspended = a, b, suspended
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = QColor('#e0b35f' if self.suspended else '#86d8cd')
        if self.a is not None and self.b is not None:
            shade = QColor(color)
            shade.setAlpha(75)
            painter.fillRect(QRect(self.marker_x(self.a), self.height()//2-2,
                                  max(1,self.marker_x(self.b)-self.marker_x(self.a)),4), shade)
        painter.setPen(color)
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        for name, value in (('A',self.a),('B',self.b)):
            if value is None:
                continue
            x = self.marker_x(value)
            top = 0 if name == 'A' else self.height()-11
            painter.drawText(QRect(max(0,min(self.width()-12,x-6)),top,12,11),Qt.AlignCenter,name)
            painter.drawLine(x,top+9 if name=='A' else top,x,self.height()//2)

    def marker_at(self, position):
        name = 'A' if position.y() < self.height()//2-4 else 'B' if position.y() > self.height()//2+4 else None
        value = self.a if name=='A' else self.b
        return name if name and value is not None and abs(position.x()-self.marker_x(value))<=8 else None

    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.marker_drag=self.marker_at(event.pos())
            if self.marker_drag:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.marker_drag:
            value=self._position_value(event.pos())
            self.marker_moved.emit(self.marker_drag,value)
            QToolTip.showText(event.globalPos(),f'{self.marker_drag} {self.value_text(value)}',self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.marker_drag and event.button()==Qt.LeftButton:
            self.marker_moved.emit(self.marker_drag,self._position_value(event.pos()))
            self.marker_drag=None
            event.accept()
            return
        super().mouseReleaseEvent(event)
