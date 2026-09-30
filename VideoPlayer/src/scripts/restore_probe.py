import os
import sys
from pathlib import Path
from multiprocessing import freeze_support

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "VideoPlayer/src"))

def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    os.environ["GRIDPLAYER_DATA_DIR"] = str(ROOT / "verification/probe-data")
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env
    init_app_env()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from PyQt5.QtTest import QTest
    from gridplayer.workspace_state import PresetStore
    from gridplayer.workspace_window import WorkspaceWindow
    store = PresetStore(ROOT / "verification/player-data/presets")
    state = store.read(next(k for k,n in store.list() if n == "測試 A"))
    w = WorkspaceWindow(restore=False)
    w.show()
    w.restore(state)
    for iteration in range(5):
        QTest.qWait(5000)
        print([(c.block.is_video_initialized, c.block.video_status.status_text, c.state.video.is_paused, str(c.state.video.uri)) for c in w.cells], flush=True)
        if iteration == 0:
            for cell in w.cells:
                cell.play_pause()
        if iteration in (1, 2):
            w.restore(state)
    w.close()
    QTest.qWait(300)

if __name__ == '__main__':
    freeze_support()
    main()
