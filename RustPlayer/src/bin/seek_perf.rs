//! Multi-player regression harness: repeated seeks on one cell must not stall the GUI.
#[path = "../player.rs"]
mod player;
use eframe::egui;
use std::{
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
struct Bench {
    players: Vec<Arc<Mutex<player::Player>>>,
    start: Instant,
    last: Instant,
    gaps: Vec<f64>,
    calls: Vec<f64>,
    clip: String,
    report: String,
    api: Arc<player::Api>,
    gl: Arc<eframe::glow::Context>,
    n: usize,
    click: Option<Instant>,
    click_ms: Option<f64>,
    other_start: Option<f64>,
    other_end: Option<f64>,
}
impl eframe::App for Bench {
    fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        if self.players.is_empty() {
            for _ in 0..4 {
                let mut p = player::Player::new(self.api.clone(), self.gl.clone()).unwrap();
                p.register(frame);
                p.set("mute", "yes").unwrap();
                p.load(&self.clip, 0., false).unwrap();
                self.players.push(Arc::new(Mutex::new(p)));
            }
            self.start = Instant::now();
            self.last = Instant::now();
        }
        let age = self.start.elapsed().as_secs_f64();
        if age > 2. && age < 8. {
            self.gaps.push(self.last.elapsed().as_secs_f64() * 1000.);
        }
        self.last = Instant::now();
        for p in &self.players {
            let mut p = p.lock().unwrap();
            p.poll();
            for key in ["duration", "time-pos", "dwidth", "dheight"] {
                let _ = p.number(key);
            }
            let _ = p.flag("pause");
            p.refresh_hidden();
        }
        if age > 2. && age < 8. {
            let other = self.players[1].lock().unwrap().number("time-pos");
            if self.other_start.is_none() {
                self.other_start = other;
            }
            self.other_end = other;
            let p = self.players[0].lock().unwrap();
            let begin = Instant::now();
            p.set("ab-loop-b", "no").unwrap();
            p.set("ab-loop-a", "no").unwrap();
            p.command(&[
                "seek",
                &format!("{}", 3. + (self.n % 80) as f64 * 0.13),
                "absolute+exact",
            ])
            .unwrap();
            self.calls.push(begin.elapsed().as_secs_f64() * 1000.);
            self.n += 1;
        }
        if age >= 8. && self.click.is_none() {
            self.click = Some(Instant::now());
            let p = self.players[0].lock().unwrap();
            p.set("pause", "yes").unwrap();
            p.command(&["seek", "7.123", "absolute+exact"]).unwrap();
        }
        if let Some(start) = self.click {
            let p = self.players[0].lock().unwrap();
            if self.click_ms.is_none()
                && p.flag("pause")
                && p.number("time-pos")
                    .is_some_and(|t| (t - 7.123).abs() < 0.04)
            {
                self.click_ms = Some(start.elapsed().as_secs_f64() * 1000.);
            }
        }
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.label("Multi-player seek regression");
            ui.horizontal_wrapped(|ui| {
                for p in &self.players {
                    let rect = ui.allocate_space(egui::vec2(320., 180.)).1;
                    let id = p.lock().unwrap().texture_id.unwrap();
                    let p = p.clone();
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
        });
        if age > 9. {
            let progress = self
                .other_end
                .zip(self.other_start)
                .map(|(end, start)| end - start)
                .unwrap_or(0.);
            let pass = self.gaps.len() > 120
                && self.gaps.iter().all(|t| *t < 100.)
                && progress > 5.
                && self.click_ms.is_some_and(|t| t < 500.);
            let stats = |v: &[f64]| {
                let mut s = v.to_vec();
                s.sort_by(f64::total_cmp);
                serde_json::json!({"count":s.len(),"p95_ms":s.get(s.len()*95/100),"max_ms":s.last(),"over_100ms":s.iter().filter(|x|**x>100.).count()})
            };
            std::fs::write(
                &self.report,
                serde_json::to_vec_pretty(
                    &serde_json::json!({"pass":pass,"ui":stats(&self.gaps),"seek_calls":stats(&self.calls),"other_progress_seconds":progress,"final_seek_position_ms":self.click_ms}),
                )
                .unwrap(),
            )
            .unwrap();
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
    let api = player::Api::load(
        &std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("runtime/libmpv-2.dll"),
    )
    .unwrap();
    eframe::run_native(
        "Seek performance regression",
        eframe::NativeOptions {
            renderer: eframe::Renderer::Glow,
            ..Default::default()
        },
        Box::new(move |cc| {
            Ok(Box::new(Bench {
                players: vec![],
                start: Instant::now(),
                last: Instant::now(),
                gaps: vec![],
                calls: vec![],
                clip: args[1].clone(),
                report: args[2].clone(),
                api,
                gl: cc.gl.clone().unwrap(),
                n: 0,
                click: None,
                click_ms: None,
                other_start: None,
                other_end: None,
            }))
        }),
    )
}
