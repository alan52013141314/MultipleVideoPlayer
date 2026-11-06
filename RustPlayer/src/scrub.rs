//! Limit preview requests while always sending the final pointer position.
#[derive(Default)]
pub struct Scrub {
    last: Option<(f64, f64)>,
}
impl Scrub {
    pub fn reset(&mut self) {
        self.last = None;
    }
    pub fn should_seek(&mut self, target: f64, now: f64, released: bool) -> bool {
        if let Some((previous, time)) = self.last {
            if (target - previous).abs() < 0.000_001 || (!released && now - time < 0.05) {
                return false;
            }
        }
        self.last = Some((target, now));
        true
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn drag_coalesces_but_release_is_exact() {
        let mut s = Scrub::default();
        assert!(s.should_seek(1., 0., false));
        assert!(!s.should_seek(2., 0.01, false));
        assert!(!s.should_seek(3., 0.02, false));
        assert!(s.should_seek(4., 0.05, false));
        assert!(!s.should_seek(4., 0.2, false));
        assert!(s.should_seek(4.125, 0.06, true));
        s.reset();
        assert!(s.should_seek(4.125, 0.07, true));
    }
}
