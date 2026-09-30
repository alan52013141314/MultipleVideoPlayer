from pathlib import Path

import pytest

from gridplayer.models.video import Video
from gridplayer.workspace_state import CellState, WorkspaceState, PresetStore, placement, adjacent_video, scan_folder


def test_spans_never_overlap_and_preserve_order():
    cells = [CellState(rows=2 if i % 3 == 0 else 1, cols=2 if i % 2 == 0 else 1) for i in range(12)]
    for columns in (2, 3, 4):
        occupied = set()
        areas = placement(cells, columns)
        assert len(areas) == 12
        for row, col, rows, cols in areas:
            area = {(r,c) for r in range(row,row+rows) for c in range(col,col+cols)}
            assert not occupied & area
            assert col + cols <= columns
            occupied |= area


def test_file_source_natural_order_wrap_and_no_recursion(tmp_path):
    for name in ("clip10.mp4", "clip2.mp4", "clip1.mp4", "notes.txt"):
        (tmp_path / name).touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "clip3.mp4").touch()
    assert adjacent_video(tmp_path / "clip1.mp4", -1).name == "clip10.mp4"
    assert adjacent_video(tmp_path / "clip1.mp4", 1).name == "clip2.mp4"
    assert adjacent_video(tmp_path / "clip2.mp4", 1).name == "clip10.mp4"
    assert adjacent_video(tmp_path / "clip10.mp4", 1).name == "clip1.mp4"


def test_recursive_playlist_sort_wrap_and_restore(tmp_path):
    for name in ('clip10.mp4', 'clip2.mp4', 'clip1.mp4', 'part2/clip10.MOV',
                 'part2/clip2.avi', 'part10/clip1.mkv', 'notes.txt'):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.touch()
    videos = scan_folder(tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in videos] == [
        'clip1.mp4', 'clip2.mp4', 'clip10.mp4', 'part2/clip2.avi',
        'part2/clip10.MOV', 'part10/clip1.mkv']
    assert adjacent_video(videos[-1], 1, videos) == videos[0]
    assert adjacent_video(videos[0], -1, videos) == videos[-1]
    assert adjacent_video(videos[0], 1, [videos[0]]) == videos[0]
    store = PresetStore(tmp_path / 'presets')
    state = WorkspaceState(cells=[CellState(video=Video(uri=videos[2]),
                               playlist=[str(p) for p in videos], source_folder=str(tmp_path))])
    key = store.save('recursive', state)
    assert store.read(key).model_dump(mode="json") == state.model_dump(mode="json")
    empty = tmp_path / 'empty'
    empty.mkdir()
    assert scan_folder(empty) == []


def test_snapshots_last_and_custom_are_independent(tmp_path):
    store = PresetStore(tmp_path)
    state = WorkspaceState(cells=[CellState(video=Video(uri="C:/missing.mp4", loop_start=1000, loop_end=2000))])
    a = store.save("A", state)
    state.cells[0].video.loop_start = 1500
    b = store.save("B", state)
    store.save("上一次", state, "last")
    state.cells[0].video.loop_start = 1800
    store.save("上一次", state, "last")
    assert store.read(a).cells[0].video.loop_start == 1000
    assert store.read(b).cells[0].video.loop_start == 1500
    assert store.read("last").cells[0].video.loop_start == 1800
    assert len(list(tmp_path.glob("*.json"))) == 3


def test_failed_replace_keeps_last_valid_data(tmp_path, monkeypatch):
    store = PresetStore(tmp_path)
    state = WorkspaceState(cells=[CellState()])
    store.save("上一次", state, "last")
    original = (tmp_path / "last.json").read_bytes()
    def fail(*args):
        raise OSError("disk error")
    monkeypatch.setattr("gridplayer.workspace_state.os.replace", fail)
    with pytest.raises(OSError):
        store.save("上一次", state, "last")
    assert (tmp_path / "last.json").read_bytes() == original
    assert not list(tmp_path.glob(".saving-*"))


def test_names_cannot_escape_data_directory(tmp_path):
    store = PresetStore(tmp_path)
    state = WorkspaceState(cells=[CellState()])
    key = store.save("../anything:*?", state)
    assert store.read(key) == state
    with pytest.raises(ValueError):
        store.read("../secret")
    with pytest.raises(ValueError):
        store.save("上一次", state)
    with pytest.raises(ValueError):
        WorkspaceState(cells=[CellState() for _ in range(13)])
