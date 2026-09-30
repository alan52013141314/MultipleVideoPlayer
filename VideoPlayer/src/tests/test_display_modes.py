import pytest

from gridplayer.models.video import Video
from gridplayer.params.static import VideoAspect as A
from gridplayer.utils.aspect_calc import calc_crop, calc_resize_scale
from gridplayer.workspace_state import CellState, WorkspaceState, PresetStore


@pytest.mark.parametrize("source,viewport,width_factor,height_factor", [
    ((1920, 1080), (640, 480), 1/3, 4/9),
    ((1080, 1920), (640, 480), 16/27, 1/4),
    ((320, 180), (640, 480), 2, 8/3),
])
def test_fixed_axis_and_native_pixels(source, viewport, width_factor, height_factor):
    assert calc_resize_scale(source, viewport, A.WIDTH, 1) == pytest.approx(width_factor)
    assert calc_resize_scale(source, viewport, A.HEIGHT, 1) == pytest.approx(height_factor)
    assert calc_resize_scale(source, viewport, A.ORIGINAL, 1) == 1
    for mode in (A.WIDTH, A.HEIGHT, A.ORIGINAL, A.NONE):
        assert calc_crop(source, viewport, mode) == (source, source)
    # Keep full input for Fit; only Fill crops, only Stretch alters aspect.
    assert calc_crop(source, viewport, A.FIT) == (source, viewport)
    assert calc_crop(source, viewport, A.STRETCH) == (viewport, viewport)


def test_six_cell_modes_and_volumes_survive_separate_snapshots(tmp_path):
    modes = [A.NONE, A.FIT, A.WIDTH, A.HEIGHT, A.STRETCH, A.ORIGINAL]
    state = WorkspaceState(cells=[CellState(video=Video(uri="C:/missing.mp4", aspect_mode=mode, volume=i/10))
                                  for i, mode in enumerate(modes)])
    store = PresetStore(tmp_path)
    key = store.save("six independent cells", state)
    state.cells[0].video.volume = .91
    state.cells[0].video.aspect_mode = A.ORIGINAL
    store.save("上一次", state, "last")
    restored = store.read(key)
    assert [c.video.aspect_mode for c in restored.cells] == modes
    assert [c.video.volume for c in restored.cells] == [i/10 for i in range(6)]
    assert store.read("last").cells[0].video.volume == .91
    assert store.read("last").cells[1:] == restored.cells[1:]
