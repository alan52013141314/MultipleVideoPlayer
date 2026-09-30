import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from gridplayer.widgets.click_slider import ClickSlider


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('fraction', [.25, .75])
def test_groove_click_jumps_and_commits_once(app, fraction):
    slider=ClickSlider(Qt.Horizontal)
    slider.setRange(0,10000)
    slider.resize(400,24)
    slider.show()
    app.processEvents()
    commits=[]
    slider.sliderReleased.connect(lambda: commits.append(slider.value()))
    QTest.mouseClick(slider,Qt.LeftButton,pos=QPoint(round(slider.width()*fraction),12))
    assert abs(slider.value()-fraction*10000)<250
    assert commits==[slider.value()]
    assert not slider.isSliderDown()
    slider.close()


def test_click_then_drag_clamps_and_commits_once(app):
    slider=ClickSlider(Qt.Horizontal)
    slider.setRange(0,10000)
    slider.resize(400,24)
    slider.show()
    app.processEvents()
    commits=[]
    slider.sliderReleased.connect(lambda: commits.append(slider.value()))
    QTest.mousePress(slider,Qt.LeftButton,pos=QPoint(120,12))
    assert slider.isSliderDown()
    QTest.mouseMove(slider,QPoint(390,12))
    QTest.mouseRelease(slider,Qt.LeftButton,pos=QPoint(450,12))
    assert slider.value()==10000
    assert commits==[10000]
    slider.close()
