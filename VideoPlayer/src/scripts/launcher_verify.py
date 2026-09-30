"""Exercise the CMD launcher with process discovery and final launch intercepted."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PLAYER = Path(__file__).resolve().parents[2]


def main():
    release = (PLAYER / "current-release.txt").read_text().strip()
    assert (PLAYER / "dist" / release / "GridPlayerWorkspace.exe").is_file()
    source_bytes = (PLAYER / "Start-Player.cmd").read_bytes()
    source = source_bytes.decode("utf-8")
    assert 'powershell' not in source.lower()
    start = 'start "" /D "%~dp0dist\\%playerRelease%" "%playerExe%" %*'
    assert source.count(start) == 1
    with tempfile.TemporaryDirectory(prefix="Player launcher test ") as temp:
        fixture = Path(temp)
        executable = fixture / "dist" / release / "GridPlayerWorkspace.exe"
        executable.parent.mkdir(parents=True)
        executable.touch()
        (fixture / "current-release.txt").write_text(release)
        # CMD still executes all selection, guard and argument forwarding logic.
        # Preserve original line endings: normal text I/O previously hid broken LF-only CMD files.
        (fixture / "Start-Player.cmd").write_bytes(source_bytes.replace(start.encode(), b'call "%~dp0record.cmd" /D "%~dp0dist\\%playerRelease%" "%playerExe%" %*'))
        (fixture / "tasklist.cmd").write_text('@echo off\nexit /b 0\n')
        (fixture / "record.cmd").write_text(f'@echo off\n"{sys.executable}" "%~dp0record.py" %*\n')
        (fixture / "record.py").write_text('import sys, os, json\nfrom pathlib import Path\nPath("launch.json").write_text(json.dumps({"args":sys.argv[1:],"data":os.environ["GRIDPLAYER_DATA_DIR"]}))\n')

        def run(arguments=""):
            return subprocess.run(f'"{os.environ["COMSPEC"]}" /d /c Start-Player.cmd {arguments}', cwd=fixture, input=b"\r\n", capture_output=True, timeout=20)

        first_run = run()
        assert first_run.returncode == 0, first_run.stderr.decode("utf-8", errors="replace")
        captured = json.loads((fixture / "launch.json").read_text())
        expected = ["/D", str(executable.parent), str(executable)]
        assert captured["args"] == expected
        assert captured["data"] == str(fixture / "dist/GridPlayerWorkspace/portable_data")
        assert run('"C:\\Test Videos\\clip 2.mp4" "C:\\Test Videos"').returncode == 0
        assert json.loads((fixture / "launch.json").read_text())["args"] == expected + [r"C:\Test Videos\clip 2.mp4", r"C:\Test Videos"]
        (fixture / "launch.json").unlink()
        (fixture / "tasklist.cmd").write_text('@echo off\necho GridPlayerWorkspace.exe 1234\n')
        blocked = run()
        assert blocked.returncode == 0
        assert not (fixture / "launch.json").exists(), "An open player must prevent a second launch."
        assert "請先正常關閉" in blocked.stdout.decode("utf-8")
    result = {"passed": True, "current_release": release, "preserves_settings_directory": True,
              "space_in_media_and_install_paths": True, "existing_player_guard": True,
              "requires_powershell": False, "preserves_original_launcher_bytes": True,
              "method": "Windows CMD fixture; process listing and final process launch intercepted."}
    (PLAYER.parent / "verification/launcher-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
