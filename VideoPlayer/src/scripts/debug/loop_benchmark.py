"""Decode-output timing around accurate AB seeks, using bundled libVLC 3."""
import argparse
import ctypes
import json
import queue
import statistics
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'VideoPlayer/src'))

def measure(cache, loops=5):
    from workspace_launcher import prepare_environment
    prepare_environment()
    from gridplayer.main.init_app_env import init_app_env
    init_app_env()
    from gridplayer.vlc_player.libvlc import vlc
    opts = ['--quiet', '--no-video-title-show', '--avcodec-hw=none']
    if cache is not None:
        opts.append(f'--file-caching={cache}')
    instance = vlc.Instance(*opts)
    player = instance.media_player_new()
    media = instance.media_new(str(ROOT/'verification/media/clip1.mp4'))
    player.set_media(media)
    player.audio_set_mute(True)
    buffer = ctypes.create_string_buffer(320*180*4)
    shown = []
    hashes = []
    events = queue.SimpleQueue()
    @vlc.CallbackDecorators.VideoLockCb
    def lock(opaque, planes):
        planes[0] = ctypes.addressof(buffer)
    @vlc.CallbackDecorators.VideoDisplayCb
    def display(opaque, picture):
        checksum=zlib.crc32(buffer)
        # libVLC can present the same frame again while a seek is buffering.
        if not hashes or checksum != hashes[-1]:
            hashes.append(checksum)
            shown.append(time.perf_counter())
    def changed(event):
        events.put(int(event.u.new_time))
    player.video_set_callbacks(lock, None, display, None)
    player.video_set_format('RV32', 320, 180, 320*4)
    player.event_manager().event_attach(vlc.EventType.MediaPlayerTimeChanged, changed)
    player.play()
    a,b = 1200,2200
    turns=[]
    deadline=time.monotonic()+25
    pending=False
    try:
        while len(turns)<loops and time.monotonic()<deadline:
            try:
                position=events.get(timeout=.05)
            except queue.Empty:
                continue
            if position < b:
                pending=False
            if position>b and not pending:
                pending=True
                turns.append({'at':time.perf_counter(),'overshoot_ms':position-b})
                player.set_time(a)
        time.sleep(.6)
    finally:
        player.stop()
        player.release()
        media.release()
        instance.release()
    assert len(turns)==loops, 'loop benchmark did not complete'
    gaps=[]
    first_frames=[]
    for turn in turns:
        # Observe actual display callback pacing around each seek, not UI time events.
        around=[(right-left)*1000 for left,right in zip(shown,shown[1:])
                if turn['at']-.15<=left<=turn['at']+.6]
        gaps.append(round(max(around),1))
        first_frames.append(round((next(t for t in shown if t>turn['at'])-turn['at'])*1000,1))
    return {'cache_ms':cache,'loops':loops,'max_frame_gap_ms_per_loop':gaps,
            'median_max_gap_ms':round(statistics.median(gaps),1),
            'first_frame_after_seek_ms':first_frames,
            'overshoot_ms':[t['overshoot_ms'] for t in turns]}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=int)
    parser.add_argument('--output',default='loop-baseline.json')
    args=parser.parse_args()
    result=measure(args.cache)
    (ROOT/'verification'/args.output).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)
