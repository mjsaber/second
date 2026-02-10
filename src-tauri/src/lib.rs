mod audio;
mod sidecar;

use std::path::PathBuf;
use std::sync::Mutex;

use serde_json::Value;
use tauri::Manager;

use crate::audio::capture::AudioCaptureManager;
use crate::audio::devices;
use crate::sidecar::{find_backend_dir, find_python, SidecarManager};

/// Tauri-managed state wrapping the sidecar process manager.
struct SidecarState(Mutex<SidecarManager>);

/// Tauri-managed state wrapping the audio capture manager.
struct AudioState {
    manager: AudioCaptureManager,
    recordings_dir: Mutex<PathBuf>,
}

// ---------------------------------------------------------------------------
// Sidecar commands
// ---------------------------------------------------------------------------

/// Start the Python sidecar, auto-detecting the Python interpreter and backend
/// directory. Sends a health check after startup and returns `"ok"` on success.
#[tauri::command]
fn start_sidecar(state: tauri::State<'_, SidecarState>) -> Result<String, String> {
    let mut mgr = state.0.lock().map_err(|e| format!("Lock poisoned: {e}"))?;

    let backend_dir = find_backend_dir()?;
    let python = find_python(Some(&backend_dir))?;

    mgr.start(&python, &backend_dir)?;

    // Verify the sidecar is responding.
    let health = mgr.send_message(serde_json::json!({"type": "health"}))?;
    if health.get("status").and_then(Value::as_str) != Some("ok") {
        mgr.stop()?;
        return Err(format!("Health check failed: {health}"));
    }

    Ok("ok".into())
}

/// Stop the Python sidecar process.
#[tauri::command]
fn stop_sidecar(state: tauri::State<'_, SidecarState>) -> Result<(), String> {
    let mut mgr = state.0.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
    mgr.stop()
}

/// Send a health check to the sidecar and return the response.
#[tauri::command]
fn sidecar_health(state: tauri::State<'_, SidecarState>) -> Result<Value, String> {
    let mut mgr = state.0.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
    mgr.send_message(serde_json::json!({"type": "health"}))
}

/// Send an arbitrary JSON message to the sidecar and return the response.
#[tauri::command]
fn send_to_sidecar(message: Value, state: tauri::State<'_, SidecarState>) -> Result<Value, String> {
    let mut mgr = state.0.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
    mgr.send_message(message)
}

/// Check whether the sidecar process is currently running.
#[tauri::command]
fn sidecar_status(state: tauri::State<'_, SidecarState>) -> Result<bool, String> {
    let mut mgr = state.0.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
    Ok(mgr.is_running())
}

// ---------------------------------------------------------------------------
// Audio commands
// ---------------------------------------------------------------------------

/// List all available audio input device names.
#[tauri::command]
fn list_audio_devices() -> Result<Vec<String>, String> {
    let devs = devices::list_input_devices()?;
    Ok(devs.into_iter().map(|d| d.name).collect())
}

/// Start recording audio from the specified device (or the default device).
///
/// Returns the file path of the WAV file being recorded.
#[tauri::command]
fn start_audio_recording(
    device_name: Option<String>,
    state: tauri::State<'_, AudioState>,
) -> Result<String, String> {
    let recordings_dir = state
        .recordings_dir
        .lock()
        .map_err(|e| format!("Lock poisoned: {e}"))?;
    state
        .manager
        .start(device_name.as_deref(), &recordings_dir)
}

/// Stop the current audio recording. Returns the path to the finalized WAV file.
#[tauri::command]
fn stop_audio_recording(state: tauri::State<'_, AudioState>) -> Result<String, String> {
    state.manager.stop()
}

// ---------------------------------------------------------------------------
// App entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState(Mutex::new(SidecarManager::new())))
        .setup(|app| {
            // Resolve the recordings directory inside the app's data dir.
            let app_data_dir = app
                .path()
                .app_data_dir()
                .map_err(|e| format!("Failed to resolve app data directory: {e}"))
                .expect("app data dir must be resolvable");

            let recordings_dir = app_data_dir.join("recordings");

            app.manage(AudioState {
                manager: AudioCaptureManager::new(),
                recordings_dir: Mutex::new(recordings_dir),
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            sidecar_health,
            send_to_sidecar,
            sidecar_status,
            list_audio_devices,
            start_audio_recording,
            stop_audio_recording,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
