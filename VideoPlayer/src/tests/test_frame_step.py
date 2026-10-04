from fractions import Fraction
import av
import pytest
from gridplayer.utils.frame_step import adjacent_frame


@pytest.fixture
def vfr_clip(tmp_path):
    path=tmp_path/'vfr.mkv'
    with av.open(str(path),'w') as output:
        stream=output.add_stream('ffv1',rate=25)
        stream.width=64
        stream.height=48
        stream.pix_fmt='yuv420p'
        stream.time_base=Fraction(1,1000)
        for i,pts in enumerate([0,40,120,160,360,400]):
            frame=av.VideoFrame(64,48,'yuv420p')
            for n,plane in enumerate(frame.planes):
                plane.update(bytes([30+i*25 if n==0 else 128])*plane.buffer_size)
            frame.pts=pts
            frame.time_base=Fraction(1,1000)
            for packet in stream.encode(frame): output.mux(packet)
        for packet in stream.encode(): output.mux(packet)
    return path


def test_variable_timestamps_and_exact_pixels_both_directions(vfr_clip):
    with av.open(str(vfr_clip)) as source:
        expected=[]
        for f in source.decode(video=0):
            rgb=f.reformat(format='rgb24')
            expected.append((float(f.pts*f.time_base),bytes(rgb.planes[0])))
    assert len({round(expected[i+1][0]-expected[i][0],3) for i in range(5)})>1
    for i in range(1,len(expected)-1):
        for direction in (-1,1):
            frame=adjacent_frame(vfr_clip,expected[i][0],direction)
            assert frame[0]==pytest.approx(expected[i+direction][0])
            assert frame[4]==expected[i+direction][1]
    assert adjacent_frame(vfr_clip,0,-1)[0]==0
    assert adjacent_frame(vfr_clip,.14,0)[0]==pytest.approx(.12)
    assert adjacent_frame(vfr_clip,expected[-1][0],1)[0]==expected[-1][0]
    assert adjacent_frame(vfr_clip,0,1,lambda:True) is None
