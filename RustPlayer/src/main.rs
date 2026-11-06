#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod app;
mod frame_index;
mod model;
mod player;
mod scrub;
mod view;
use eframe::egui;
static STARTED: std::sync::OnceLock<std::time::Instant> = std::sync::OnceLock::new();
fn main() -> eframe::Result<()> {
    let _ = STARTED.set(std::time::Instant::now());
    let options = eframe::NativeOptions {
        renderer: eframe::Renderer::Glow,
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1280., 800.])
            .with_min_inner_size([720., 420.]),
        ..Default::default()
    };
    eframe::run_native(
        &format!("MultipleVideoPlayer {} — Rust", env!("CARGO_PKG_VERSION")),
        options,
        Box::new(|cc| Ok(Box::new(app::App::new(cc)))),
    )
}
