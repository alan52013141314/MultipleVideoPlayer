from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QToolTip


class ClickSlider(QSlider):
    """Absolute click-to-position while preserving handle dragging and keys."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._absolute_drag = False
        self._drag_offset = 0
        self.value_text = None
        self.setMouseTracking(True)

    def _position_value(self, position):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        if self.orientation() == Qt.Horizontal:
            pixel = position.x() - groove.x() - handle.width() // 2
            length = groove.width() - handle.width()
        else:
            pixel = position.y() - groove.y() - handle.height() // 2
            length = groove.height() - handle.height()
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), pixel,
                                             max(1, length), option.upsideDown)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        coordinate = event.pos().x() if self.orientation() == Qt.Horizontal else event.pos().y()
        center = handle.center().x() if self.orientation() == Qt.Horizontal else handle.center().y()
        self._drag_offset = coordinate - center if handle.contains(event.pos()) else 0
        self._absolute_drag = True
        self.setSliderDown(True)
        self.setValue(self._drag_value(event.pos()))
        event.accept()

    def _drag_value(self, position):
        position = type(position)(position)
        if self.orientation() == Qt.Horizontal:
            position.setX(position.x() - self._drag_offset)
        else:
            position.setY(position.y() - self._drag_offset)
        return self._position_value(position)

    def mouseMoveEvent(self, event):
        value = self._drag_value(event.pos()) if self._absolute_drag else self._position_value(event.pos())
        if self.value_text is not None:
            QToolTip.showText(event.globalPos(), self.value_text(value), self)
        if not self._absolute_drag:
            return super().mouseMoveEvent(event)
        self.setValue(value)
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self._absolute_drag or event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)
        self.setValue(self._drag_value(event.pos()))
        self._absolute_drag = False
        self.setSliderDown(False)  # exactly one commit via sliderReleased
        event.accept()

    def leaveEvent(self, event):
        if not self._absolute_drag:
            QToolTip.hideText()
        super().leaveEvent(event)
