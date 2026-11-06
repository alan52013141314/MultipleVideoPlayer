use crate::{
    model::{self, Cell, Video, Workspace},
    player::{Api, Player},
    view,
};
use eframe::egui::{self, pos2, vec2, Color32, Pos2, Rect, Sense, Stroke, Vec2};
use std::{
    path::{Path, PathBuf},
    sync::{mpsc, Arc, Mutex},
    time::{Duration, Instant},
};
type Shared = Arc<Mutex<Player>>;
#[derive(Default)]
struct Runtime {
    player: Option<Shared>,
    key: String,
    time: f64,
    duration: f64,
    source: Vec2,
    drag: Option<u8>,
    error: String,
    loading: bool,
    popup_open: bool,
    index: Vec<f64>,
    index_job: Option<crate::frame_index::Job>,
    pending_step: Option<isize>,
}
struct ScanResult {
    index: usize,
    id: String,
    path: PathBuf,
    files: Result<Vec<PathBuf>, String>,
}
pub struct App {
    state: Workspace,
    runtime: Vec<Runtime>,
    api: Result<Arc<Api>, String>,
    gl: Arc<eframe::glow::Context>,
    data: PathBuf,
    last_hover: usize,
    focus: Option<usize>,
    seek_seconds: f64,
    presets: Vec<(String, String)>,
    selected: String,
    preset_name: String,
    save_dialog: bool,
    overwrite: bool,
    ab_edit: Option<(usize, f64, f64)>,
    message: String,
    tx: mpsc::Sender<ScanResult>,
    rx: mpsc::Receiver<ScanResult>,
    restore_window: bool,
    started: Instant,
    first_paint: bool,
    first_video: bool,
    ffmpeg: PathBuf,
    save_last: bool,
    remove_cell: Option<usize>,
}
impl App {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        let mut fonts = egui::FontDefinitions::default();
        for path in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyh.ttc"] {
            if let Ok(data) = std::fs::read(path) {
                fonts
                    .font_data
                    .insert("CJK".into(), egui::FontData::from_owned(data).into());
                fonts
                    .families
                    .entry(egui::FontFamily::Proportional)
                    .or_default()
                    .push("CJK".into());
                break;
            }
        }
        cc.egui_ctx.set_fonts(fonts);
        cc.egui_ctx.set_theme(egui::ThemePreference::Dark);
        let exe = std::env::current_exe().unwrap_or_default();
        let base = exe.parent().unwrap_or(Path::new("."));
        let data = std::env::var_os("GRIDPLAYER_DATA_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| base.join("portable_data"));
        let runtime = if !cfg!(debug_assertions) || base.join("runtime/libmpv-2.dll").exists() {
            base.join("runtime")
        } else {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("runtime")
        };
        let mut message = String::new();
        let mut save_last = true;
        let mut state = if data.join("presets/last.json").exists() {
            match model::read_preset(&data.join("presets/last.json")) {
                Ok(p) => p.state,
                Err(e) => {
                    message = format!("上一次工作區無法讀取，原檔保留：{e}");
                    save_last = false;
                    Workspace::default()
                }
            }
        } else {
            Workspace::default()
        };
        for c in &mut state.cells {
            if let Some(v) = &mut c.video {
                v.is_paused = true;
            }
        }
        let seek_seconds = std::fs::read_to_string(data.join("workspace.ini"))
            .ok()
            .and_then(|s| {
                s.lines().find_map(|l| {
                    l.trim()
                        .strip_prefix("seek_seconds=")
                        .and_then(|v| v.trim().parse::<f64>().ok())
                })
            })
            .filter(|x| x.is_finite() && *x > 0. && *x <= 86400.)
            .unwrap_or(5.);
        let (tx, rx) = mpsc::channel();
        let mut app = Self {
            state,
            runtime: (0..12).map(|_| Runtime::default()).collect(),
            api: Api::load(&runtime.join("libmpv-2.dll")),
            gl: cc.gl.clone().unwrap(),
            data,
            last_hover: 0,
            focus: None,
            seek_seconds,
            presets: vec![],
            selected: "last".into(),
            preset_name: String::new(),
            save_dialog: false,
            overwrite: false,
            ab_edit: None,
            message,
            tx,
            rx,
            restore_window: true,
            started: *crate::STARTED.get().unwrap_or(&Instant::now()),
            first_paint: false,
            first_video: false,
            ffmpeg: runtime.join("ffmpeg.exe"),
            save_last,
            remove_cell: None,
        };
        app.refresh_presets();
        let paths = std::env::args_os()
            .skip(1)
            .map(PathBuf::from)
            .collect::<Vec<_>>();
        if !paths.is_empty() {
            app.open_paths(0, paths)
        }
        app
    }
    fn refresh_presets(&mut self) {
        self.presets = std::fs::read_dir(self.data.join("presets"))
            .into_iter()
            .flatten()
            .flatten()
            .filter_map(|e| {
                let p = e.path();
                if p.extension()?.to_str()? != "json" {
                    return None;
                }
                let key = p.file_stem()?.to_str()?.to_owned();
                let value: serde_json::Value =
                    serde_json::from_slice(&std::fs::read(p).ok()?).ok()?;
                Some((key, value.get("name")?.as_str()?.to_owned()))
            })
            .collect();
        self.presets.sort_by(|a, b| {
            (a.0 != "last")
                .cmp(&(b.0 != "last"))
                .then_with(|| model::natural_cmp(&a.1, &b.1))
        });
    }
    fn report(&mut self, result: Result<(), String>) {
        if let Err(e) = result {
            self.message = e;
        }
    }
    fn command(&mut self, i: usize, args: &[&str]) {
        if args.first() == Some(&"stop") || args == ["cycle", "pause"] {
            self.runtime[i].pending_step = None;
        }
        if let Some(p) = self.runtime[i].player.clone() {
            self.report(p.lock().unwrap().command(args));
        }
    }
    fn snapshot(&mut self) -> Workspace {
        for (i, c) in self.state.cells.iter_mut().enumerate() {
            if let Some(v) = &mut c.video {
                if let Some(p) = &self.runtime[i].player {
                    let p = p.lock().unwrap();
                    if p.loaded {
                        v.current_position = (p.number("time-pos").unwrap_or(self.runtime[i].time)
                            * 1000.)
                            .round() as i64;
                        v.is_paused = p.flag("pause");
                    }
                }
            }
        }
        self.state.clone()
    }
    fn save(&mut self, key: String, name: String) {
        let snapshot = self.snapshot();
        let r = model::save_preset(&self.data.join("presets"), &key, &name, &snapshot);
        if r.is_ok() {
            self.selected = key;
            self.refresh_presets();
        }
        self.report(r);
    }
    fn load_preset(&mut self) {
        let path = self
            .data
            .join("presets")
            .join(format!("{}.json", self.selected));
        match model::read_preset(&path) {
            Err(e) => self.message = e,
            Ok(p) => {
                for i in 0..12 {
                    self.command(i, &["stop"]);
                    self.runtime[i].key.clear();
                    self.runtime[i].error.clear();
                }
                self.state = p.state;
                for c in &mut self.state.cells {
                    if let Some(v) = &mut c.video {
                        v.is_paused = true
                    }
                }
                self.focus = None;
                self.last_hover = 0;
                self.restore_window = true;
            }
        }
    }
    fn open_paths(&mut self, start: usize, paths: Vec<PathBuf>) {
        if paths.len() > self.state.cells.len().saturating_sub(start) {
            self.message = "拖入數目超過剩餘格子，超出部分未載入。".into();
        }
        for (i, path) in (start..self.state.cells.len()).zip(paths) {
            let tx = self.tx.clone();
            let id = uuid::Uuid::new_v4().simple().to_string();
            self.state.cells[i].id = id.clone();
            self.runtime[i].loading = true;
            std::thread::spawn(move || {
                let files = if path.is_dir() {
                    model::scan(&path, true)
                } else if path.is_file() && model::is_video(&path) {
                    model::scan(path.parent().unwrap_or(Path::new(".")), false)
                } else {
                    Err("請拖入影片檔案或資料夾".into())
                };
                let _ = tx.send(ScanResult {
                    index: i,
                    id,
                    path,
                    files,
                });
            });
        }
    }
    fn pick(&mut self, i: usize, folder: bool) {
        if folder {
            if let Some(p) = rfd::FileDialog::new().pick_folder() {
                self.open_paths(i, vec![p]);
            }
        } else if let Some(p) = rfd::FileDialog::new().pick_files() {
            self.open_paths(i, p);
        }
    }
    fn apply_scans(&mut self) {
        while let Ok(r) = self.rx.try_recv() {
            if self.state.cells.get(r.index).is_none_or(|c| c.id != r.id) {
                continue;
            }
            self.runtime[r.index].loading = false;
            match r.files {
                Err(e) => self.message = e,
                Ok(files) => {
                    let file = if r.path.is_dir() {
                        files.first().cloned()
                    } else {
                        Some(r.path.clone())
                    };
                    if let Some(file) = file {
                        let c = &mut self.state.cells[r.index];
                        let mut v = Video::new(&file);
                        if let Some(old) = &c.video {
                            v.volume = old.volume;
                            v.is_muted = old.is_muted;
                            v.aspect_mode = old.aspect_mode.clone();
                        }
                        c.video = Some(v);
                        c.playlist = files.iter().map(|p| p.to_string_lossy().into()).collect();
                        c.source_folder = if r.path.is_dir() {
                            Some(r.path.to_string_lossy().into())
                        } else {
                            None
                        };
                        c.view_center = [0.5; 2];
                        c.loop_suspended = false;
                        self.runtime[r.index].key.clear();
                    } else {
                        self.message = "資料夾中沒有支援的影片".into();
                    }
                }
            }
        }
    }
    fn next(&mut self, i: usize, direction: isize) {
        let c = &mut self.state.cells[i];
        if let Some(v) = &c.video {
            if c.playlist.is_empty() {
                return;
            }
            let current = c.playlist.iter().position(|p| p == &v.uri).unwrap_or(0);
            let next =
                (current as isize + direction).rem_euclid(c.playlist.len() as isize) as usize;
            let mut new = Video::new(Path::new(&c.playlist[next]));
            new.volume = v.volume;
            new.is_muted = v.is_muted;
            new.aspect_mode = v.aspect_mode.clone();
            new.is_paused = v.is_paused;
            c.video = Some(new);
            c.view_center = [0.5; 2];
            c.loop_suspended = false;
            self.runtime[i].key.clear();
        }
    }
    fn set_loop(&mut self, i: usize) {
        let c = &self.state.cells[i];
        let interval = if c.loop_suspended {
            None
        } else {
            c.video.as_ref().and_then(Video::interval)
        };
        if let Some(p) = self.runtime[i].player.clone() {
            let p = p.lock().unwrap();
            let _ = p.set("ab-loop-b", "no");
            let _ = p.set("ab-loop-a", "no");
            if let Some((a, b)) = interval {
                let _ = p.set_number("ab-loop-a", a);
                let _ = p.set_number("ab-loop-b", b);
            }
        }
    }
    fn seek(&mut self, i: usize, t: f64) {
        self.runtime[i].pending_step = None;
        let t = t.clamp(0., self.runtime[i].duration.max(0.));
        let c = &mut self.state.cells[i];
        if let Some(v) = &mut c.video {
            c.loop_suspended = v.interval().is_some_and(|(a, b)| t < a || t > b);
            v.current_position = (t * 1000.).round() as i64;
        }
        self.set_loop(i);
        self.command(i, &["seek", &format!("{t:.6}"), "absolute+exact"]);
        self.runtime[i].time = t;
    }
    fn reset_view(&mut self, i: usize) {
        self.state.cells[i].view_center = [0.5; 2];
        if let Some(v) = &mut self.state.cells[i].video {
            v.scale = 1.;
        }
    }
    fn step_frame(&mut self, i: usize, direction: isize) {
        let Some(v) = &self.state.cells[i].video else {
            return;
        };
        if !v.is_paused {
            return;
        }
        if self.runtime[i].index.is_empty() {
            self.runtime[i].pending_step = Some(direction);
            if self.runtime[i].index_job.is_none() {
                match crate::frame_index::Job::start(&self.ffmpeg, Path::new(&v.uri)) {
                    Ok(job) => self.runtime[i].index_job = Some(job),
                    Err(e) => self.message = e,
                }
            }
            return;
        }
        let current = self.runtime[i]
            .player
            .as_ref()
            .and_then(|p| p.lock().unwrap().number("time-pos"))
            .unwrap_or(self.runtime[i].time);
        if let Some(target) =
            crate::frame_index::adjacent(&self.runtime[i].index, current, direction)
        {
            self.seek(i, target);
        }
    }
    fn poll_indexes(&mut self) {
        for i in 0..self.state.cells.len() {
            if let Some(result) = self.runtime[i]
                .index_job
                .as_ref()
                .and_then(|job| job.poll())
            {
                self.runtime[i].index_job = None;
                match result {
                    Ok(pts) => {
                        self.runtime[i].index = pts;
                        if let Some(direction) = self.runtime[i].pending_step.take() {
                            self.step_frame(i, direction);
                        }
                    }
                    Err(e) => {
                        self.runtime[i].pending_step = None;
                        self.message = e;
                    }
                }
            }
        }
    }
    fn update_players(&mut self, frame: &mut eframe::Frame) {
        let mut created = false;
        for i in 0..self.state.cells.len() {
            let Some(v) = self.state.cells[i].video.clone() else {
                continue;
            };
            if self.runtime[i].player.is_none() && !created {
                created = true;
                match &self.api {
                    Err(e) => self.runtime[i].error = e.clone(),
                    Ok(api) => match Player::new(api.clone(), self.gl.clone()) {
                        Ok(mut p) => {
                            p.register(frame);
                            self.runtime[i].player = Some(Arc::new(Mutex::new(p)));
                        }
                        Err(e) => self.runtime[i].error = e,
                    },
                }
            }
            let Some(p) = self.runtime[i].player.clone() else {
                continue;
            };
            if self.runtime[i].key != v.id {
                self.runtime[i].index_job = None;
                self.runtime[i].index.clear();
                self.runtime[i].pending_step = None;
                self.runtime[i].key = v.id.clone();
                self.runtime[i].time = v.current_position as f64 / 1000.;
                self.runtime[i].duration = 0.;
                self.runtime[i].error.clear();
                let mut player = p.lock().unwrap();
                if !Path::new(&v.uri).is_file() {
                    self.runtime[i].error = "影片不存在；路徑保留在 preset 中".into();
                    let _ = player.command(&["stop"]);
                    player.loaded = false;
                    continue;
                }
                let _ = player.set_number("volume", v.volume * 100.);
                let _ = player.set(
                    "mute",
                    if self.state.muted || v.is_muted {
                        "yes"
                    } else {
                        "no"
                    },
                );
                let _ = player.set_number("speed", v.rate);
                let _ = player.set("ab-loop-a", "no");
                let _ = player.set("ab-loop-b", "no");
                if let Err(e) = player.load(&v.uri, v.current_position as f64 / 1000., v.is_paused)
                {
                    self.runtime[i].error = e;
                }
                drop(player);
                self.set_loop(i);
            }
            let mut player = p.lock().unwrap();
            player.poll();
            if let Some(e) = &player.error {
                self.runtime[i].error = e.clone();
            }
            if player.loaded {
                self.runtime[i].duration = player.number("duration").unwrap_or(0.);
                if self.runtime[i].drag.is_none() {
                    self.runtime[i].time =
                        player.number("time-pos").unwrap_or(self.runtime[i].time);
                }
                self.runtime[i].source = vec2(
                    player.number("dwidth").unwrap_or(1920.) as f32,
                    player.number("dheight").unwrap_or(1080.) as f32,
                );
                if let Some(v) = &mut self.state.cells[i].video {
                    v.is_paused = player.flag("pause");
                }
            }
        }
    }
    fn toolbar(&mut self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal_wrapped(|ui| {
                ui.strong("MultipleVideoPlayer");
                ui.label(format!("{} Rust", env!("CARGO_PKG_VERSION")));
                ui.separator();
                if ui.button("開啟影片").clicked() {
                    self.pick(self.last_hover, false)
                }
                if ui.button("資料夾").clicked() {
                    self.pick(self.last_hover, true)
                }
                ui.separator();
                let mut cols = self.state.columns;
                egui::ComboBox::from_id_salt("columns")
                    .selected_text(format!("{cols} 欄"))
                    .show_ui(ui, |ui| {
                        for n in 2..=4 {
                            ui.selectable_value(&mut cols, n, format!("{n} 欄"));
                        }
                    });
                self.state.columns = cols;
                if ui
                    .add_enabled(self.state.cells.len() < 12, egui::Button::new("＋格"))
                    .clicked()
                {
                    self.state.cells.push(Cell::default());
                }
                if ui.checkbox(&mut self.state.muted, "全部靜音").changed() {
                    self.sync_audio();
                }
                ui.label("← → 秒");
                if ui
                    .add(
                        egui::DragValue::new(&mut self.seek_seconds)
                            .range(0.001..=86400.)
                            .speed(0.1)
                            .max_decimals(3),
                    )
                    .changed()
                {
                    self.save_settings();
                }
                if ui.checkbox(&mut self.state.borderless, "無邊框").changed() {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Decorations(
                        !self.state.borderless,
                    ));
                }
                if ui.checkbox(&mut self.state.fullscreen, "全螢幕").changed() {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Fullscreen(self.state.fullscreen));
                }
                if self.focus.is_some() && ui.button("返回網格 Esc").clicked() {
                    self.focus = None;
                }
                if self.state.borderless && ui.button("關閉").clicked() {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
            });
            ui.horizontal(|ui| {
                egui::ComboBox::from_id_salt("preset")
                    .selected_text(
                        self.presets
                            .iter()
                            .find(|p| p.0 == self.selected)
                            .map(|p| p.1.as_str())
                            .unwrap_or("選擇 preset"),
                    )
                    .show_ui(ui, |ui| {
                        for (k, n) in &self.presets {
                            ui.selectable_value(&mut self.selected, k.clone(), n);
                        }
                    });
                if ui.button("載入").clicked() {
                    self.load_preset();
                }
                if ui.button("另存 preset").clicked() {
                    self.save_dialog = true;
                    self.preset_name.clear();
                }
                if ui
                    .add_enabled(
                        self.selected != "last" && !self.selected.is_empty(),
                        egui::Button::new("更新 preset"),
                    )
                    .clicked()
                {
                    self.overwrite = true;
                }
                if !self.message.is_empty() {
                    ui.colored_label(Color32::LIGHT_RED, &self.message);
                    if ui.small_button("×").clicked() {
                        self.message.clear();
                    }
                }
            });
        });
    }
    fn sync_audio(&mut self) {
        for (i, c) in self.state.cells.iter().enumerate() {
            if let (Some(v), Some(p)) = (&c.video, &self.runtime[i].player) {
                let p = p.lock().unwrap();
                let _ = p.set_number("volume", v.volume * 100.);
                let _ = p.set(
                    "mute",
                    if self.state.muted || v.is_muted {
                        "yes"
                    } else {
                        "no"
                    },
                );
            }
        }
    }
    fn save_settings(&self) {
        let _ = std::fs::create_dir_all(&self.data);
        let _ = std::fs::write(
            self.data.join("workspace.ini"),
            format!("[workspace]\nseek_seconds={}\n", self.seek_seconds),
        );
    }
    fn cell_ui(&mut self, ui: &mut egui::Ui, i: usize, rect: Rect) {
        let hovered = ui.ctx().pointer_hover_pos().is_some_and(|p| {
            rect.contains(p)
                && ui.clip_rect().contains(p)
                && ui.ctx().layer_id_at(p) == Some(ui.layer_id())
        });
        if hovered {
            self.last_hover = i;
        }
        ui.painter().rect_filled(rect, 3., Color32::BLACK);
        ui.painter().rect_stroke(
            rect,
            3.,
            Stroke::new(
                1_f32,
                if hovered {
                    Color32::from_rgb(83, 166, 210)
                } else {
                    Color32::from_gray(50)
                },
            ),
            egui::StrokeKind::Inside,
        );
        let response = ui.interact(rect, ui.id().with((i, "video")), Sense::click_and_drag());
        let controls = hovered
            || self.runtime[i].drag.is_some()
            || self.runtime[i].popup_open
            || (self.last_hover == i && ui.memory(|m| m.any_popup_open()));
        let control_rect = Rect::from_min_max(
            pos2(rect.min.x + 4., rect.max.y - 108.),
            rect.max - vec2(4., 4.),
        );
        let c = &mut self.state.cells[i];
        if let Some(v) = &mut c.video {
            let source = self.runtime[i].source.max(vec2(1., 1.));
            let dpi = ui.ctx().pixels_per_point();
            let in_video = hovered
                && !control_rect.contains(ui.ctx().pointer_hover_pos().unwrap_or(Pos2::ZERO));
            if in_video {
                let wheel = ui.input(|s| {
                    s.events
                        .iter()
                        .filter_map(|e| match e {
                            egui::Event::MouseWheel { unit, delta, .. } => Some(
                                delta.y
                                    / if *unit == egui::MouseWheelUnit::Point {
                                        40.
                                    } else {
                                        1.
                                    },
                            ),
                            _ => None,
                        })
                        .sum::<f32>()
                });
                if wheel != 0. {
                    view::zoom(
                        rect,
                        source,
                        &v.aspect_mode,
                        &mut v.scale,
                        &mut c.view_center,
                        dpi,
                        ui.ctx().pointer_hover_pos().unwrap(),
                        1.1f32.powf(wheel),
                    );
                    ui.ctx().input_mut(|s| {
                        s.raw_scroll_delta = Vec2::ZERO;
                        s.smooth_scroll_delta = Vec2::ZERO;
                    });
                }
            }
            if response.dragged_by(egui::PointerButton::Middle) {
                let image = view::video_rect(
                    rect,
                    source,
                    &v.aspect_mode,
                    v.scale as f32,
                    c.view_center,
                    dpi,
                );
                let d = ui.input(|s| s.pointer.delta()) / image.size();
                c.view_center[0] -= d.x;
                c.view_center[1] -= d.y;
                view::clamp_center(
                    rect,
                    source,
                    &v.aspect_mode,
                    v.scale as f32,
                    &mut c.view_center,
                    dpi,
                );
            }
            let image_rect = view::video_rect(
                rect,
                source,
                &v.aspect_mode,
                v.scale as f32,
                c.view_center,
                dpi,
            );
            if let Some(p) = &self.runtime[i].player {
                let id = p.lock().unwrap().texture_id;
                if let Some(id) = id {
                    let p = p.clone();
                    let render_size =
                        (source * (image_rect.width() * dpi / source.x).min(1.)).max(vec2(1., 1.));
                    let painter = ui.painter().with_clip_rect(rect.intersect(ui.clip_rect()));
                    painter.add(egui::PaintCallback {
                        rect,
                        callback: Arc::new(egui_glow::CallbackFn::new(move |_, _| {
                            p.lock()
                                .unwrap()
                                .paint(render_size.x as i32, render_size.y as i32)
                        })),
                    });
                    painter.image(
                        id,
                        image_rect,
                        Rect::from_min_max(Pos2::ZERO, pos2(1., 1.)),
                        Color32::WHITE,
                    );
                }
            }
        } else {
            ui.painter().text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                format!("{}  拖入影片或資料夾", i + 1),
                egui::FontId::proportional(15.),
                Color32::GRAY,
            );
        }
        if !self.runtime[i].error.is_empty() {
            ui.painter().text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                &self.runtime[i].error,
                egui::FontId::proportional(13.),
                Color32::LIGHT_RED,
            );
        }
        if self.runtime[i].loading {
            ui.painter().text(
                rect.center(),
                egui::Align2::CENTER_CENTER,
                "正在讀取影片清單…",
                egui::FontId::proportional(14.),
                Color32::WHITE,
            );
        }
        if controls {
            ui.scope_builder(
                egui::UiBuilder::new()
                    .max_rect(control_rect)
                    .id_salt((i, "controls")),
                |ui| {
                    ui.set_clip_rect(control_rect.intersect(ui.clip_rect()));
                    ui.painter()
                        .rect_filled(control_rect, 3., Color32::from_black_alpha(225));
                    self.controls(ui, i);
                },
            );
        }
        response.context_menu(|ui| {
            if ui.button("開啟影片").clicked() {
                ui.close_menu();
                self.pick(i, false)
            }
            if ui.button("開啟資料夾").clicked() {
                ui.close_menu();
                self.pick(i, true)
            }
            ui.separator();
            for (r, c, label) in [
                (1, 1, "1 × 1"),
                (1, 2, "2 欄 × 1 列"),
                (2, 1, "1 欄 × 2 列"),
                (2, 2, "2 × 2"),
            ] {
                if ui.button(label).clicked() {
                    self.state.cells[i].rows = r;
                    self.state.cells[i].cols = c;
                    ui.close_menu();
                }
            }
            if ui.button("清空影片").clicked() {
                self.command(i, &["stop"]);
                self.state.cells[i].video = None;
                self.state.cells[i].playlist.clear();
                self.runtime[i].index_job = None;
                self.runtime[i].index.clear();
                self.runtime[i].key.clear();
                ui.close_menu();
            }
            if ui
                .add_enabled(self.state.cells.len() > 1, egui::Button::new("移除此格"))
                .clicked()
            {
                self.remove_cell = Some(i);
                ui.close_menu();
            }
        });
    }
    fn controls(&mut self, ui: &mut egui::Ui, i: usize) {
        self.runtime[i].popup_open = false;
        ui.spacing_mut().item_spacing = vec2(4., 2.);
        let has = self.state.cells[i].video.is_some();
        ui.horizontal(|ui| {
            if ui.small_button("◀|").on_hover_text("上一條影片").clicked() {
                self.next(i, -1);
            }
            let paused = self.state.cells[i]
                .video
                .as_ref()
                .is_none_or(|v| v.is_paused);
            if ui
                .add_enabled(has, egui::Button::new(if paused { "▶" } else { "Ⅱ" }))
                .clicked()
            {
                self.command(i, &["cycle", "pause"]);
            }
            let volume_button = ui.small_button("音量");
            let volume_id = egui::Id::new((i, "volume_popup"));
            if volume_button.clicked() {
                ui.memory_mut(|m| m.toggle_popup(volume_id));
            }
            let volume_menu = egui::popup_below_widget(
                ui,
                volume_id,
                &volume_button,
                egui::PopupCloseBehavior::CloseOnClickOutside,
                |ui| {
                    if let Some(v) = &mut self.state.cells[i].video {
                        let changed = ui
                            .add(egui::Slider::new(&mut v.volume, 0.0..=1.).show_value(false))
                            .changed()
                            | ui.checkbox(&mut v.is_muted, "靜音").changed();
                        let mut percent = v.volume * 100.;
                        let entered = ui
                            .add(
                                egui::DragValue::new(&mut percent)
                                    .range(0.0..=100.)
                                    .suffix("%")
                                    .max_decimals(0),
                            )
                            .changed();
                        if entered {
                            v.volume = percent / 100.;
                        }
                        if changed || entered {
                            self.sync_audio();
                        }
                    }
                },
            );
            self.runtime[i].popup_open |= volume_menu.is_some();
            if ui.small_button("|▶").on_hover_text("下一條影片").clicked() {
                self.next(i, 1);
            }
            if ui.max_rect().width() < 340. {
                let extra_button = ui.small_button("更多");
                let extra_id = egui::Id::new((i, "extra_popup"));
                if extra_button.clicked() {
                    ui.memory_mut(|m| m.toggle_popup(extra_id));
                }
                let extra_menu = egui::popup_below_widget(
                    ui,
                    extra_id,
                    &extra_button,
                    egui::PopupCloseBehavior::CloseOnClickOutside,
                    |ui| {
                        self.extra_controls(ui, i, has, paused);
                    },
                );
                self.runtime[i].popup_open |= extra_menu.is_some();
            } else {
                self.extra_controls(ui, i, has, paused);
            }
        });
        self.timeline(ui, i);
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 3.;
            ui.label(
                egui::RichText::new(format!(
                    "{} / {}",
                    short_time(self.runtime[i].time),
                    short_time(self.runtime[i].duration)
                ))
                .size(11.),
            )
            .on_hover_text(format!(
                "{} / {}",
                model::time(self.runtime[i].time),
                model::time(self.runtime[i].duration)
            ));
            let (a, b) = self.state.cells[i]
                .video
                .as_ref()
                .map(|v| (v.loop_start, v.loop_end))
                .unwrap_or_default();
            if ui
                .small_button("A")
                .on_hover_text("以目前時間設定 A")
                .clicked()
            {
                if let Some(v) = &mut self.state.cells[i].video {
                    let ms = (self.runtime[i].time * 1000.).round() as i64;
                    v.loop_start = Some(ms);
                    if v.loop_end.is_some_and(|b| b <= ms) {
                        v.loop_end = None;
                    }
                }
                self.set_loop(i);
            }
            if ui
                .small_button("B")
                .on_hover_text("以目前時間設定 B")
                .clicked()
            {
                if let Some(v) = &mut self.state.cells[i].video {
                    let ms = (self.runtime[i].time * 1000.).round() as i64;
                    if v.loop_start.is_none_or(|a| ms > a) {
                        v.loop_end = Some(ms);
                    }
                }
                self.set_loop(i);
            }
            let label = if ui.max_rect().width() < 320. {
                "AB".into()
            } else if let (Some(a), Some(b)) = (a, b) {
                format!("{:.2}–{:.2}", a as f64 / 1000., b as f64 / 1000.)
            } else {
                "AB 編輯".into()
            };
            if ui
                .small_button(label)
                .on_hover_text(format!(
                    "A {}\nB {}\n區間 {:.3} 秒；點擊輸入時間",
                    a.map(|a| model::time(a as f64 / 1000.))
                        .unwrap_or("未設定".into()),
                    b.map(|b| model::time(b as f64 / 1000.))
                        .unwrap_or("未設定".into()),
                    (b.unwrap_or(0) - a.unwrap_or(0)).max(0) as f64 / 1000.
                ))
                .clicked()
            {
                self.ab_edit = Some((
                    i,
                    a.unwrap_or(0) as f64 / 1000.,
                    b.map(|v| v as f64 / 1000.)
                        .unwrap_or(self.runtime[i].duration),
                ));
            }
            if ui
                .small_button("回A")
                .on_hover_text("Back to looping：回到 A，恢復循環並保留暫停狀態")
                .clicked()
            {
                if let Some((a, _)) = self.state.cells[i].video.as_ref().and_then(Video::interval) {
                    self.seek(i, a);
                }
            }
            if ui.small_button("×AB").clicked() {
                if let Some(v) = &mut self.state.cells[i].video {
                    v.loop_start = None;
                    v.loop_end = None;
                }
                self.state.cells[i].loop_suspended = false;
                self.set_loop(i);
            }
        });
        ui.horizontal(|ui| {
            if let Some(v) = &self.state.cells[i].video {
                ui.label(format!("{:.2}×", v.scale));
            }
            if ui.small_button("重置視圖").clicked() {
                self.reset_view(i);
            }
            if self.runtime[i].index_job.is_some() {
                ui.spinner();
                ui.label("建立影格索引…");
            }
            if self.state.cells[i].loop_suspended {
                ui.colored_label(Color32::YELLOW, "循環暫停");
            }
            if let Some(v) = &self.state.cells[i].video {
                ui.add(
                    egui::Label::new(
                        Path::new(&v.uri)
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy(),
                    )
                    .truncate(),
                )
                .on_hover_text(&v.uri);
            }
        });
    }
    fn extra_controls(&mut self, ui: &mut egui::Ui, i: usize, has: bool, paused: bool) {
        if ui
            .add_enabled(has && paused, egui::Button::new("‹格"))
            .clicked()
        {
            self.step_frame(i, -1);
        }
        if ui
            .add_enabled(has && paused, egui::Button::new("格›"))
            .clicked()
        {
            self.step_frame(i, 1);
        }
        if ui
            .small_button(if self.focus == Some(i) {
                "還原"
            } else {
                "放大格"
            })
            .clicked()
        {
            self.focus = if self.focus == Some(i) { None } else { Some(i) };
        }
        if let Some(v) = &mut self.state.cells[i].video {
            let old = v.aspect_mode.clone();
            let mode_menu = egui::ComboBox::from_id_salt((i, "mode"))
                .width(65.)
                .selected_text(mode_label(&v.aspect_mode))
                .show_ui(ui, |ui| {
                    for (m, l) in [
                        ("none", "Fit"),
                        ("fit", "Fill"),
                        ("width", "符合寬"),
                        ("height", "符合高"),
                        ("stretch", "Stretch"),
                        ("original", "原始 1:1"),
                    ] {
                        ui.selectable_value(&mut v.aspect_mode, m.into(), l);
                    }
                });
            self.runtime[i].popup_open |= mode_menu.inner.is_some();
            if old != v.aspect_mode {
                self.reset_view(i);
            }
        }
    }
    fn timeline(&mut self, ui: &mut egui::Ui, i: usize) {
        let (rect, response) =
            ui.allocate_exact_size(vec2(ui.available_width(), 28.), Sense::click_and_drag());
        let duration = self.runtime[i].duration;
        if duration <= 0. {
            return;
        }
        let left = rect.left() + 5.;
        let width = (rect.width() - 10.).max(1.);
        let x = |t: f64| left + (t / duration).clamp(0., 1.) as f32 * width;
        let y = rect.center().y;
        let p = ui.painter();
        p.line_segment(
            [pos2(left, y), pos2(left + width, y)],
            Stroke::new(4_f32, Color32::from_gray(70)),
        );
        let (a, b) = self.state.cells[i]
            .video
            .as_ref()
            .map(|v| {
                (
                    v.loop_start.map(|v| v as f64 / 1000.),
                    v.loop_end.map(|v| v as f64 / 1000.),
                )
            })
            .unwrap_or_default();
        if let (Some(a), Some(b)) = (a, b) {
            p.line_segment(
                [pos2(x(a), y), pos2(x(b), y)],
                Stroke::new(
                    4_f32,
                    if self.state.cells[i].loop_suspended {
                        Color32::GOLD
                    } else {
                        Color32::from_rgb(45, 150, 130)
                    },
                ),
            );
        }
        for (t, label, dy, color) in [
            (a, "A", -9., Color32::LIGHT_GREEN),
            (b, "B", 9., Color32::LIGHT_BLUE),
        ] {
            if let Some(t) = t {
                p.line_segment(
                    [pos2(x(t), y - 5.), pos2(x(t), y + 5.)],
                    Stroke::new(2_f32, color),
                );
                p.text(
                    pos2(x(t), y + dy),
                    egui::Align2::CENTER_CENTER,
                    label,
                    egui::FontId::proportional(10.),
                    color,
                );
            }
        }
        p.circle_filled(pos2(x(self.runtime[i].time), y), 5., Color32::WHITE);
        if response.hovered() {
            if let Some(pos) = response.hover_pos() {
                response.clone().on_hover_text(model::time(
                    ((pos.x - left) / width).clamp(0., 1.) as f64 * duration,
                ));
            }
        }
        let press = ui.input(|s| {
            s.events.iter().find_map(|e| match e {
                egui::Event::PointerButton {
                    pos,
                    button: egui::PointerButton::Primary,
                    pressed: true,
                    ..
                } => Some(*pos),
                _ => None,
            })
        });
        if let Some(pos) = press.filter(|pos| {
            rect.contains(*pos)
                && ui.clip_rect().contains(*pos)
                && ui.ctx().layer_id_at(*pos) == Some(ui.layer_id())
        }) {
            self.runtime[i].drag = Some(
                if pos.y < y - 3. && a.is_some_and(|a| (pos.x - x(a)).abs() < 11.) {
                    1
                } else if pos.y > y + 3. && b.is_some_and(|b| (pos.x - x(b)).abs() < 11.) {
                    2
                } else {
                    0
                },
            );
        }
        if self.runtime[i].drag.is_some() {
            if let Some(pos) = ui.input(|s| s.pointer.latest_pos()) {
                let t = ((pos.x - left) / width).clamp(0., 1.) as f64 * duration;
                match self.runtime[i].drag.unwrap_or(0) {
                    1 => {
                        if let Some(v) = &mut self.state.cells[i].video {
                            v.loop_start = Some(
                                (t.min(b.unwrap_or(duration) - 0.001).max(0.) * 1000.).round()
                                    as i64,
                            );
                        }
                        self.set_loop(i);
                    }
                    2 => {
                        if let Some(v) = &mut self.state.cells[i].video {
                            v.loop_end = Some(
                                (t.max(a.unwrap_or(0.) + 0.001).min(duration) * 1000.).round()
                                    as i64,
                            );
                        }
                        self.set_loop(i);
                    }
                    _ => self.seek(i, t),
                }
            }
        }
        if ui.input(|s| {
            s.pointer.button_released(egui::PointerButton::Primary)
                || !s.pointer.button_down(egui::PointerButton::Primary)
        }) {
            self.runtime[i].drag = None;
        }
    }
    fn dialogs(&mut self, ctx: &egui::Context) {
        if self.save_dialog {
            let mut open = true;
            egui::Window::new("另存 preset")
                .collapsible(false)
                .open(&mut open)
                .show(ctx, |ui| {
                    ui.text_edit_singleline(&mut self.preset_name);
                    if ui.button("保存").clicked() {
                        let name = self.preset_name.trim().to_string();
                        if self.presets.iter().any(|(_, n)| n == &name) {
                            self.message = "已存在同名 preset，請改名或使用更新。".into();
                        } else {
                            self.save(uuid::Uuid::new_v4().simple().to_string(), name);
                            self.save_dialog = false;
                        }
                    }
                });
            if !open {
                self.save_dialog = false
            }
        }
        if self.overwrite {
            egui::Window::new("確認更新 preset")
                .collapsible(false)
                .show(ctx, |ui| {
                    let name = self
                        .presets
                        .iter()
                        .find(|p| p.0 == self.selected)
                        .map(|p| p.1.clone())
                        .unwrap_or_default();
                    ui.label(format!("以目前工作區覆寫「{name}」？"));
                    if ui.button("確認更新").clicked() {
                        self.save(self.selected.clone(), name);
                        self.overwrite = false;
                    }
                    if ui.button("取消").clicked() {
                        self.overwrite = false;
                    }
                });
        }
        if let Some((i, mut a, mut b)) = self.ab_edit {
            let mut open = true;
            let mut apply = false;
            egui::Window::new("輸入 A／B 時間（秒）")
                .open(&mut open)
                .show(ctx, |ui| {
                    ui.horizontal(|ui| {
                        ui.label("A");
                        ui.add(
                            egui::DragValue::new(&mut a)
                                .speed(0.01)
                                .max_decimals(3)
                                .range(0.0..=self.runtime[i].duration),
                        );
                        ui.label("B");
                        ui.add(
                            egui::DragValue::new(&mut b)
                                .speed(0.01)
                                .max_decimals(3)
                                .range(0.0..=self.runtime[i].duration),
                        );
                    });
                    ui.label(format!("區間長度：{:.3} 秒", b - a));
                    apply = ui.add_enabled(b > a, egui::Button::new("套用")).clicked();
                });
            if apply {
                if let Some(v) = &mut self.state.cells[i].video {
                    v.loop_start = Some((a * 1000.).round() as i64);
                    v.loop_end = Some((b * 1000.).round() as i64);
                }
                self.state.cells[i].loop_suspended = false;
                self.set_loop(i);
                self.ab_edit = None;
            } else {
                self.ab_edit = if open { Some((i, a, b)) } else { None };
            }
        }
    }
}
impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        if self.restore_window {
            self.restore_window = false;
            let g = self.state.geometry;
            ctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(vec2(
                g[2].max(720) as f32,
                g[3].max(420) as f32,
            )));
            ctx.send_viewport_cmd(egui::ViewportCommand::OuterPosition(pos2(
                g[0] as f32,
                g[1] as f32,
            )));
            ctx.send_viewport_cmd(egui::ViewportCommand::Decorations(!self.state.borderless));
            ctx.send_viewport_cmd(egui::ViewportCommand::Fullscreen(self.state.fullscreen));
        }
        self.apply_scans();
        self.poll_indexes();
        self.update_players(frame);
        for r in &self.runtime {
            if let Some(p) = &r.player {
                p.lock().unwrap().refresh_hidden();
            }
        }
        if !self.first_video
            && self.runtime.iter().any(|r| {
                r.player
                    .as_ref()
                    .is_some_and(|p| p.lock().unwrap().has_frame)
            })
        {
            self.first_video = true;
            if let Some(path) = std::env::var_os("MVP_METRICS_PATH") {
                use std::io::Write;
                if let Ok(mut f) = std::fs::OpenOptions::new().append(true).open(path) {
                    let _ = writeln!(f, "first_frame_ms={}", self.started.elapsed().as_millis());
                }
            }
        }
        if !ctx.wants_keyboard_input() {
            let i = self.last_hover.min(self.state.cells.len() - 1);
            if ctx.input(|s| s.key_pressed(egui::Key::ArrowLeft)) {
                self.seek(i, self.runtime[i].time - self.seek_seconds);
            }
            if ctx.input(|s| s.key_pressed(egui::Key::ArrowRight)) {
                self.seek(i, self.runtime[i].time + self.seek_seconds);
            }
            if ctx.input(|s| s.key_pressed(egui::Key::F11)) {
                self.state.fullscreen = !self.state.fullscreen;
                ctx.send_viewport_cmd(egui::ViewportCommand::Fullscreen(self.state.fullscreen));
            }
            if ctx.input(|s| s.key_pressed(egui::Key::Escape)) {
                if self.focus.is_some() {
                    self.focus = None;
                } else {
                    self.state.fullscreen = false;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Fullscreen(false));
                }
            }
        }
        self.toolbar(ctx);
        egui::CentralPanel::default()
            .frame(egui::Frame::NONE.inner_margin(4.))
            .show(ctx, |ui| {
                let available = ui.available_size();
                if let Some(i) = self.focus {
                    let rect = ui.available_rect_before_wrap();
                    self.cell_ui(ui, i, rect);
                } else {
                    egui::ScrollArea::vertical()
                        .drag_to_scroll(false)
                        .show(ui, |ui| {
                            let placements = self.state.placement();
                            let cols = self.state.columns;
                            let rows = placements
                                .iter()
                                .map(|(r, _, h, _)| r + h)
                                .max()
                                .unwrap_or(2);
                            let width = (available.x - 8. * (cols - 1) as f32) / cols as f32;
                            let height = ((available.y - 8.) / 2.).max(160.);
                            let origin = ui.cursor().min;
                            ui.allocate_space(vec2(available.x, rows as f32 * (height + 8.) - 8.));
                            for (i, (r, c, h, w)) in placements.into_iter().enumerate() {
                                let rect = Rect::from_min_size(
                                    origin
                                        + vec2(c as f32 * (width + 8.), r as f32 * (height + 8.)),
                                    vec2(
                                        w as f32 * (width + 8.) - 8.,
                                        h as f32 * (height + 8.) - 8.,
                                    ),
                                );
                                self.cell_ui(ui, i, rect);
                            }
                        });
                }
            });
        if let Some(i) = self.remove_cell.take() {
            self.command(i, &["stop"]);
            self.state.cells.remove(i);
            let mut r = self.runtime.remove(i);
            r.index_job = None;
            r.pending_step = None;
            r.index.clear();
            r.key.clear();
            r.error.clear();
            self.runtime.push(r);
            self.focus = None;
            self.last_hover = self.last_hover.min(self.state.cells.len() - 1);
        }
        let files = ctx.input(|s| {
            s.raw
                .dropped_files
                .iter()
                .filter_map(|f| f.path.clone())
                .collect::<Vec<_>>()
        });
        if !files.is_empty() {
            self.open_paths(self.last_hover, files);
        }
        self.dialogs(ctx);
        if let Err(e) = &self.api {
            self.message = e.clone();
        }
        if !self.state.fullscreen {
            ctx.input(|s| {
                if let Some(r) = s.viewport().outer_rect {
                    self.state.geometry[0] = r.min.x.round() as i32;
                    self.state.geometry[1] = r.min.y.round() as i32;
                }
                if let Some(r) = s.viewport().inner_rect {
                    self.state.geometry[2] = r.width().round() as i32;
                    self.state.geometry[3] = r.height().round() as i32;
                }
            });
        }
        if !self.first_paint {
            self.first_paint = true;
            eprintln!("window_ready_ms={}", self.started.elapsed().as_millis());
            if let Some(path) = std::env::var_os("MVP_METRICS_PATH") {
                let _ = std::fs::write(
                    path,
                    format!("window_ready_ms={}\n", self.started.elapsed().as_millis()),
                );
            }
        }
        ctx.request_repaint_after(Duration::from_millis(16));
        if let Ok(ms) = std::env::var("MVP_AUTO_CLOSE_MS") {
            if let Ok(ms) = ms.parse::<u128>() {
                if self.started.elapsed().as_millis() > ms {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
            }
        }
    }
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        let state = self.snapshot();
        if self.save_last {
            if let Err(e) = model::save_preset(&self.data.join("presets"), "last", "上一次", &state)
            {
                let _ = std::fs::write(self.data.join("save-error.log"), e);
            }
        }
        self.save_settings();
        for r in &mut self.runtime {
            r.index_job = None;
            r.player = None;
        }
    }
}
fn mode_label(mode: &str) -> &str {
    match mode {
        "fit" => "Fill",
        "width" => "符合寬",
        "height" => "符合高",
        "stretch" => "Stretch",
        "original" => "原始 1:1",
        _ => "Fit",
    }
}
fn short_time(t: f64) -> String {
    let s = t.max(0.) as u64;
    format!("{}:{:02}", s / 60, s % 60)
}
