"""Measure actual workspace AB seek cadence through the live VLC frame driver."""
import json
import os
import sys
import time
from pathlib import Path
from multiprocessing import freeze_support

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'VideoPlayer/src'))

def main():
    from workspace_launcher import prepare_environment
    prepare_environment()
    os.environ['GRIDPLAYER_DATA_DIR']=str(ROOT/'verification/loop-timing-data')
    from gridplayer.main.init_app_env import init_app_env
    from gridplayer.main.init_app import init_app
    from gridplayer.utils.libvlc import init_vlc
    from gridplayer.params import env
    from PyQt5.QtTest import QTest
    init_app_env()
    app=init_app()
    env.VLC_VERSION,env.VLC_PYTHON_VERSION=init_vlc()
    from gridplayer.workspace_window import WorkspaceWindow
    w=WorkspaceWindow(restore=False)
    w.show()
    w.global_mute.setChecked(True)
    def wait(check,seconds=15):
        end=time.monotonic()+seconds
        while not check():
            assert time.monotonic()<end,'timing timeout'
            QTest.qWait(3)
    result={}
    try:
        w.drop_files(0,[str(ROOT/'verification/media/clip1.mp4')])
        c=w.cells[0]
        wait(lambda:c.block.is_video_initialized and c.block.time>500)
        b=c.block
        b.set_loop_start_time(1200)
        b.set_loop_end_time(2200)
        b.seek(1200)
        wait(lambda:1200<=b.time<2200)
        samples=[]
        underlying=b.video_driver.set_time
        def record(position):
            if position==1200:
                samples.append(time.perf_counter())
            return underlying(position)
        b.video_driver.set_time=record
        wait(lambda:len(samples)>=6,20)
        intervals=[round((r-l)*1000,1) for l,r in zip(samples,samples[1:])]
        result={'interval_ms':1000,'observed_loop_intervals_ms':intervals,
                'mean_interval_ms':round(sum(intervals)/len(intervals),1),
                'minimum_interval_ms':min(intervals),
                'note':'Actual seek cadence, not a claim about rendered frame continuity'}
    finally:
        w.close()
        QTest.qWait(100)
    name=sys.argv[1] if len(sys.argv)>1 else 'loop-workspace-baseline.json'
    (ROOT/'verification'/name).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    freeze_support()
    main()
