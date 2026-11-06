//! Native renderer/decoder integration checks. Runs against a supplied test clip.
#[path = "../frame_index.rs"]
mod frame_index;
#[path = "../player.rs"]
mod player;
use eframe::egui;
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
struct Verify {
    players: Vec<Arc<Mutex<player::Player>>>,
    job: Option<frame_index::Job>,
    pts: Vec<f64>,
    index: usize,
    last: Instant,
    started: Instant,
    checks: Vec<serde_json::Value>,
    done: bool,
    report: PathBuf,
    gl: Arc<eframe::glow::Context>,
    api: Arc<player::Api>,
    clip: String,
    references: Vec<Vec<u8>>,
    picture_step: usize,
    baseline: Vec<u8>,
    other_baseline: Vec<u8>,
}
impl eframe::App for Verify {
    fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        if self.players.is_empty() {
            for i in 0..2 {
                let mut p = player::Player::new(self.api.clone(), self.gl.clone()).unwrap();
                p.register(frame);
                p.load(&self.clip, 0., true).unwrap();
                p.set_number("volume", if i == 0 { 23. } else { 78. })
                    .unwrap();
                self.players.push(Arc::new(Mutex::new(p)));
            }
        }
        for p in &self.players {
            p.lock().unwrap().poll();
        }
        if let Some(r) = self.job.as_ref().and_then(|j| j.poll()) {
            self.job = None;
            match r {
                Ok(pts) => {
                    self.pts = pts;
                    self.last = Instant::now();
                }
                Err(e) => {
                    self.checks.push(serde_json::json!({"error":e}));
                    self.done = true;
                }
            }
        }
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.label("Native decoder integration verification");
            for p in &self.players {
                let p = p.clone();
                let rect = ui.allocate_space(egui::vec2(320., 180.)).1;
                let id = p.lock().unwrap().texture_id.unwrap();
                ui.painter().add(egui::PaintCallback {
                    rect,
                    callback: Arc::new(egui_glow::CallbackFn::new(move |_, _| {
                        p.lock().unwrap().paint(320, 180)
                    })),
                });
                ui.painter().image(
                    id,
                    rect,
                    egui::Rect::from_min_max(egui::Pos2::ZERO, egui::pos2(1., 1.)),
                    egui::Color32::WHITE,
                );
            }
        });
        if !self.done
            && self.picture_step == 0
            && !self.pts.is_empty()
            && self.players[0].lock().unwrap().loaded
            && self.last.elapsed() > Duration::from_millis(220)
        {
            let p = self.players[0].lock().unwrap();
            if self.index > 0 {
                let expected = self.pts[sequence(self.index - 1, self.pts.len())];
                let actual = p.number("time-pos");
                let pixels = p.rendered_pixels();
                let nearest = self
                    .references
                    .iter()
                    .enumerate()
                    .filter(|(_, r)| r.len() == pixels.len())
                    .min_by_key(|(_, r)| {
                        r.iter()
                            .zip(&pixels)
                            .map(|(a, b)| (*a as i64 - *b as i64).pow(2))
                            .sum::<i64>()
                    })
                    .map(|(i, _)| i);
                self.checks.push(serde_json::json!({"expected":expected,"actual":actual,"nearest_decoded_image":nearest,"pass":actual.is_some_and(|t|(t-expected).abs()<0.0001)&&nearest==Some(sequence(self.index-1,self.pts.len()))}));
            }
            if self.index == self.pts.len() * 2 {
                let second = self.players[1].lock().unwrap();
                self.checks.push(serde_json::json!({"independent_volume":p.number("volume")==Some(23.)&&second.number("volume")==Some(78.),"paused":p.flag("pause")}));
                self.baseline = p.rendered_pixels();
                self.other_baseline = second.rendered_pixels();
                p.set_number("brightness", 35.).unwrap();
                self.picture_step = 1;
                self.last = Instant::now();
            } else {
                p.command(&[
                    "seek",
                    &format!("{:.8}", self.pts[sequence(self.index, self.pts.len())]),
                    "absolute+exact",
                ])
                .unwrap();
                self.index += 1;
                self.last = Instant::now();
            }
        }
        if !self.done && self.picture_step > 0 && self.last.elapsed() > Duration::from_millis(300) {
            let keys = ["brightness", "contrast", "saturation", "gamma", "hue"];
            let key = keys[(self.picture_step - 1) / 2];
            let p = self.players[0].lock().unwrap();
            let second = self.players[1].lock().unwrap();
            let delta = image_delta(&self.baseline, &p.rendered_pixels());
            let other_delta = image_delta(&self.other_baseline, &second.rendered_pixels());
            let adjusted = self.picture_step % 2 == 1;
            let pass = if adjusted { delta > 0.5 } else { delta < 0.1 } && other_delta < 0.1;
            self.checks.push(serde_json::json!({"picture":key,"adjusted":adjusted,"pixel_delta":delta,"other_cell_delta":other_delta,"pass":pass}));
            if self.picture_step == 10 {
                self.done = true;
            } else {
                if adjusted {
                    p.set_number(key, 0.).unwrap();
                } else {
                    p.set_number(keys[self.picture_step / 2], 35.).unwrap();
                }
                self.picture_step += 1;
                self.last = Instant::now();
            }
        }
        if self.started.elapsed() > Duration::from_secs(45) {
            self.checks.push(serde_json::json!({"error":"timeout"}));
            self.done = true;
        }
        if self.done {
            let pass = self.checks.iter().all(|v| {
                v.get("error").is_none()
                    && v.get("pass") != Some(&false.into())
                    && v.get("independent_volume") != Some(&false.into())
            });
            let _=std::fs::write(&self.report,serde_json::to_vec_pretty(&serde_json::json!({"pass":pass,"decoded_frames":self.pts.len(),"checks":self.checks})).unwrap());
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
        ctx.request_repaint_after(Duration::from_millis(16));
    }
    fn on_exit(&mut self, _: Option<&eframe::glow::Context>) {
        self.players.clear();
    }
}
fn main() -> eframe::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let clip = args[1].clone();
    let report = PathBuf::from(&args[2]);
    let runtime = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("runtime");
    let reference_dir = report.with_extension("frames");
    std::fs::create_dir_all(&reference_dir).unwrap();
    let status = std::process::Command::new(runtime.join("ffmpeg.exe"))
        .args([
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            &clip,
            "-an",
            "-fps_mode",
            "passthrough",
            "-y",
        ])
        .arg(reference_dir.join("%04d.png"))
        .status()
        .unwrap();
    assert!(status.success());
    let mut files = std::fs::read_dir(reference_dir)
        .unwrap()
        .flatten()
        .map(|e| e.path())
        .collect::<Vec<_>>();
    files.sort();
    let references = files
        .iter()
        .map(|p| image::open(p).unwrap().to_rgb8().into_raw())
        .collect();
    let job =
        frame_index::Job::start(&runtime.join("ffmpeg.exe"), std::path::Path::new(&clip)).unwrap();
    let api = player::Api::load(&runtime.join("libmpv-2.dll")).unwrap();
    eframe::run_native(
        "MultipleVideoPlayer native verification",
        eframe::NativeOptions {
            renderer: eframe::Renderer::Glow,
            ..Default::default()
        },
        Box::new(move |cc| {
            Ok(Box::new(Verify {
                players: vec![],
                job: Some(job),
                pts: vec![],
                index: 0,
                last: Instant::now(),
                started: Instant::now(),
                checks: vec![],
                done: false,
                report,
                gl: cc.gl.clone().unwrap(),
                api,
                clip,
                references,
                picture_step: 0,
                baseline: vec![],
                other_baseline: vec![],
            }))
        }),
    )
}

fn sequence(i: usize, n: usize) -> usize {
    if i < n {
        i
    } else {
        2 * n - i - 1
    }
}
fn image_delta(a: &[u8], b: &[u8]) -> f64 {
    if a.is_empty() || a.len() != b.len() {
        return f64::INFINITY;
    }
    a.iter()
        .zip(b)
        .map(|(a, b)| (*a as f64 - *b as f64).abs())
        .sum::<f64>()
        / a.len() as f64
}
