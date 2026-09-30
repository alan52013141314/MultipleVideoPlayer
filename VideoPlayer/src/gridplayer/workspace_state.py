"""Portable workspace snapshots; video payloads use the upstream Video model."""
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from gridplayer.models.video import Video
from gridplayer.params.extensions import SUPPORTED_VIDEO_EXT


class CellState(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    rows: int = Field(default=1, ge=1, le=2)
    cols: int = Field(default=1, ge=1, le=2)
    video: Video | None = None
    playlist: list[str] = Field(default_factory=list)
    source_folder: str | None = None


class WorkspaceState(BaseModel):
    version: Literal[1] = 1
    cells: list[CellState] = Field(min_length=1, max_length=12)
    columns: int = Field(default=3, ge=2, le=4)
    geometry: list[int] = Field(default_factory=lambda: [80, 80, 1280, 800], min_length=4, max_length=4)
    borderless: bool = False
    fullscreen: bool = False
    muted: bool = False

    @model_validator(mode="after")
    def unique_cells(self):
        if len({c.id for c in self.cells}) != len(self.cells):
            raise ValueError("格子識別重複")
        return self


def placement(cells, columns):
    """Stable row-major packing, preserving all cells when a span grows."""
    occupied = set()
    result = []
    for cell in cells:
        for row in range(24):
            for col in range(columns - cell.cols + 1):
                area = {(r, c) for r in range(row, row + cell.rows)
                        for c in range(col, col + cell.cols)}
                if not occupied & area:
                    occupied |= area
                    result.append((row, col, cell.rows, cell.cols))
                    break
            else:
                continue
            break
        else:
            raise ValueError("布局無法容納")
    return result


def folder_videos(path):
    path = Path(path)
    return sorted((p for p in path.parent.iterdir()
                   if p.is_file() and p.suffix[1:].lower() in SUPPORTED_VIDEO_EXT), key=lambda p: natural_key(p.name))


def natural_key(name):
    # Tagged parts compare safely even when a path component begins with digits.
    return [(1, int(s)) if s.isdigit() else (0, s.casefold()) for s in re.split(r"(\d+)", name)]


def scan_folder(directory):
    """Recursive playlist; do not follow directory links or junctions."""
    root = Path(directory).resolve()
    files = []
    def failed(error):
        raise error
    for current, dirs, names in os.walk(root, followlinks=False, onerror=failed):
        dirs[:] = [d for d in dirs if not (Path(current)/d).is_symlink()
                   and not (Path(current)/d).is_junction()]
        files.extend(Path(current)/name for name in names
                     if Path(name).suffix[1:].lower() in SUPPORTED_VIDEO_EXT
                     and (Path(current)/name).is_file())
    return sorted(files, key=lambda p: (natural_key(p.relative_to(root).as_posix()), p.as_posix()))


def adjacent_video(path, direction, playlist=None):
    files = [Path(p) for p in playlist] if playlist else folder_videos(path)
    if not files:
        return None
    try:
        index = (files.index(Path(path)) + direction) % len(files)
    except ValueError:
        return None
    return files[index]


class PresetStore:
    """One atomic document per snapshot; user names are never used as paths."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        if key != "last" and not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("無效 preset 識別")
        return self.directory / f"{key}.json"

    def list(self):
        result = []
        for path in self.directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._path(path.stem)
                result.append((path.stem, str(data["name"])))
            except (ValueError, KeyError, OSError):
                continue
        return sorted(result, key=lambda item: (item[0] != "last", item[1].casefold()))

    def read(self, key):
        data = json.loads(self._path(key).read_text(encoding="utf-8"))
        return WorkspaceState.model_validate(data["state"])

    def save(self, name, state, key=None):
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("名稱需為 1–100 個字元")
        if (name == "上一次") != (key == "last"):
            raise ValueError("「上一次」保留供關閉自動保存")
        key = key or uuid4().hex
        destination = self._path(key)
        state = WorkspaceState.model_validate(state.model_dump())
        content = json.dumps({"name": name, "state": state.model_dump(mode="json")}, ensure_ascii=False, indent=2)
        fd, temporary = tempfile.mkstemp(prefix=".saving-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if Path(temporary).exists():
                Path(temporary).unlink()
        return key
