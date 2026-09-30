"""Verify the project launcher selects the same release shipped in the ZIP."""
import hashlib
import json
import sys
import types
import zipfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

PLAYER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYER / "src"))
from gridplayer.workspace_version import VERSION


def digest(data):
    return hashlib.sha256(data).hexdigest()


def code_names(code):
    yield code.co_name
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from code_names(value)


def main():
    release = (PLAYER / "current-release.txt").read_text().strip()
    installed = PLAYER / "dist" / release
    executable = installed / "GridPlayerWorkspace.exe"
    executable_hash = digest(executable.read_bytes())
    assert release == "GridPlayerWorkspace-" + executable_hash[:12]
    archive_path = PLAYER / f"GridPlayerWorkspace-{VERSION}-win64.zip"
    archive = CArchiveReader(str(executable))
    modules = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith(".pyz")))
    assert VERSION in modules.extract("gridplayer.workspace_version").co_consts
    window = modules.extract("gridplayer.workspace_window")
    assert "gridplayer.workspace_version" in window.co_names
    assert "update_volume_button" in set(code_names(window))
    assert "mousePressEvent" in set(code_names(modules.extract("gridplayer.widgets.click_slider")))
    checked = 0
    with zipfile.ZipFile(archive_path) as package:
        for item in package.infolist():
            if item.is_dir():
                continue
            relative = Path(item.filename).relative_to("GridPlayerWorkspace")
            assert "portable_data" not in relative.parts, "User data must not be bundled."
            data = package.read(item)
            assert digest(data) == digest((installed / relative).read_bytes()), str(relative)
            assert digest(data) == digest((PLAYER / "build/release-stage/GridPlayerWorkspace" / relative).read_bytes()), str(relative)
            checked += 1
    archive_hash = digest(archive_path.read_bytes())
    assert archive_hash in (PLAYER / "SHA256SUMS.txt").read_text()
    result = {
        "passed": True,
        "version": VERSION,
        "current_release": release,
        "installed_copy_pending": False,
        "zip_stage_installed_files_identical": checked,
        "compiled_volume_popup_and_click_slider": True,
        "compiled_title_version": VERSION,
        "zip_sha256": archive_hash,
        "desktop_visual_check": "Not performed: computer-use authorization remains unavailable.",
    }
    (PLAYER.parent / "verification/release-pr005-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
