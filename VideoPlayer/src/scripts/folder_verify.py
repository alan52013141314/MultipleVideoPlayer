"""Real VLC regression for recursive folder drops and cyclic per-cell lists."""
import json
import os
import shutil
import sys
import time
from pathlib import Path
from multiprocessing import freeze_support

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'VideoPlayer/src'))


def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    evidence = ROOT / 'verification'
    os.environ['GRIDPLAYER_DATA_DIR'] = str(evidence / 'folder-player-data')
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env
    from gridplayer.params.static import VideoAspect
    from PyQt5.QtCore import Qt, QMimeData, QUrl, QPointF, QPoint
    from PyQt5.QtGui import QDropEvent, QDragEnterEvent
    from PyQt5.QtTest import QTest
    init_app_env()
    app = init_app()
    env.VLC_VERSION, env.VLC_PYTHON_VERSION = init_vlc()
    from gridplayer.workspace_window import WorkspaceWindow
    folder = evidence / 'folder-fixture'
    (folder / 'part2').mkdir(parents=True, exist_ok=True)
    (evidence / 'empty-folder-fixture').mkdir(exist_ok=True)
    for name in ('clip10.mp4', 'clip2.mp4', 'part2/clip1.mp4'):
        shutil.copyfile(evidence / 'media/small-landscape.mp4', folder / name)
    (folder / 'notes.txt').write_text('not a video', encoding='utf8')
    w = WorkspaceWindow(restore=False)
    w.show()
    w.global_mute.setChecked(True)
    result = {'passed': False}
    def wait(check):
        deadline = time.monotonic() + 20
        while not check():
            assert time.monotonic() < deadline, 'folder verification timeout'
            QTest.qWait(40)
    def ready(cell):
        return cell.block is not None and cell.block.is_video_initialized
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(folder)), QUrl.fromLocalFile(str(evidence/'media/clip1.mp4'))])
        enter = QDragEnterEvent(QPoint(20,20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(w.cells[0], enter)
        drop = QDropEvent(QPointF(20,20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        app.sendEvent(w.cells[0], drop)
        assert drop.isAccepted()
        first, second = w.cells[:2]
        wait(lambda: ready(first) and ready(second) and not w.folder_jobs)
        assert Path(first.state.video.uri).name == 'clip2.mp4'
        assert [Path(p).relative_to(folder).as_posix() for p in first.state.playlist] == [
            'clip2.mp4', 'clip10.mp4', 'part2/clip1.mp4']
        other_id = second.block
        first.volume.setValue(27)
        first.display_mode.setCurrentIndex(first.display_mode.findData(VideoAspect.WIDTH))
        for direction, expected in [(1,'clip10.mp4'), (1,'part2/clip1.mp4'), (1,'clip2.mp4'), (-1,'part2/clip1.mp4')]:
            first.switch(direction)
            wait(lambda: ready(first))
            assert Path(first.state.video.uri).relative_to(folder).as_posix() == expected
            assert first.state.video.volume == .27
            assert first.state.video.aspect_mode == VideoAspect.WIDTH
            assert second.block is other_id
        # File drops use the same-layer snapshot, also wrapping both ways.
        original = Path(second.state.video.uri)
        second.switch(-1)
        wait(lambda: ready(second))
        assert Path(second.state.video.uri) == Path(second.state.playlist[-1])
        second.switch(1)
        wait(lambda: ready(second))
        assert Path(second.state.video.uri) == original
        key = w.store.save('folder-list', w.snapshot())
        saved = w.store.read(key)
        w.restore(saved)
        wait(lambda: ready(w.cells[0]) and ready(w.cells[1]))
        assert w.cells[0].state.playlist == saved.cells[0].playlist
        assert w.cells[0].state.source_folder == str(folder)
        assert w.cells[0].volume.value() == 27
        first = w.cells[0]
        kept = first.block
        w.drop_files(0, [str(evidence/'empty-folder-fixture')])
        wait(lambda: not w.folder_jobs)
        assert first.block is kept
        # A later drop must beat a queued older folder scan.
        w.drop_files(0, [str(folder)])
        w.drop_files(0, [str(evidence/'media/small-portrait.mp4')])
        wait(lambda: not w.folder_jobs and ready(first))
        assert Path(first.state.video.uri).name == 'small-portrait.mp4'
        assert first.state.source_folder is None
        result = {'passed': True, 'checks': [
            'mixed folder/file Qt drop; one source per cell',
            'recursive natural order; first clip starts; non-video filtered',
            'forward/backward wrapping for folder and file sources',
            'switch preserves mode/volume; other cell keeps its player',
            'preset restores ordered list, source folder, mode and volume',
            'empty folder keeps original; latest drop wins over older scan']}
    finally:
        w.close()
        QTest.qWait(200)
        (evidence/'folder-verification.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    freeze_support()
    main()
