from types import SimpleNamespace

import pytest
from gridplayer.models.video import Video
from gridplayer.params.static import VideoAspect as A
from gridplayer.utils.pan_geometry import video_rect
from gridplayer.workspace_state import CellState, WorkspaceState, PresetStore
from gridplayer.workspace_window import WorkspaceBlock
from gridplayer.vlc_player.player_base import VlcPlayerBase


def test_late_initialization_callbacks_after_cleanup_do_not_touch_released_vlc():
    released = SimpleNamespace(_media_player=None, _playlist_player=None)
    VlcPlayerBase.cb_parse_changed(released, None)
    VlcPlayerBase.load_video_st2_set_media(released)
    VlcPlayerBase.load_video_st3_extract_media_track(released)
    VlcPlayerBase.load_video_st4_loaded(released)


@pytest.mark.parametrize('target,expected,suspended', [(2500,2500,False), (6000,6000,True),
                                                     (-500,0,True), (15000,9999,True), (2000,2000,False)])
def test_manual_seek_crosses_markers_without_removing_them(target, expected, suspended):
    calls = []
    video = Video(uri='clip.mp4', loop_start=2000, loop_end=4000, is_paused=True)
    block = SimpleNamespace(is_video_initialized=True, video_params=video, loop_suspended=True,
                            video_driver=SimpleNamespace(length=10000, set_time=calls.append))
    WorkspaceBlock.user_seek(block, target)
    assert calls == [expected]
    assert block.loop_suspended is suspended
    assert (video.loop_start, video.loop_end, video.is_paused) == (2000,4000,True)


@pytest.mark.parametrize('mode', [A.NONE,A.FIT,A.WIDTH,A.HEIGHT,A.STRETCH,A.ORIGINAL])
def test_pan_only_reveals_cropped_pixels_and_clamps(mode):
    for source in [(1920,1080),(1080,1920),(100,100)]:
        for requested in [(0,0),(-99999,-99999),(99999,99999)]:
            (x,y,w,h),offset = video_rect(source,(640,480),mode,requested,ratio=2)
            if w > 640:
                assert 640-w <= x <= 0
            else:
                assert x == round((640-w)/2) and offset[0] == 0
            if h > 480:
                assert 480-h <= y <= 0
            else:
                assert y == round((480-h)/2) and offset[1] == 0


def test_suspended_loop_restores_with_position_and_old_presets_default(tmp_path):
    state = WorkspaceState(cells=[CellState(video=Video(uri='clip.mp4',loop_start=2000,loop_end=4000,
                                                      current_position=7000),loop_suspended=True)])
    store=PresetStore(tmp_path)
    store.save('上一次',state,'last')
    restored=store.read('last').cells[0]
    assert restored.loop_suspended and restored.video.current_position==7000
    old=state.model_dump()
    del old['cells'][0]['loop_suspended']
    assert not WorkspaceState.model_validate(old).cells[0].loop_suspended
