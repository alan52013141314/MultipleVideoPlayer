import sys
import os
from pathlib import Path

from PyQt5.QtCore import QStandardPaths

from gridplayer.params import env

PORTABLE_APP_DIR = "portable_data"


def is_portable() -> bool:
    if not (env.IS_WINDOWS and env.IS_PYINSTALLER):
        return False

    portable_data_dir = Path(sys.executable).parent / PORTABLE_APP_DIR

    return portable_data_dir.is_dir()


def get_app_data_dir() -> Path:
    if os.environ.get("GRIDPLAYER_DATA_DIR"):
        directory = Path(os.environ["GRIDPLAYER_DATA_DIR"])
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    if is_portable():
        return Path(sys.executable).parent / PORTABLE_APP_DIR

    app_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))

    if not app_dir.is_dir():
        app_dir.mkdir(parents=True)

    return app_dir
