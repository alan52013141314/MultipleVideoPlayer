//! Presentation timestamps come from decoded frames, never an average frame rate.
use std::{
    io::{BufRead, BufReader},
    path::Path,
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
};
pub struct Job {
    child: Arc<Mutex<Child>>,
    rx: mpsc::Receiver<Result<Vec<f64>, String>>,
}
impl Job {
    pub fn start(ffmpeg: &Path, video: &Path) -> Result<Self, String> {
        let mut command = Command::new(ffmpeg);
        command
            .args([
                "-nostdin",
                "-hide_banner",
                "-nostats",
                "-loglevel",
                "info",
                "-i",
            ])
            .arg(video)
            .args([
                "-map",
                "0:v:0",
                "-vf",
                "showinfo",
                "-an",
                "-sn",
                "-dn",
                "-fps_mode",
                "passthrough",
                "-f",
                "null",
                "-",
            ])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|e| format!("無法建立解碼索引：{e}"))?;
        let stderr = child.stderr.take().ok_or("無法讀取影格資料")?;
        let child = Arc::new(Mutex::new(child));
        let owned = child.clone();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let mut pts = Vec::new();
            let mut tail = String::new();
            let mut time_base = None;
            let mut invalid = false;
            for line in BufReader::new(stderr).lines() {
                match line {
                    Ok(line) => {
                        if let Some(base) = parse_time_base(&line) {
                            time_base = Some(base);
                        }
                        if let Some(t) = time_base.and_then(|base| parse_pts(&line, base)) {
                            if pts.last().is_none_or(|p| t > *p) {
                                pts.push(t);
                            } else {
                                invalid = true;
                            }
                        } else if !line.is_empty() {
                            tail = line;
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(Err(e.to_string()));
                        return;
                    }
                }
            }
            let result = owned.lock().unwrap().wait();
            let result = match result {
                Ok(s) if s.success() && !pts.is_empty() && !invalid => Ok(pts),
                _ if invalid => Err("影片含重複或逆序時間戳，無法保證精準逐格。".into()),
                _ => Err(format!("影片解碼索引失敗：{tail}")),
            };
            let _ = tx.send(result);
        });
        Ok(Self { child, rx })
    }
    pub fn poll(&self) -> Option<Result<Vec<f64>, String>> {
        self.rx.try_recv().ok()
    }
}
impl Drop for Job {
    fn drop(&mut self) {
        let mut c = self.child.lock().unwrap();
        if c.try_wait().ok().flatten().is_none() {
            let _ = c.kill();
        }
    }
}
fn parse_time_base(line: &str) -> Option<(i64, i64)> {
    let token = line
        .split("config in time_base:")
        .nth(1)?
        .trim()
        .split(',')
        .next()?;
    let (a, b) = token.split_once('/')?;
    let a = a.trim().parse().ok()?;
    let b = b.trim().parse().ok()?;
    if a > 0 && b > 0 {
        Some((a, b))
    } else {
        None
    }
}
fn parse_pts(line: &str, base: (i64, i64)) -> Option<f64> {
    if !line.contains("showinfo") || !line.contains(" n:") {
        return None;
    }
    line.split(" pts:")
        .nth(1)?
        .split_whitespace()
        .next()?
        .parse::<i64>()
        .ok()
        .map(|n| n as f64 * base.0 as f64 / base.1 as f64)
}
pub fn adjacent(pts: &[f64], current: f64, direction: isize) -> Option<f64> {
    if pts.is_empty() {
        return None;
    }
    let after = pts.partition_point(|t| *t <= current + 0.00001);
    let current_idx = after.saturating_sub(1);
    let target = if direction > 0 {
        current_idx.saturating_add(1).min(pts.len() - 1)
    } else {
        current_idx.saturating_sub(1)
    };
    Some(pts[target])
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vfr_adjacent_and_boundaries() {
        let pts = [0., 0.04, 0.08, 0.2, 0.24, 0.6];
        assert_eq!(adjacent(&pts, 0.2, -1), Some(0.08));
        assert_eq!(adjacent(&pts, 0.2, 1), Some(0.24));
        assert_eq!(adjacent(&pts, 0., -1), Some(0.));
        assert_eq!(adjacent(&pts, 0.6, 1), Some(0.6));
    }
    #[test]
    fn parse_real_decoder_line() {
        assert_eq!(
            parse_pts(
                "[Parsed_showinfo_0 @ 123] n:   12 pts: 512 pts_time:0.04 duration:0.04",
                (1, 12800)
            ),
            Some(0.04)
        );
        assert_eq!(
            parse_time_base("[Parsed_showinfo_0] config in time_base: 1/12800, frame_rate: 25/1"),
            Some((1, 12800))
        );
        assert_eq!(
            parse_pts(
                "[showinfo] n: 1 pts: 128001280 pts_time:10000.1",
                (1, 12800)
            ),
            Some(10000.1)
        );
    }
}
