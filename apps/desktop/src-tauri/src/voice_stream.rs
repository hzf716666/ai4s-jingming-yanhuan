// Streaming voice input via sherpa-onnx. Provides true real-time, word-by-word
// transcription using Paraformer/SenseVoice streaming models.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;

use tauri::{AppHandle, Emitter, State};

use crate::runtime;
use crate::voice::{model_dir, read_model_size, save_model_size};

const MODEL_BASE_URL: &str = "https://hf-mirror.com/k2-fsa/sherpa-onnx-streaming-paraformer-bilingual-zh-en/raw/main";

const MODEL_SIZES: &[&str] = &["tiny", "base"];
const DEFAULT_MODEL: &str = "tiny";

fn streaming_model_bytes(size: &str) -> u64 {
    match size {
        "tiny" => 23_000_000,
        "base" => 46_000_000,
        _ => 23_000_000,
    }
}

struct SessionHandle {
    recognizer: sherpa_onnx::OnlineRecognizer,
    stream: sherpa_onnx::OnlineStream,
    sample_rate: i32,
    start_time: std::time::Instant,
}

pub struct StreamingVoiceState {
    inner: Mutex<StreamingVoiceInner>,
}

struct StreamingVoiceInner {
    model_size: Option<String>,
    sessions: HashMap<String, SessionHandle>,
}

impl Default for StreamingVoiceInner {
    fn default() -> Self {
        Self {
            model_size: None,
            sessions: HashMap::new(),
        }
    }
}

impl Default for StreamingVoiceState {
    fn default() -> Self {
        Self {
            inner: Mutex::new(StreamingVoiceInner::default()),
        }
    }
}

fn streaming_model_path(app: &AppHandle) -> Result<PathBuf, String> {
    let state = app.state::<StreamingVoiceState>();
    let size = state
        .inner
        .lock()
        .unwrap()
        .model_size
        .clone()
        .unwrap_or_else(|| DEFAULT_MODEL.to_string());
    Ok(model_dir(app)?.join(format!("sherpa-onnx-{size}.onnx")))
}

#[derive(serde::Serialize)]
pub struct StreamingVoiceStatus {
    pub available: bool,
    pub model_downloaded: bool,
    pub active_model: String,
    pub is_streaming: bool,
    pub session_count: usize,
}

#[tauri::command(async)]
pub fn streaming_voice_status(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
) -> Result<StreamingVoiceStatus, String> {
    let inner = state.inner.lock().unwrap();
    let model_file = streaming_model_path(&app)?;

    Ok(StreamingVoiceStatus {
        available: model_file.is_file(),
        model_downloaded: model_file.is_file(),
        active_model: inner.model_size.clone().unwrap_or_else(|| DEFAULT_MODEL.to_string()),
        is_streaming: !inner.sessions.is_empty(),
        session_count: inner.sessions.len(),
    })
}

#[tauri::command(async)]
pub fn download_streaming_model(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
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
    let dest = streaming_model_path(&app)?;

    if dest.is_file() {
        save_model_size(&app, &model)?;
        state.inner.lock().unwrap().model_size = Some(model.clone());
        let _ = app.emit("voice-stream:progress", serde_json::json!({
            "model": model,
            "downloadedBytes": dest.metadata().map(|m| m.len()).unwrap_or(0),
            "totalBytes": streaming_model_bytes(&model),
            "done": true,
        }));
        return Ok(());
    }

    let url = format!(
        "{}/sherpa-onnx-streaming-paraformer-bilingual-zh-en-{}.onnx",
        MODEL_BASE_URL, model
    );
    let total = streaming_model_bytes(&model);

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
                    let _ = app2.emit("voice-stream:progress", serde_json::json!({
                        "model": model2,
                        "downloadedBytes": downloaded,
                        "totalBytes": total,
                        "done": false,
                    }));
                }
            }

            std::fs::write(&dest2, &buf)
                .map_err(|e| format!("failed to save model: {e}"))?;

            let _ = app2.emit("voice-stream:progress", serde_json::json!({
                "model": model2,
                "downloadedBytes": downloaded,
                "totalBytes": total,
                "done": true,
            }));
            Ok(())
        })();
        let _ = tx.send(res);
    });

    let result = rx.recv().map_err(|e| format!("download thread panicked: {e}"))?;

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

#[derive(serde::Serialize)]
pub struct StartStreamingResult {
    pub session_id: String,
    pub sample_rate: i32,
}

#[tauri::command(async)]
pub fn start_streaming_session(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
) -> Result<StartStreamingResult, String> {
    let model_path = streaming_model_path(&app)?;
    if !model_path.is_file() {
        return Err(format!(
            "model not downloaded: {}. Call download_streaming_model first.",
            model_path.display()
        ));
    }

    let recognizer = sherpa_onnx::OnlineRecognizer::create(&sherpa_onnx::OnlineRecognizerConfig {
        model_config: sherpa_onnx::OnlineModelConfig {
            paraformer: sherpa_onnx::OnlineParaformerModelConfig {
                encoder: Some(model_path.to_string_lossy().to_string()),
                decoder: Default::default(),
            },
            ..Default::default()
        },
        ..Default::default()
    }).ok_or("failed to create OnlineRecognizer")?;

    let stream = recognizer.create_stream();
    let sample_rate = 16000;
    let session_id = uuid::Uuid::new_v4().to_string();

    {
        let mut inner = state.inner.lock().unwrap();
        inner.sessions.insert(
            session_id.clone(),
            SessionHandle {
                recognizer,
                stream,
                sample_rate,
                start_time: std::time::Instant::now(),
            },
        );
    }

    let _ = app.emit(
        "voice-stream:started",
        serde_json::json!({
            "sessionId": session_id,
        }),
    );

    Ok(StartStreamingResult {
        session_id,
        sample_rate,
    })
}

#[tauri::command(async)]
pub fn accept_audio_chunk(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
    session_id: String,
    samples: Vec<f32>,
) -> Result<(), String> {
    let mut inner = state.inner.lock().unwrap();
    let session = inner
        .sessions
        .get_mut(&session_id)
        .ok_or_else(|| "session not found or expired".to_string())?;

    session.stream.accept_waveform(session.sample_rate, samples.as_slice());

    session.recognizer.decode(&session.stream);

    let partial_text = session.recognizer
        .get_result(&session.stream)
        .map(|r| r.text)
        .unwrap_or_default();

    let _ = app.emit(
        "voice-stream:partial",
        serde_json::json!({
            "sessionId": session_id,
            "text": partial_text,
            "elapsedMs": session.start_time.elapsed().as_millis() as u64,
        }),
    );

    Ok(())
}

#[tauri::command(async)]
pub fn get_streaming_partial(
    _app: AppHandle,
    state: State<'_, StreamingVoiceState>,
    session_id: String,
) -> Result<String, String> {
    let inner = state.inner.lock().unwrap();
    let session = inner
        .sessions
        .get(&session_id)
        .ok_or_else(|| "session not found or expired".to_string())?;

    Ok(session.recognizer.get_result(&session.stream).map(|r| r.text).unwrap_or_default())
}

#[tauri::command(async)]
pub fn end_streaming_session(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
    session_id: String,
) -> Result<String, String> {
    let mut inner = state.inner.lock().unwrap();
    let mut session = inner
        .sessions
        .remove(&session_id)
        .ok_or_else(|| "session not found or expired".to_string())?;

    session.recognizer.decode(&session.stream);

    let final_text = session.recognizer.get_result(&session.stream).map(|r| r.text).unwrap_or_default();
    let elapsed_ms = session.start_time.elapsed().as_millis() as u64;

    let _ = app.emit(
        "voice-stream:final",
        serde_json::json!({
            "sessionId": session_id,
            "text": final_text,
            "elapsedMs": elapsed_ms,
        }),
    );

    Ok(final_text)
}

#[tauri::command(async)]
pub fn cancel_streaming_session(
    app: AppHandle,
    state: State<'_, StreamingVoiceState>,
    session_id: String,
) -> Result<(), String> {
    let mut inner = state.inner.lock().unwrap();
    inner.sessions.remove(&session_id);

    let _ = app.emit(
        "voice-stream:cancelled",
        serde_json::json!({
            "sessionId": session_id,
        }),
    );

    Ok(())
}

pub fn init(app: &AppHandle) {
    let state = app.state::<StreamingVoiceState>();
    let size = read_model_size(app);
    state.inner.lock().unwrap().model_size = Some(size.clone());

    let model_file = match streaming_model_path(app) {
        Ok(path) => path,
        Err(_) => return,
    };
    if !model_file.is_file() {
        let _ = app.emit(
            "voice-stream:needs-model",
            serde_json::json!({
                "model": size,
            }),
        );
    }
}
