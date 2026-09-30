"""Entry point for the local-only GridPlayer v0.5.5 workspace edition."""
import os
import sys
from multiprocessing import freeze_support
from pathlib import Path


def prepare_environment():
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    os.environ.setdefault("GRIDPLAYER_DATA_DIR", str(root / "portable_data"))
    vlc = root / "libVLC"
    if not vlc.exists():
        vlc = root / "upstream-portable" / "GridPlayer" / "libVLC"
    os.environ["PYTHON_VLC_LIB_PATH"] = str(vlc / "libvlc.dll")
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(vlc / "plugins")


def main():
    prepare_environment()
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.main.init_log import init_log
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env

    init_app_env()
    from gridplayer.settings import Settings
    Settings().set("logging/log_limit", True)
    init_log()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from gridplayer.workspace_window import WorkspaceWindow

    window = WorkspaceWindow()
    window.show()
    if sys.argv[1:]:
        window.drop_files(0, sys.argv[1:])
    return app.exec_()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
