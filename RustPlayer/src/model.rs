use serde::{Deserialize, Serialize};
use std::{
    cmp::Ordering,
    collections::{BTreeMap, HashSet},
    fs,
    io::Write,
    path::{Path, PathBuf},
};

fn id() -> String {
    uuid::Uuid::new_v4().simple().to_string()
}
fn one() -> f64 {
    1.0
}
fn fit() -> String {
    "none".into()
}
fn center() -> [f32; 2] {
    [0.5, 0.5]
}
fn span() -> usize {
    1
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Video {
    #[serde(default = "id")]
    pub id: String,
    pub uri: String,
    #[serde(default)]
    pub current_position: i64,
    #[serde(default)]
    pub loop_start: Option<i64>,
    #[serde(default)]
    pub loop_end: Option<i64>,
    #[serde(default = "fit")]
    pub aspect_mode: String,
    #[serde(default = "one")]
    pub scale: f64,
    #[serde(default = "one")]
    pub volume: f64,
    #[serde(default = "one")]
    pub rate: f64,
    #[serde(default)]
    pub is_muted: bool,
    #[serde(default)]
    pub is_paused: bool,
    #[serde(flatten)]
    pub extra: BTreeMap<String, serde_json::Value>,
}
impl Video {
    pub fn new(path: &Path) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            uri: path.to_string_lossy().into(),
            current_position: 0,
            loop_start: None,
            loop_end: None,
            aspect_mode: fit(),
            scale: 1.,
            volume: 1.,
            rate: 1.,
            is_muted: false,
            is_paused: false,
            extra: BTreeMap::new(),
        }
    }
    pub fn interval(&self) -> Option<(f64, f64)> {
        match (self.loop_start, self.loop_end) {
            (Some(a), Some(b)) if a >= 0 && b > a => Some((a as f64 / 1000., b as f64 / 1000.)),
            _ => None,
        }
    }
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Cell {
    #[serde(default = "id")]
    pub id: String,
    #[serde(default = "span")]
    pub rows: usize,
    #[serde(default = "span")]
    pub cols: usize,
    #[serde(default)]
    pub video: Option<Video>,
    #[serde(default)]
    pub playlist: Vec<String>,
    #[serde(default)]
    pub source_folder: Option<String>,
    #[serde(default)]
    pub loop_suspended: bool,
    #[serde(default = "center")]
    pub view_center: [f32; 2],
}
impl Default for Cell {
    fn default() -> Self {
        Self {
            id: id(),
            rows: 1,
            cols: 1,
            video: None,
            playlist: vec![],
            source_folder: None,
            loop_suspended: false,
            view_center: center(),
        }
    }
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub version: u32,
    pub cells: Vec<Cell>,
    pub columns: usize,
    pub geometry: [i32; 4],
    pub borderless: bool,
    pub fullscreen: bool,
    pub muted: bool,
}
impl Default for Workspace {
    fn default() -> Self {
        Self {
            version: 1,
            cells: (0..6).map(|_| Cell::default()).collect(),
            columns: 3,
            geometry: [80, 80, 1280, 800],
            borderless: false,
            fullscreen: false,
            muted: false,
        }
    }
}
impl Workspace {
    pub fn validate(&self) -> Result<(), String> {
        if self.version != 1
            || !(1..=12).contains(&self.cells.len())
            || !(2..=4).contains(&self.columns)
        {
            return Err("不支援的工作區版本或格數".into());
        }
        let mut ids = HashSet::new();
        for c in &self.cells {
            if !ids.insert(&c.id)
                || !(1..=2).contains(&c.rows)
                || !(1..=2).contains(&c.cols)
                || c.view_center
                    .iter()
                    .any(|x| !x.is_finite() || !(0.0..=1.0).contains(x))
            {
                return Err("格子資料無效".into());
            }
            if let Some(v) = &c.video {
                if !v.scale.is_finite()
                    || !(1.0..=10.0).contains(&v.scale)
                    || !v.volume.is_finite()
                    || !(0.0..=1.0).contains(&v.volume)
                    || !["fit", "none", "width", "height", "stretch", "original"]
                        .contains(&v.aspect_mode.as_str())
                {
                    return Err("影片顯示或音量資料無效".into());
                }
            }
        }
        Ok(())
    }
    pub fn placement(&self) -> Vec<(usize, usize, usize, usize)> {
        let mut used = HashSet::new();
        let mut out = vec![];
        for c in &self.cells {
            'place: for r in 0..24 {
                for col in 0..=self.columns - c.cols {
                    let area: Vec<_> = (r..r + c.rows)
                        .flat_map(|y| (col..col + c.cols).map(move |x| (y, x)))
                        .collect();
                    if area.iter().all(|p| !used.contains(p)) {
                        used.extend(area);
                        out.push((r, col, c.rows, c.cols));
                        break 'place;
                    }
                }
            }
        }
        out
    }
}
#[derive(Serialize, Deserialize)]
pub struct Preset {
    pub name: String,
    pub state: Workspace,
}
pub fn read_preset(path: &Path) -> Result<Preset, String> {
    let p: Preset = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    p.state.validate()?;
    Ok(p)
}
pub fn save_preset(dir: &Path, key: &str, name: &str, state: &Workspace) -> Result<(), String> {
    state.validate()?;
    if key != "last" && (key.len() != 32 || !key.bytes().all(|b| b.is_ascii_hexdigit())) {
        return Err("無效 preset 識別".into());
    }
    if name.trim().is_empty()
        || name.chars().count() > 100
        || ((name == "上一次") != (key == "last"))
    {
        return Err("名稱需為 1–100 字；「上一次」為保留名稱".into());
    }
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let tmp = dir.join(format!(".saving-{}", id()));
    let dst = dir.join(format!("{key}.json"));
    let result = (|| {
        let data = serde_json::to_vec_pretty(&Preset {
            name: name.trim().into(),
            state: state.clone(),
        })
        .map_err(|e| e.to_string())?;
        let mut f = fs::File::create(&tmp).map_err(|e| e.to_string())?;
        f.write_all(&data)
            .and_then(|_| f.sync_all())
            .map_err(|e| e.to_string())?;
        drop(f);
        // MoveFileExW provides replacement on Windows without deleting the previous snapshot first.
        #[cfg(windows)]
        {
            use std::os::windows::ffi::OsStrExt;
            unsafe extern "system" {
                fn MoveFileExW(a: *const u16, b: *const u16, flags: u32) -> i32;
            }
            let a: Vec<_> = tmp.as_os_str().encode_wide().chain(Some(0)).collect();
            let b: Vec<_> = dst.as_os_str().encode_wide().chain(Some(0)).collect();
            if unsafe { MoveFileExW(a.as_ptr(), b.as_ptr(), 9) } == 0 {
                return Err(std::io::Error::last_os_error().to_string());
            }
        }
        #[cfg(not(windows))]
        fs::rename(&tmp, &dst).map_err(|e| e.to_string())?;
        Ok(())
    })();
    let _ = fs::remove_file(tmp);
    result
}
pub fn natural_cmp(a: &str, b: &str) -> Ordering {
    let a = a.to_lowercase();
    let b = b.to_lowercase();
    let mut x = a.as_str();
    let mut y = b.as_str();
    while !x.is_empty() && !y.is_empty() {
        let xd = x.as_bytes()[0].is_ascii_digit();
        let yd = y.as_bytes()[0].is_ascii_digit();
        if xd && yd {
            let nx = x.bytes().take_while(u8::is_ascii_digit).count();
            let ny = y.bytes().take_while(u8::is_ascii_digit).count();
            let xx = x[..nx].trim_start_matches('0');
            let yy = y[..ny].trim_start_matches('0');
            let cmp = xx.len().cmp(&yy.len()).then_with(|| xx.cmp(yy));
            if cmp != Ordering::Equal {
                return cmp;
            }
            x = &x[nx..];
            y = &y[ny..];
        } else {
            let xc = x.chars().next().unwrap();
            let yc = y.chars().next().unwrap();
            let cmp = xc.cmp(&yc);
            if cmp != Ordering::Equal {
                return cmp;
            }
            x = &x[xc.len_utf8()..];
            y = &y[yc.len_utf8()..];
        }
    }
    x.len().cmp(&y.len()).then_with(|| a.cmp(&b))
}
pub fn is_video(p: &Path) -> bool {
    p.extension().and_then(|s| s.to_str()).is_some_and(|s| {
        [
            "3g2", "3gp", "3gp2", "3gpp", "amv", "asf", "avi", "bik", "crf", "divx", "drc", "dv",
            "dvr-ms", "evo", "f4v", "flv", "gvi", "gxf", "h265", "hevc", "iso", "m1v", "m2v",
            "m2t", "m2ts", "m4v", "mkv", "mov", "mp2", "mp2v", "mp4", "mp4v", "mpe", "mpeg",
            "mpeg1", "mpeg2", "mpeg4", "mpg", "mpv2", "mts", "mtv", "mxf", "nsv", "nuv", "ogg",
            "ogm", "ogv", "ogx", "ps", "rec", "rm", "rmvb", "rpl", "thp", "tod", "ts", "tts",
            "txd", "vob", "vro", "webm", "wm", "wmv", "wtv", "xesc",
        ]
        .contains(&s.to_lowercase().as_str())
    })
}
pub fn scan(root: &Path, recursive: bool) -> Result<Vec<PathBuf>, String> {
    fn visit(p: &Path, recurse: bool, out: &mut Vec<PathBuf>) -> Result<(), String> {
        for e in fs::read_dir(p).map_err(|e| e.to_string())? {
            let e = e.map_err(|e| e.to_string())?;
            let m = e.metadata().map_err(|e| e.to_string())?;
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if m.file_attributes() & 0x400 != 0 {
                    continue;
                }
            }
            if e.file_type().map_err(|e| e.to_string())?.is_symlink() {
                continue;
            }
            if m.is_dir() && recurse {
                visit(&e.path(), true, out)?
            } else if m.is_file() && is_video(&e.path()) {
                out.push(e.path())
            }
        }
        Ok(())
    }
    let mut out = vec![];
    visit(root, recursive, &mut out)?;
    out.sort_by(|a, b| {
        natural_cmp(
            &a.strip_prefix(root)
                .unwrap_or(a)
                .to_string_lossy()
                .replace('\\', "/"),
            &b.strip_prefix(root)
                .unwrap_or(b)
                .to_string_lossy()
                .replace('\\', "/"),
        )
        .then_with(|| a.cmp(b))
    });
    Ok(out)
}
pub fn time(t: f64) -> String {
    let ms = (t.max(0.) * 1000.).round() as u64;
    format!(
        "{:02}:{:02}:{:02}.{:03}",
        ms / 3600000,
        ms / 60000 % 60,
        ms / 1000 % 60,
        ms % 1000
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn atomic_preset_and_invalid_data() {
        let dir = std::env::temp_dir().join(format!("mvp-test-{}", id()));
        let mut w = Workspace::default();
        let mut v = Video::new(Path::new("C:/missing.mp4"));
        v.loop_start = Some(1234);
        v.loop_end = Some(5678);
        v.scale = 2.5;
        v.volume = 0.23;
        w.cells[0].video = Some(v);
        w.cells[0].view_center = [0.4, 0.7];
        save_preset(&dir, "last", "上一次", &w).unwrap();
        let restored = read_preset(&dir.join("last.json")).unwrap();
        assert_eq!(restored.state.cells[0].view_center, [0.4, 0.7]);
        assert_eq!(restored.state.cells[0].video.as_ref().unwrap().volume, 0.23);
        let original = fs::read(dir.join("last.json")).unwrap();
        w.cells[1].id = w.cells[0].id.clone();
        assert!(save_preset(&dir, "last", "上一次", &w).is_err());
        assert_eq!(fs::read(dir.join("last.json")).unwrap(), original);
        assert!(save_preset(&dir, "../outside", "bad", &Workspace::default()).is_err());
        let _ = fs::remove_file(dir.join("last.json"));
        let _ = fs::remove_dir(dir);
    }
    #[test]
    fn recursive_natural_playlist() {
        let dir = std::env::temp_dir().join(format!("mvp-test-{}", id()));
        fs::create_dir_all(dir.join("sub")).unwrap();
        for p in [
            "clip10.mp4",
            "clip2.mp4",
            "clip1.mp4",
            "ignore.txt",
            "sub/clip3.mkv",
        ] {
            fs::write(dir.join(p), b"").unwrap();
        }
        let all = scan(&dir, true).unwrap();
        assert_eq!(all.len(), 4);
        assert_eq!(all[0].file_name().unwrap(), "clip1.mp4");
        assert_eq!(all[1].file_name().unwrap(), "clip2.mp4");
        assert_eq!(scan(&dir, false).unwrap().len(), 3);
        for p in [
            "clip10.mp4",
            "clip2.mp4",
            "clip1.mp4",
            "ignore.txt",
            "sub/clip3.mkv",
        ] {
            fs::remove_file(dir.join(p)).unwrap();
        }
        fs::remove_dir(dir.join("sub")).unwrap();
        fs::remove_dir(dir).unwrap();
    }
    #[test]
    fn natural_paths() {
        let mut a = vec!["a/clip10.mp4", "a/clip2.mp4", "a/clip1.mp4"];
        a.sort_by(|a, b| natural_cmp(a, b));
        assert_eq!(a, vec!["a/clip1.mp4", "a/clip2.mp4", "a/clip10.mp4"]);
        assert_eq!(
            natural_cmp("9999999999999999999999", "10000000000000000000000"),
            Ordering::Less
        );
    }
    #[test]
    fn spans_never_overlap() {
        let mut w = Workspace::default();
        w.cells[0].rows = 2;
        w.cells[0].cols = 2;
        let mut seen = HashSet::new();
        for (r, c, h, s) in w.placement() {
            for y in r..r + h {
                for x in c..c + s {
                    assert!(seen.insert((y, x)))
                }
            }
        }
    }
    #[test]
    fn legacy_unknown_fields_survive() {
        let mut w = Workspace::default();
        let mut v = Video::new(Path::new("C:\\sample.mp4"));
        v.extra.insert("transform".into(), "none".into());
        w.cells[0].video = Some(v);
        let restored: Workspace =
            serde_json::from_str(&serde_json::to_string(&w).unwrap()).unwrap();
        restored.validate().unwrap();
        assert_eq!(
            restored.cells[0].video.as_ref().unwrap().extra["transform"],
            "none"
        );
    }
}
