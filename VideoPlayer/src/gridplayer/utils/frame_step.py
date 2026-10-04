"""Decode neighbouring presentation timestamps; never infer frames from FPS."""
from fractions import Fraction
import av


def adjacent_frame(path, seconds, direction, cancelled=lambda: False):
    target=Fraction(str(seconds))
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        origin=(Fraction(container.start_time,av.time_base) if container.start_time is not None
                else Fraction(stream.start_time or 0)*stream.time_base)
        # Decode from a preceding keyframe. Retry from the beginning when a
        # sparse/VFR interval leaves no predecessor in the initial window.
        for start in (max(Fraction(0),target-2),Fraction(0)):
            container.seek(int((origin+start)/stream.time_base),stream=stream,backward=True,any_frame=False)
            previous=current=following=None
            for frame in container.decode(stream):
                if cancelled():
                    return None
                if frame.pts is None:
                    continue
                stamp=Fraction(frame.pts)*frame.time_base-origin
                if stamp <= target+Fraction(1,1000000):
                    previous,current=current,(stamp,frame)
                else:
                    following=(stamp,frame)
                    break
            selected=following if direction>0 else previous if direction<0 else current
            if selected is None:
                if direction<0 and start>0:
                    continue
                selected=current or following
            if selected is None:
                raise ValueError('沒有可解碼的影格')
            stamp,frame=selected
            rgb=frame.reformat(format='rgb24')
            return float(stamp),rgb.width,rgb.height,rgb.planes[0].line_size,bytes(rgb.planes[0]),getattr(frame,'rotation',0)

