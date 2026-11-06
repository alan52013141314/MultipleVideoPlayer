use eframe::egui::{pos2, vec2, Pos2, Rect, Vec2};
pub fn video_rect(
    cell: Rect,
    source: Vec2,
    mode: &str,
    scale: f32,
    center: [f32; 2],
    dpi: f32,
) -> Rect {
    let ratios = cell.size() / source.max(vec2(1., 1.));
    let size = match mode {
        "stretch" => cell.size(),
        "fit" => source * ratios.x.max(ratios.y),
        "width" => source * ratios.x,
        "height" => source * ratios.y,
        "original" => source / dpi.max(0.1),
        _ => source * ratios.x.min(ratios.y),
    } * scale;
    let mut min = cell.center() - vec2(size.x * center[0], size.y * center[1]);
    for axis in 0..2 {
        if size[axis] <= cell.size()[axis] {
            min[axis] = cell.center()[axis] - size[axis] / 2.
        } else {
            min[axis] = min[axis].clamp(cell.max[axis] - size[axis], cell.min[axis]);
        }
    }
    Rect::from_min_size(min, size)
}
// Geometry inputs remain explicit so callers cannot mix logical and physical pixels.
#[allow(clippy::too_many_arguments)]
pub fn zoom(
    cell: Rect,
    source: Vec2,
    mode: &str,
    scale: &mut f64,
    center: &mut [f32; 2],
    dpi: f32,
    anchor: Pos2,
    factor: f32,
) {
    let old = video_rect(cell, source, mode, *scale as f32, *center, dpi);
    let anchor = pos2(
        anchor.x.clamp(old.min.x, old.max.x),
        anchor.y.clamp(old.min.y, old.max.y),
    );
    let uv = (anchor - old.min) / old.size();
    *scale = (*scale * factor as f64).clamp(1., 8.);
    let new = video_rect(cell, source, mode, *scale as f32, *center, dpi);
    let newmin = anchor - new.size() * uv;
    let c = (cell.center() - newmin) / new.size();
    *center = [c.x.clamp(0., 1.), c.y.clamp(0., 1.)];
    clamp_center(cell, source, mode, *scale as f32, center, dpi);
}
pub fn clamp_center(
    cell: Rect,
    source: Vec2,
    mode: &str,
    scale: f32,
    center: &mut [f32; 2],
    dpi: f32,
) {
    let r = video_rect(cell, source, mode, scale, *center, dpi);
    let c = (cell.center() - r.min) / r.size();
    *center = [c.x, c.y];
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fit_fill_original() {
        let c = Rect::from_min_size(Pos2::ZERO, vec2(400., 400.));
        let s = vec2(1920., 1080.);
        assert_eq!(
            video_rect(c, s, "none", 1., [0.5; 2], 1.).size(),
            vec2(400., 225.)
        );
        assert_eq!(
            video_rect(c, s, "original", 1., [0.5; 2], 2.).size(),
            vec2(960., 540.)
        );
        let r = video_rect(c, s, "fit", 1., [0.; 2], 1.);
        assert!(r.contains(c.min) && r.contains(c.max));
    }
    #[test]
    fn zoom_keeps_cursor_pixel() {
        let c = Rect::from_min_size(Pos2::ZERO, vec2(600., 400.));
        let s = vec2(600., 400.);
        let a = pos2(120., 240.);
        let mut scale = 1.;
        let mut center = [0.5; 2];
        zoom(c, s, "none", &mut scale, &mut center, 1., a, 2.);
        let r = video_rect(c, s, "none", scale as f32, center, 1.);
        let uv = (a - r.min) / r.size();
        assert!((uv.x - 0.2).abs() < 0.001 && (uv.y - 0.6).abs() < 0.001);
    }
}
