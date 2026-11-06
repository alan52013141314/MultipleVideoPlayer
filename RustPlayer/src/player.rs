//! Minimal dynamically loaded libmpv API. All render operations stay on the GUI GL thread.
use eframe::glow::{self, HasContext};
use std::{
    ffi::{c_char, c_int, c_void, CStr, CString},
    path::Path,
    ptr,
    sync::Arc,
};
type Handle = *mut c_void;
unsafe extern "C" fn render_changed(ctx: *mut c_void) {
    unsafe {
        (*(ctx as *const std::sync::atomic::AtomicBool))
            .store(true, std::sync::atomic::Ordering::Release);
    }
}
#[repr(C)]
struct Param {
    kind: c_int,
    data: *mut c_void,
}
#[repr(C)]
struct GlInit {
    get: unsafe extern "C" fn(*mut c_void, *const c_char) -> *mut c_void,
    ctx: *mut c_void,
}
#[repr(C)]
struct Fbo {
    fbo: c_int,
    w: c_int,
    h: c_int,
    format: c_int,
}
#[repr(C)]
struct Event {
    id: c_int,
    error: c_int,
    userdata: u64,
    data: *mut c_void,
}
#[repr(C)]
struct Property {
    name: *const c_char,
    format: c_int,
    data: *mut c_void,
}
pub struct Api {
    _lib: libloading::Library,
    create: unsafe extern "C" fn() -> Handle,
    init: unsafe extern "C" fn(Handle) -> c_int,
    destroy: unsafe extern "C" fn(Handle),
    option: unsafe extern "C" fn(Handle, *const c_char, *const c_char) -> c_int,
    command: unsafe extern "C" fn(Handle, u64, *const *const c_char) -> c_int,
    observe: unsafe extern "C" fn(Handle, u64, *const c_char, c_int) -> c_int,
    set: unsafe extern "C" fn(Handle, u64, *const c_char, c_int, *mut c_void) -> c_int,
    wait: unsafe extern "C" fn(Handle, f64) -> *const Event,
    error: unsafe extern "C" fn(c_int) -> *const c_char,
    render_create: unsafe extern "C" fn(*mut Handle, Handle, *mut Param) -> c_int,
    render: unsafe extern "C" fn(Handle, *mut Param) -> c_int,
    render_free: unsafe extern "C" fn(Handle),
    render_update: unsafe extern "C" fn(Handle) -> u64,
    render_callback:
        unsafe extern "C" fn(Handle, Option<unsafe extern "C" fn(*mut c_void)>, *mut c_void),
}
impl Api {
    pub fn load(path: &Path) -> Result<Arc<Self>, String> {
        unsafe {
            let l: libloading::Library = libloading::os::windows::Library::load_with_flags(
                path,
                libloading::os::windows::LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
                    | libloading::os::windows::LOAD_LIBRARY_SEARCH_DEFAULT_DIRS,
            )
            .map(Into::into)
            .map_err(|e| format!("無法載入 {}：{e}", path.display()))?;
            macro_rules! f {
                ($n:literal) => {
                    *l.get(concat!($n, "\0").as_bytes())
                        .map_err(|e| e.to_string())?
                };
            }
            Ok(Arc::new(Self {
                create: f!("mpv_create"),
                init: f!("mpv_initialize"),
                destroy: f!("mpv_terminate_destroy"),
                option: f!("mpv_set_option_string"),
                command: f!("mpv_command_async"),
                observe: f!("mpv_observe_property"),
                set: f!("mpv_set_property_async"),
                wait: f!("mpv_wait_event"),
                error: f!("mpv_error_string"),
                render_create: f!("mpv_render_context_create"),
                render: f!("mpv_render_context_render"),
                render_free: f!("mpv_render_context_free"),
                render_update: f!("mpv_render_context_update"),
                render_callback: f!("mpv_render_context_set_update_callback"),
                _lib: l,
            }))
        }
    }
    fn check(&self, r: c_int) -> Result<(), String> {
        if r < 0 {
            Err(unsafe { CStr::from_ptr((self.error)(r)) }
                .to_string_lossy()
                .into())
        } else {
            Ok(())
        }
    }
}
unsafe extern "C" fn proc_address(_: *mut c_void, name: *const c_char) -> *mut c_void {
    #[link(name = "opengl32")]
    unsafe extern "system" {
        fn wglGetProcAddress(name: *const c_char) -> *mut c_void;
    }
    let p = unsafe { wglGetProcAddress(name) };
    if !p.is_null() && (p as usize) > 3 && (p as isize) != -1 {
        return p;
    }
    static OPENGL: std::sync::OnceLock<libloading::Library> = std::sync::OnceLock::new();
    let l = OPENGL.get_or_init(|| unsafe {
        libloading::Library::new("opengl32.dll").expect("Windows OpenGL")
    });
    unsafe {
        l.get::<*mut c_void>(CStr::from_ptr(name).to_bytes_with_nul())
            .map(|s| *s)
            .unwrap_or(ptr::null_mut())
    }
}
pub struct Player {
    api: Arc<Api>,
    handle: Handle,
    render: Handle,
    gl: Arc<glow::Context>,
    texture: glow::Texture,
    fbo: glow::Framebuffer,
    pub texture_id: Option<eframe::egui::TextureId>,
    size: [i32; 2],
    pub loaded: bool,
    pub error: Option<String>,
    pub redraw: bool,
    pub has_frame: bool,
    dirty: Box<std::sync::atomic::AtomicBool>,
    numbers: std::collections::HashMap<String, f64>,
    paused: bool,
}
// egui callbacks require Send + Sync. The mutex protects access, while creation,
// paint and destruction are all owned by eframe's single native GUI thread.
unsafe impl Send for Player {}
impl Player {
    pub fn new(api: Arc<Api>, gl: Arc<glow::Context>) -> Result<Self, String> {
        unsafe {
            let h = (api.create)();
            if h.is_null() {
                return Err("無法建立播放核心".into());
            }
            for (k, v) in [
                ("vo", "libmpv"),
                ("hwdec", "auto-safe"),
                ("keep-open", "yes"),
                ("idle", "yes"),
                ("pause", "yes"),
                ("osc", "no"),
                ("input-default-bindings", "no"),
                ("input-terminal", "no"),
                ("terminal", "no"),
                ("config", "no"),
                ("load-scripts", "no"),
                ("audio-display", "no"),
                ("hr-seek", "yes"),
                ("hr-seek-framedrop", "no"),
                ("keepaspect", "no"),
            ] {
                let k = CString::new(k).unwrap();
                let v = CString::new(v).unwrap();
                let r = (api.option)(h, k.as_ptr(), v.as_ptr());
                if let Err(e) = api.check(r) {
                    (api.destroy)(h);
                    return Err(e);
                }
            }
            if let Err(e) = api.check((api.init)(h)) {
                (api.destroy)(h);
                return Err(e);
            }
            for (key, format) in [
                ("time-pos", 5),
                ("duration", 5),
                ("dwidth", 5),
                ("dheight", 5),
                ("volume", 5),
                ("pause", 3),
            ] {
                let name = CString::new(key).unwrap();
                if let Err(e) = api.check((api.observe)(h, 0, name.as_ptr(), format)) {
                    (api.destroy)(h);
                    return Err(e);
                }
            }
            let mut render = ptr::null_mut();
            let mut init = GlInit {
                get: proc_address,
                ctx: ptr::null_mut(),
            };
            let mut params = [
                Param {
                    kind: 1,
                    data: c"opengl".as_ptr() as *mut _,
                },
                Param {
                    kind: 2,
                    data: &mut init as *mut _ as *mut _,
                },
                Param {
                    kind: 0,
                    data: ptr::null_mut(),
                },
            ];
            if let Err(e) = api.check((api.render_create)(&mut render, h, params.as_mut_ptr())) {
                (api.destroy)(h);
                return Err(e);
            }
            let texture = gl.create_texture()?;
            let fbo = gl.create_framebuffer()?;
            let mut dirty = Box::new(std::sync::atomic::AtomicBool::new(true));
            (api.render_callback)(
                render,
                Some(render_changed),
                &mut *dirty as *mut _ as *mut c_void,
            );
            Ok(Self {
                api,
                handle: h,
                render,
                gl,
                texture,
                fbo,
                texture_id: None,
                size: [0, 0],
                loaded: false,
                error: None,
                redraw: true,
                has_frame: false,
                dirty,
                numbers: std::collections::HashMap::new(),
                paused: true,
            })
        }
    }
    pub fn register(&mut self, frame: &mut eframe::Frame) {
        if self.texture_id.is_none() {
            self.texture_id = Some(frame.register_native_glow_texture(self.texture));
        }
    }
    pub fn command(&self, args: &[&str]) -> Result<(), String> {
        let a: Vec<_> = args
            .iter()
            .map(|s| CString::new(*s).map_err(|e| e.to_string()))
            .collect::<Result<_, _>>()?;
        let mut ptrs: Vec<_> = a.iter().map(|a| a.as_ptr()).collect();
        ptrs.push(ptr::null());
        self.api
            .check(unsafe { (self.api.command)(self.handle, 0, ptrs.as_ptr()) })
    }
    pub fn set(&self, key: &str, value: &str) -> Result<(), String> {
        self.command(&["set", key, value])
    }
    pub fn number(&self, key: &str) -> Option<f64> {
        self.numbers.get(key).copied()
    }
    pub fn flag(&self, key: &str) -> bool {
        key == "pause" && self.paused
    }
    pub fn set_number(&self, key: &str, mut value: f64) -> Result<(), String> {
        let k = CString::new(key).unwrap();
        self.api.check(unsafe {
            (self.api.set)(
                self.handle,
                0,
                k.as_ptr(),
                5,
                &mut value as *mut _ as *mut _,
            )
        })
    }
    pub fn load(&mut self, path: &str, start: f64, paused: bool) -> Result<(), String> {
        self.has_frame = false;
        self.loaded = false;
        self.error = None;
        self.set("pause", if paused { "yes" } else { "no" })?;
        self.command(&[
            "loadfile",
            path,
            "replace",
            "-1",
            &format!("start={start:.6}"),
        ])
    }
    pub fn poll(&mut self) {
        // No synchronous core calls on the GL thread: seeks may wait for this
        // same thread to render. Consume observations instead of querying it.
        for _ in 0..256 {
            let e = unsafe { &*(self.api.wait)(self.handle, 0.) };
            if e.id == 0 {
                break;
            }
            if e.id == 8 {
                self.loaded = true;
                self.redraw = true
            }
            if e.id == 22 && !e.data.is_null() {
                let p = unsafe { &*(e.data as *const Property) };
                if !p.name.is_null() {
                    let key = unsafe { CStr::from_ptr(p.name) }.to_string_lossy();
                    if p.format == 5 && !p.data.is_null() {
                        self.numbers
                            .insert(key.into_owned(), unsafe { *(p.data as *const f64) });
                    } else if p.format == 3 && key == "pause" && !p.data.is_null() {
                        self.paused = unsafe { *(p.data as *const c_int) } != 0;
                    } else if p.format == 0 {
                        self.numbers.remove(key.as_ref());
                    }
                }
            }
            if e.error < 0 {
                self.error = self.api.check(e.error).err()
            }
        }
    }
    pub fn paint(&mut self, w: i32, h: i32) {
        unsafe {
            let w = w.clamp(1, 4096);
            let h = h.clamp(1, 4096);
            let old = self.gl.get_parameter_i32(glow::FRAMEBUFFER_BINDING);
            if self.size != [w, h] {
                self.gl.bind_texture(glow::TEXTURE_2D, Some(self.texture));
                self.gl.tex_image_2d(
                    glow::TEXTURE_2D,
                    0,
                    glow::RGBA8 as i32,
                    w,
                    h,
                    0,
                    glow::RGBA,
                    glow::UNSIGNED_BYTE,
                    glow::PixelUnpackData::Slice(None),
                );
                self.gl.tex_parameter_i32(
                    glow::TEXTURE_2D,
                    glow::TEXTURE_MIN_FILTER,
                    glow::LINEAR as i32,
                );
                self.gl.tex_parameter_i32(
                    glow::TEXTURE_2D,
                    glow::TEXTURE_MAG_FILTER,
                    glow::LINEAR as i32,
                );
                self.gl.tex_parameter_i32(
                    glow::TEXTURE_2D,
                    glow::TEXTURE_WRAP_S,
                    glow::CLAMP_TO_EDGE as i32,
                );
                self.gl.tex_parameter_i32(
                    glow::TEXTURE_2D,
                    glow::TEXTURE_WRAP_T,
                    glow::CLAMP_TO_EDGE as i32,
                );
                self.gl.bind_framebuffer(glow::FRAMEBUFFER, Some(self.fbo));
                self.gl.framebuffer_texture_2d(
                    glow::FRAMEBUFFER,
                    glow::COLOR_ATTACHMENT0,
                    glow::TEXTURE_2D,
                    Some(self.texture),
                    0,
                );
                self.gl.bind_texture(glow::TEXTURE_2D, None);
                self.size = [w, h];
                self.redraw = true;
            }
            let notified = self.dirty.swap(false, std::sync::atomic::Ordering::AcqRel);
            if (self.api.render_update)(self.render) & 1 != 0 || self.redraw || notified {
                self.gl.disable(glow::SCISSOR_TEST);
                self.gl.disable(glow::BLEND);
                self.gl.use_program(None);
                self.gl.bind_vertex_array(None);
                self.gl.bind_buffer(glow::ARRAY_BUFFER, None);
                let mut f = Fbo {
                    fbo: self.fbo.0.get() as i32,
                    w,
                    h,
                    format: glow::RGBA8 as i32,
                };
                let mut flip: c_int = 0;
                let mut block: c_int = 0;
                let mut params = [
                    Param {
                        kind: 3,
                        data: &mut f as *mut _ as *mut _,
                    },
                    Param {
                        kind: 4,
                        data: &mut flip as *mut _ as *mut _,
                    },
                    Param {
                        kind: 12,
                        data: &mut block as *mut _ as *mut _,
                    },
                    Param {
                        kind: 0,
                        data: ptr::null_mut(),
                    },
                ];
                let r = (self.api.render)(self.render, params.as_mut_ptr());
                if r < 0 {
                    self.error = self.api.check(r).err()
                }
                self.redraw = false;
                if self.loaded && self.number("time-pos").is_some() {
                    self.has_frame = true;
                }
            }
            self.gl.bind_framebuffer(
                glow::FRAMEBUFFER,
                std::num::NonZeroU32::new(old as u32).map(glow::NativeFramebuffer),
            );
        }
    }
}
impl Player {
    pub fn refresh_hidden(&mut self) {
        let [w, h] = self.size;
        if w > 0 && h > 0 {
            self.paint(w, h);
        } else {
            self.paint(320, 180);
        }
    }
    #[allow(dead_code)]
    pub fn rendered_pixels(&self) -> Vec<u8> {
        unsafe {
            let old = self.gl.get_parameter_i32(glow::FRAMEBUFFER_BINDING);
            self.gl.bind_framebuffer(glow::FRAMEBUFFER, Some(self.fbo));
            let mut bytes = vec![0; (self.size[0] * self.size[1] * 3) as usize];
            self.gl.read_pixels(
                0,
                0,
                self.size[0],
                self.size[1],
                glow::RGB,
                glow::UNSIGNED_BYTE,
                glow::PixelPackData::Slice(Some(&mut bytes)),
            );
            self.gl.bind_framebuffer(
                glow::FRAMEBUFFER,
                std::num::NonZeroU32::new(old as u32).map(glow::NativeFramebuffer),
            );
            bytes
        }
    }
}
impl Drop for Player {
    fn drop(&mut self) {
        unsafe {
            (self.api.render_callback)(self.render, None, ptr::null_mut());
            (self.api.render_free)(self.render);
            (self.api.destroy)(self.handle);
            self.gl.delete_framebuffer(self.fbo); /* registered texture is owned by egui painter */
        }
    }
}
