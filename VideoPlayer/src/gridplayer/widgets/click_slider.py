from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickSlider(QSlider):
    """Absolute click-to-position while preserving handle dragging and keys."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._absolute_drag = False

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
        if handle.contains(event.pos()):
            return super().mousePressEvent(event)
        self._absolute_drag = True
        self.setSliderDown(True)
        self.setValue(self._position_value(event.pos()))
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._absolute_drag:
            return super().mouseMoveEvent(event)
        self.setValue(self._position_value(event.pos()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self._absolute_drag or event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)
        self.setValue(self._position_value(event.pos()))
        self._absolute_drag = False
        self.setSliderDown(False)  # exactly one commit via sliderReleased
        event.accept()
