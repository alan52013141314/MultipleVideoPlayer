"""Position a complete video surface within a clipped cell, in logical pixels."""
from gridplayer.params.static import VideoAspect


def video_rect(video_size, viewport, mode, offset=(0, 0), ratio=1, scale=1):
    vw, vh = video_size
    width, height = viewport
    if min(vw, vh, width, height) <= 0:
        return (0, 0, width, height), (0, 0)
    if mode == VideoAspect.STRETCH:
        draw_w, draw_h = width * scale, height * scale
    else:
        factor = {
            VideoAspect.NONE: min(width / vw, height / vh),
            VideoAspect.FIT: max(width / vw, height / vh),
            VideoAspect.WIDTH: width / vw,
            VideoAspect.HEIGHT: height / vh,
            VideoAspect.ORIGINAL: 1 / ratio,
        }[mode] * scale
        draw_w, draw_h = vw * factor, vh * factor
    draw_w, draw_h = max(1, round(draw_w)), max(1, round(draw_h))
    center_x, center_y = (width - draw_w) / 2, (height - draw_h) / 2
    dx = max(-abs(center_x), min(abs(center_x), offset[0])) if draw_w > width else 0
    dy = max(-abs(center_y), min(abs(center_y), offset[1])) if draw_h > height else 0
    return (round(center_x + dx), round(center_y + dy), draw_w, draw_h), (dx, dy)
