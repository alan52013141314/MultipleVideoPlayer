# Windows onedir packaging, following upstream's PyInstaller + external libVLC layout.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
a = Analysis([str(root / 'workspace_launcher.py')], pathex=[str(root)],
    binaries=[], datas=collect_data_files('streamlink'), hiddenimports=[],
    excludes=['tkinter', 'PyQt5.QtWebEngine', 'PyQt5.QtQml', 'PyQt5.QtQuick'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='GridPlayerWorkspace',
    console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='GridPlayerWorkspace')
