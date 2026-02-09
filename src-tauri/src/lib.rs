mod sidecar;

use std::sync::Mutex;

use serde_json::Value;

use crate::sidecar::{find_backend_dir, find_python, SidecarManager};

/// Tauri-managed state wrapping the sidecar process manager.
struct SidecarState(Mutex<SidecarManager>);

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState(Mutex::new(SidecarManager::new())))
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            sidecar_health,
            send_to_sidecar,
            sidecar_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
