"""Offscreen widget reproduction: real Qt mouse click and narrow-cell geometry."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'VideoPlayer/src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['GRIDPLAYER_DATA_DIR'] = str(ROOT/'verification/controls-widget-data')

def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    from gridplayer.main.init_app_env import init_app_env
    init_app_env()
    from gridplayer.main.init_app import init_app
    from gridplayer.workspace_window import WorkspaceWindow
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import Qt, QPoint
    app = init_app()
    w = WorkspaceWindow(restore=False)
    w._hover_timer.stop()
    c = w.cells[0]
    result = {}
    for width in (260, 415):
        c.resize(width, 240)
        panel = c.bottom_panel
        panel.resize(width-2, panel.sizeHint().height())
        panel.show()
        app.processEvents()
        c.seekbar.setEnabled(True)
        c.seekbar.setValue(1000)
        released = []
        def committed():
            released.append(c.seekbar.value())
        c.seekbar.sliderReleased.connect(committed)
        QTest.mouseClick(c.seekbar, Qt.LeftButton, pos=QPoint(round(c.seekbar.width()*.75), c.seekbar.height()//2))
        result[str(width)] = {'volume_button_width': c.volume_button.width(),
                             'volume_popup_in_main_layout':panel.layout().indexOf(c.volume_controls)>=0,
                             'panel_width':panel.width(), 'seek_value_after_75pct_click':c.seekbar.value(),
                             'seek_releases':released}
        panel.grab().save(str(ROOT/f'verification/controls-{width}.png'))
        assert abs(c.seekbar.value()-7500)<250
        assert len(released)==1
        assert panel.width()==width-2
        assert panel.layout().indexOf(c.volume_controls)<0
        assert c.volume_button.geometry().right()<panel.width()
        c.seekbar.sliderReleased.disconnect(committed)
    print(json.dumps(result), flush=True)
    (ROOT/'verification/controls-widget-verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    w.close()

if __name__ == '__main__':
    main()
