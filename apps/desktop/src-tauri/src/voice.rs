// Local speech-to-text via bundled whisper.cpp. The sidecar binary
// (binaries/whisper-cli-<triple>) is a short-lived CLI tool — invoked with an
// audio file, outputs text to stdout, then exits. Models are downloaded from
// HuggingFace on first use and cached under the runtime root.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::runtime;

/// Available whisper.cpp model sizes (ggml-<size>.bin).
const MODEL_SIZES: &[&str] = &["tiny", "base", "small"];
const DEFAULT_MODEL: &str = "tiny";

/// Base URL for whisper.cpp GGML model downloads.
/// Uses hf-mirror.com (HuggingFace mirror accessible from mainland China).
/// To switch back to the official HuggingFace hub, change to:
///   "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
const MODEL_BASE_URL: &str =
    "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main";

/// Approximate sizes in bytes for progress reporting.
const MODEL_BYTES: &[(&str, u64)] = &[
    ("tiny", 77_000_000),
    ("base", 147_000_000),
    ("small", 487_000_000),
];

fn model_bytes(size: &str) -> u64 {
    MODEL_BYTES
        .iter()
        .find(|(s, _)| *s == size)
        .map(|(_, b)| *b)
        .unwrap_or(77_000_000)
}

#[derive(Default)]
pub struct VoiceState {
    inner: Mutex<VoiceInner>,
}

#[derive(Default)]
struct VoiceInner {
    /// The user's chosen model size ("tiny" | "base" | "small").
    model_size: Option<String>,
    /// Set while a download is in progress (so concurrent requests don't race).
    downloading: bool,
}

/// Directory where whisper models are cached, e.g.
/// ~/Library/Application Support/com.ai4s.workbench/runtime/models/
pub fn model_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(runtime::runtime_root(app)?.join("models"))
}

/// Path to the currently-active model file (defaults to tiny).
fn model_path(app: &AppHandle) -> Result<PathBuf, String> {
    let state = app.state::<VoiceState>();
    let size = state
        .inner
        .lock()
        .unwrap()
        .model_size
        .clone()
        .unwrap_or_else(|| DEFAULT_MODEL.to_string());
    Ok(model_dir(app)?.join(format!("ggml-{size}.bin")))
}

/// Persist the user's model-size preference in a one-line file.
fn model_size_file(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(model_dir(app)?.join("model-size.txt"))
}

pub fn read_model_size(app: &AppHandle) -> String {
    model_size_file(app)
        .ok()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .map(|s| s.trim().to_string())
        .filter(|s| MODEL_SIZES.contains(&s.as_str()))
        .unwrap_or_else(|| DEFAULT_MODEL.to_string())
}

pub fn save_model_size(app: &AppHandle, size: &str) -> Result<(), String> {
    let file = model_size_file(app)?;
    if let Some(parent) = file.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    std::fs::write(&file, size).map_err(|e| e.to_string())
}

// ---- Tauri Commands ----

/// Result of a transcription call.
#[derive(serde::Serialize)]
pub struct TranscribeResult {
    pub text: String,
    /// Wall-clock seconds the sidecar took (None when skipped).
    pub duration_secs: Option<f64>,
}

/// Resolve the bundled whisper-cli sidecar binary. In production (Tauri build)
/// it lives next to the app executable; in dev mode (`cargo tauri dev`) the
/// sidecar lives in `binaries/` with its target-triple suffix, so we look
/// there first, then fall back to PATH.
fn whisper_cli_path() -> Result<PathBuf, String> {
    let name = if cfg!(windows) {
        "whisper-cli.exe"
    } else {
        "whisper-cli"
    };

    // 1) Next to the current exe (production — Tauri copies it there).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let bin = dir.join(name);
            if bin.is_file() {
                return Ok(bin);
            }
        }
    }

    // 2) In the binaries/ directory (dev mode after running fetch-whisper.sh).
    //    The file is named like `whisper-cli-x86_64-pc-windows-msvc.exe`; we
    //    glob for `whisper-cli-*` and pick the first match.
    let cargo_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_default();
    let binaries_dir = PathBuf::from(&cargo_dir).join("binaries");
    if let Ok(entries) = std::fs::read_dir(&binaries_dir) {
        let prefix = if cfg!(windows) {
            "whisper-cli-"
        } else {
            "whisper-cli-"
        };
        for entry in entries.flatten() {
            let fname = entry.file_name();
            let fname = fname.to_string_lossy();
            if fname.starts_with(prefix) {
                let path = binaries_dir.join(fname.as_ref());
                if path.is_file() {
                    return Ok(path);
                }
            }
        }
    }

    // 3) Fall back to PATH (useful when the developer installed whisper.cpp
    //    globally, e.g. `brew install whisper-cpp`).
    Err(format!(
        "whisper-cli not found. Run: bash scripts/dev/fetch-whisper.sh"
    ))
}

/// Resolve the audio file path. `path` may be:
///   - An absolute path → used as-is.
///   - A plain file name (no directory separators) → resolved relative to the
///     active workspace (where `add_binary_to_workspace` writes files).
/// This avoids cross-platform path-encoding issues when Windows backslash paths
/// transit Tauri's JSON IPC layer.
fn resolve_audio_path(app: &AppHandle, path: &str) -> Result<PathBuf, String> {
    let p = Path::new(path);
    // Already absolute or contains directory separators — use as-is.
    if p.is_absolute() || path.contains('/') || path.contains('\\') {
        if p.is_file() {
            return Ok(p.to_path_buf());
        }
        // The path had separators but doesn't exist — try as a workspace-relative
        // fallback in case it's a mangled absolute path.
        let ws = runtime::workspace_dir(app)?;
        let fallback = ws.join(p.file_name().unwrap_or(p.as_os_str()));
        if fallback.is_file() {
            return Ok(fallback);
        }
        return Err(format!(
            "audio file not found: {}",
            path.replace('\\', "/")
        ));
    }
    // Plain file name → resolve against the active workspace.
    let ws = runtime::workspace_dir(app)?;
    let resolved = ws.join(path);
    if resolved.is_file() {
        return Ok(resolved);
    }
    Err(format!(
        "audio file not found: {} (in {})",
        path,
        ws.to_string_lossy().replace('\\', "/"),
    ))
}

/// Run whisper.cpp on an audio file (16 kHz mono WAV) and return the
/// transcribed text. Blocks the caller for the duration of inference — the
/// frontend should call this from a non-UI thread or show a spinner.
///
/// `path` can be an absolute path or a workspace-relative filename.
#[tauri::command(async)]
pub fn transcribe_audio(
    app: AppHandle,
    _state: State<'_, VoiceState>,
    path: String,
    language: Option<String>,
) -> Result<TranscribeResult, String> {
    let audio_path = resolve_audio_path(&app, &path)?;

    let model = model_path(&app)?;
    if !model.is_file() {
        return Err(format!(
            "model not downloaded: {}. The app will auto-download it on first use.",
            model.to_string_lossy().replace('\\', "/"),
        ));
    }

    let whisper_bin = whisper_cli_path()?;
    let lang = language.unwrap_or_else(|| "auto".to_string());
    let start = std::time::Instant::now();

    let output = runtime::quiet_command(&whisper_bin)
        .arg("-m")
        .arg(model.to_string_lossy().to_string())
        .arg("-f")
        .arg(audio_path.to_string_lossy().to_string())
        .arg("-l")
        .arg(&lang)
        .arg("--no-timestamps")
        .arg("-otxt")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("failed to run whisper-cli: {e}"))?;

    let duration = start.elapsed().as_secs_f64();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("whisper-cli exited with error: {stderr}"));
    }

    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok(TranscribeResult {
        text,
        duration_secs: Some(duration),
    })
}

/// Current voice-input status: which models are downloaded, which is active,
/// and whether a download is in progress.
#[derive(serde::Serialize)]
pub struct VoiceStatus {
    pub available: bool,
    pub models_downloaded: Vec<String>,
    pub active_model: String,
    pub downloading: bool,
}

#[tauri::command(async)]
pub fn voice_status(app: AppHandle, state: State<'_, VoiceState>) -> Result<VoiceStatus, String> {
    let dir = model_dir(&app)?;
    let inner = state.inner.lock().unwrap();
    let active = inner
        .model_size
        .clone()
        .unwrap_or_else(|| DEFAULT_MODEL.to_string());

    let mut downloaded = Vec::new();
    for size in MODEL_SIZES {
        if dir.join(format!("ggml-{size}.bin")).is_file() {
            downloaded.push(size.to_string());
        }
    }

    Ok(VoiceStatus {
        available: !downloaded.is_empty(),
        models_downloaded: downloaded,
        active_model: active,
        downloading: inner.downloading,
    })
}

/// Switch the active model size ("tiny", "base", or "small"). The model file
/// must already be downloaded (call `voice_model_download` first if needed).
#[tauri::command(async)]
pub fn set_voice_model(
    app: AppHandle,
    state: State<'_, VoiceState>,
    model: String,
) -> Result<(), String> {
    if !MODEL_SIZES.contains(&model.as_str()) {
        return Err(format!(
            "unknown model size: {model}. Use one of: {}",
            MODEL_SIZES.join(", ")
        ));
    }
    let path = model_dir(&app)?.join(format!("ggml-{model}.bin"));
    if !path.is_file() {
        return Err(format!(
            "model not downloaded: {}. Download it first.",
            path.display()
        ));
    }
    save_model_size(&app, &model)?;
    state.inner.lock().unwrap().model_size = Some(model.clone());
    Ok(())
}

/// Download a whisper model from HuggingFace. Emits `voice:progress` events
/// with {model, downloaded_bytes, total_bytes, done: bool}. Idempotent.
#[tauri::command(async)]
pub fn voice_model_download(
    app: AppHandle,
    state: State<'_, VoiceState>,
    model: String,
) -> Result<(), String> {
    if !MODEL_SIZES.contains(&model.as_str()) {
        return Err(format!(
            "unknown model size: {model}. Use one of: {}",
            MODEL_SIZES.join(", ")
        ));
    }

    let dir = model_dir(&app)?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let dest = dir.join(format!("ggml-{model}.bin"));

    // Already downloaded.
    if dest.is_file() {
        save_model_size(&app, &model)?;
        state.inner.lock().unwrap().model_size = Some(model.clone());
        // Emit a done event so the UI can advance.
        let _ = app.emit("voice:progress", serde_json::json!({
            "model": model,
            "downloadedBytes": dest.metadata().map(|m| m.len()).unwrap_or(0),
            "totalBytes": model_bytes(&model),
            "done": true,
        }));
        return Ok(());
    }

    // Guard against concurrent downloads.
    {
        let mut inner = state.inner.lock().unwrap();
        if inner.downloading {
            return Err("a model download is already in progress".to_string());
        }
        inner.downloading = true;
    }

    let url = format!("{MODEL_BASE_URL}/ggml-{model}.bin");
    let total = model_bytes(&model);

    // Download on a dedicated OS thread via std::thread::spawn to avoid the
    // tokio panic that reqwest::blocking causes: it creates its own internal
    // tokio Runtime, and dropping that Runtime inside Tauri's async command
    // context triggers "Cannot drop a runtime in a context where blocking
    // is not allowed". A plain OS thread has no async context — safe to drop.
    let (tx, rx) = std::sync::mpsc::channel::<Result<(), String>>();
    let app2 = app.clone();
    let model2 = model.clone();
    let dest2 = dest.clone();

    std::thread::spawn(move || {
        let res = (move || -> Result<(), String> {
            let client = reqwest::blocking::Client::new();
            let resp = client
                .get(&url)
                .timeout(std::time::Duration::from_secs(600))
                .send()
                .map_err(|e| format!("download failed: {e}"))?;

            if !resp.status().is_success() {
                return Err(format!("download failed: HTTP {}", resp.status()));
            }

            let mut downloaded: u64 = 0;
            let mut buf = Vec::new();
            use std::io::Read;
            let mut reader = resp;
            let mut chunk = [0u8; 64 * 1024];
            let mut last_emit = std::time::Instant::now();
            loop {
                let n = reader
                    .read(&mut chunk)
                    .map_err(|e| format!("download read error: {e}"))?;
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&chunk[..n]);
                downloaded += n as u64;

                let now = std::time::Instant::now();
                if (now - last_emit).as_millis() >= 200 || downloaded == total {
                    last_emit = now;
                    let _ = app2.emit("voice:progress", serde_json::json!({
                        "model": model2,
                        "downloadedBytes": downloaded,
                        "totalBytes": total,
                        "done": false,
                    }));
                }
            }

            std::fs::write(&dest2, &buf)
                .map_err(|e| format!("failed to save model: {e}"))?;

            let _ = app2.emit("voice:progress", serde_json::json!({
                "model": model2,
                "downloadedBytes": downloaded,
                "totalBytes": total,
                "done": true,
            }));
            Ok(())
        })();
        let _ = tx.send(res);
    });

    // Block the Tauri command until download completes.
    let result = rx.recv().map_err(|e| format!("download thread panicked: {e}"))?;

    // Reset downloading flag regardless of outcome.
    state.inner.lock().unwrap().downloading = false;

    match &result {
        Ok(()) => {
            save_model_size(&app, &model)?;
            state.inner.lock().unwrap().model_size = Some(model.clone());
        }
        Err(e) => {
            let _ = std::fs::remove_file(&dest);
            return Err(e.clone());
        }
    }

    result
}

/// Initialize voice state from disk on app start. Also checks whether the
/// whisper-cli binary and model are present and emits events so the frontend
/// can surface a one-click fix if anything is missing.
pub fn init(app: &AppHandle) {
    let size = read_model_size(app);
    let state = app.state::<VoiceState>();
    state.inner.lock().unwrap().model_size = Some(size.clone());

    // Check whisper-cli binary.
    if let Err(e) = whisper_cli_path() {
        let _ = app.emit("voice:needs-binary", serde_json::json!({
            "message": e,
        }));
    }

    // Check model.
    let model_file = match model_dir(app) {
        Ok(dir) => dir.join(format!("ggml-{size}.bin")),
        Err(_) => return,
    };
    if !model_file.is_file() {
        let _ = app.emit("voice:needs-model", serde_json::json!({
            "model": size,
        }));
    }
}
