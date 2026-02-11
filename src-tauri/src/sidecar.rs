//! Sidecar process manager for the Python backend.
//!
//! Manages the lifecycle of a child Python process that communicates via
//! JSON-over-stdin/stdout. Each request is a single JSON line written to the
//! child's stdin; each response is a single JSON line read from its stdout.

use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, Command, Stdio};

use serde_json::Value;

/// Manages a child Python sidecar process.
///
/// The manager owns the child process handle and provides methods to send
/// JSON messages and receive JSON responses over piped stdin/stdout.
pub struct SidecarManager {
    process: Option<Child>,
    stdin: Option<std::process::ChildStdin>,
    stdout: Option<BufReader<std::process::ChildStdout>>,
}

impl SidecarManager {
    /// Create a new manager with no running process.
    pub fn new() -> Self {
        Self {
            process: None,
            stdin: None,
            stdout: None,
        }
    }

    /// Spawn the Python sidecar process.
    ///
    /// # Arguments
    /// * `python_path` - Path to the Python interpreter (e.g. `python3`).
    /// * `backend_dir` - Working directory containing `main.py`.
    ///
    /// # Errors
    /// Returns an error if the process cannot be spawned or if a sidecar is
    /// already running.
    pub fn start(&mut self, python_path: &str, backend_dir: &str) -> Result<(), String> {
        if self.is_running() {
            return Err("Sidecar is already running".into());
        }

        let mut child = Command::new(python_path)
            .arg("main.py")
            .current_dir(backend_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

        self.stdin = child.stdin.take();
        self.stdout = child.stdout.take().map(BufReader::new);
        self.process = Some(child);

        Ok(())
    }

    /// Send a JSON message to the sidecar and wait for a single-line JSON
    /// response.
    ///
    /// # Errors
    /// Returns an error if the sidecar is not running, or if
    /// serialization/deserialization fails, or if the write/read fails.
    pub fn send_message(&mut self, message: Value) -> Result<Value, String> {
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| "Sidecar stdin not available".to_string())?;
        let stdout = self
            .stdout
            .as_mut()
            .ok_or_else(|| "Sidecar stdout not available".to_string())?;

        let mut serialized = serde_json::to_string(&message)
            .map_err(|e| format!("Failed to serialize message: {e}"))?;
        serialized.push('\n');

        stdin
            .write_all(serialized.as_bytes())
            .map_err(|e| format!("Failed to write to sidecar stdin: {e}"))?;
        stdin
            .flush()
            .map_err(|e| format!("Failed to flush sidecar stdin: {e}"))?;

        let mut line = String::new();
        let bytes_read = stdout
            .read_line(&mut line)
            .map_err(|e| format!("Failed to read from sidecar stdout: {e}"))?;

        if bytes_read == 0 {
            return Err("Sidecar process closed stdout (possible crash)".into());
        }

        serde_json::from_str(line.trim())
            .map_err(|e| format!("Failed to parse sidecar response: {e}"))
    }

    /// Kill the sidecar process and clean up handles.
    ///
    /// # Errors
    /// Returns an error if the kill signal cannot be sent.
    pub fn stop(&mut self) -> Result<(), String> {
        // Drop stdin/stdout first so the child isn't blocked on I/O.
        self.stdin.take();
        self.stdout.take();

        if let Some(mut child) = self.process.take() {
            child
                .kill()
                .map_err(|e| format!("Failed to kill sidecar: {e}"))?;
            child
                .wait()
                .map_err(|e| format!("Failed to wait on sidecar: {e}"))?;
        }

        Ok(())
    }

    /// Returns `true` if the sidecar process is believed to be running.
    ///
    /// This performs a non-blocking check. If the process has exited since the
    /// last check the internal state is cleaned up automatically.
    pub fn is_running(&mut self) -> bool {
        if let Some(ref mut child) = self.process {
            match child.try_wait() {
                Ok(Some(_status)) => {
                    // Process has exited — clean up.
                    self.process.take();
                    self.stdin.take();
                    self.stdout.take();
                    false
                }
                Ok(None) => true,
                Err(_) => false,
            }
        } else {
            false
        }
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        // Best-effort cleanup on drop.
        let _ = self.stop();
    }
}

// ---------------------------------------------------------------------------
// Python discovery helpers
// ---------------------------------------------------------------------------

/// Try to locate a usable Python interpreter.
///
/// Search order:
/// 1. `python3` on `$PATH`
/// 2. `python` on `$PATH`
/// 3. The backend virtualenv at `<backend_dir>/.venv/bin/python`
///
/// # Errors
/// Returns an error if no Python interpreter can be found.
pub fn find_python(backend_dir: Option<&str>) -> Result<String, String> {
    // 1. .venv inside the backend directory (preferred — correct Python version + deps)
    if let Some(dir) = backend_dir {
        let venv_python = Path::new(dir).join(".venv/bin/python");
        if venv_python.exists() {
            return venv_python
                .to_str()
                .map(String::from)
                .ok_or_else(|| "Virtualenv python path is not valid UTF-8".into());
        }
    }

    // 2. python3 on PATH
    if command_exists("python3") {
        return Ok("python3".into());
    }

    // 3. python on PATH
    if command_exists("python") {
        return Ok("python".into());
    }

    Err("Could not find a Python interpreter. Create a virtualenv in backend/.venv or install Python 3.11+.".into())
}

/// Resolve the backend directory path.
///
/// Checks, in order:
/// 1. The `SECOND_BACKEND_DIR` environment variable.
/// 2. `../backend/` relative to the current executable.
///
/// # Errors
/// Returns an error if no valid backend directory can be found.
pub fn find_backend_dir() -> Result<String, String> {
    // 1. Env var
    if let Ok(dir) = std::env::var("SECOND_BACKEND_DIR") {
        let path = Path::new(&dir);
        if path.is_dir() {
            return Ok(dir);
        }
        return Err(format!(
            "SECOND_BACKEND_DIR is set to '{dir}' but that directory does not exist"
        ));
    }

    // 2. Relative to executable (handles both release and dev builds)
    //    - Release: exe is at <project>/second  => ../backend works
    //    - Dev:     exe is at src-tauri/target/debug/second => ../../../backend works
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            for relative in ["../backend", "../../../backend"] {
                let backend = exe_dir.join(relative);
                if backend.is_dir() {
                    return backend
                        .canonicalize()
                        .map_err(|e| format!("Failed to canonicalize backend path: {e}"))?
                        .to_str()
                        .map(String::from)
                        .ok_or_else(|| "Backend path is not valid UTF-8".into());
                }
            }
        }
    }

    // 3. Relative to current working directory (dev mode — npx tauri dev runs from project root)
    if let Ok(cwd) = std::env::current_dir() {
        let backend = cwd.join("backend");
        if backend.is_dir() {
            return backend
                .canonicalize()
                .map_err(|e| format!("Failed to canonicalize backend path: {e}"))?
                .to_str()
                .map(String::from)
                .ok_or_else(|| "Backend path is not valid UTF-8".into());
        }
    }

    Err("Could not find the backend directory. Set SECOND_BACKEND_DIR or ensure backend/ exists relative to the project root.".into())
}

/// Check whether a command is available on `$PATH` by running it with
/// `--version`.
fn command_exists(cmd: &str) -> bool {
    Command::new(cmd)
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // -- Unit tests for JSON serialization / deserialization --

    #[test]
    fn test_health_message_serialization() {
        let msg = json!({"type": "health"});
        let serialized = serde_json::to_string(&msg).expect("serialize");
        assert!(serialized.contains("\"type\":\"health\""));
    }

    #[test]
    fn test_response_deserialization() {
        let raw = r#"{"type": "health", "status": "ok"}"#;
        let parsed: Value = serde_json::from_str(raw).expect("parse");
        assert_eq!(parsed["type"], "health");
        assert_eq!(parsed["status"], "ok");
    }

    #[test]
    fn test_error_response_deserialization() {
        let raw = r#"{"type": "error", "message": "something went wrong"}"#;
        let parsed: Value = serde_json::from_str(raw).expect("parse");
        assert_eq!(parsed["type"], "error");
        assert_eq!(parsed["message"], "something went wrong");
    }

    #[test]
    fn test_complex_message_roundtrip() {
        let msg = json!({
            "type": "transcribe_chunk",
            "audio_base64": "AAAA",
            "initial_prompt": "test"
        });
        let serialized = serde_json::to_string(&msg).expect("serialize");
        let deserialized: Value = serde_json::from_str(&serialized).expect("deserialize");
        assert_eq!(msg, deserialized);
    }

    // -- find_python tests --

    #[test]
    fn test_find_python_returns_ok() {
        // On any system with Python installed this should succeed.
        let result = find_python(None);
        // We can't guarantee Python is installed in CI, so just check the
        // function doesn't panic and returns a reasonable result.
        match result {
            Ok(path) => assert!(!path.is_empty()),
            Err(e) => assert!(e.contains("Could not find")),
        }
    }

    #[test]
    fn test_find_python_with_nonexistent_venv() {
        let result = find_python(Some("/tmp/definitely_does_not_exist_12345"));
        // Venv doesn't exist, so falls back to system python; only errors if none found.
        match result {
            Ok(path) => assert!(!path.is_empty()),
            Err(e) => assert!(e.contains("Could not find")),
        }
    }

    // -- SidecarManager unit tests --

    #[test]
    fn test_new_manager_is_not_running() {
        let mut mgr = SidecarManager::new();
        assert!(!mgr.is_running());
    }

    #[test]
    fn test_stop_on_idle_manager_is_ok() {
        let mut mgr = SidecarManager::new();
        assert!(mgr.stop().is_ok());
    }

    #[test]
    fn test_send_message_without_start_returns_error() {
        let mut mgr = SidecarManager::new();
        let result = mgr.send_message(json!({"type": "health"}));
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("stdin not available"));
    }

    #[test]
    fn test_start_with_invalid_python_returns_error() {
        let mut mgr = SidecarManager::new();
        let result = mgr.start("/no/such/python", "/tmp");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Failed to spawn"));
    }

    #[test]
    fn test_double_start_returns_error() {
        let mut mgr = SidecarManager::new();
        // Use a long-running command so the process is still alive for the
        // second start attempt. `cat` with piped stdin will block until stdin
        // is closed.
        let started = mgr.start("cat", "/tmp");
        if started.is_ok() {
            let second = mgr.start("cat", "/tmp");
            assert!(second.is_err());
            assert!(second.unwrap_err().contains("already running"));
            let _ = mgr.stop();
        }
    }

    // -- Integration test with the real Python backend --

    #[test]
    fn test_integration_health_check() {
        // Use a well-known path relative to the repo root rather than
        // relying on find_backend_dir(), which resolves from the test
        // binary location and may not match the source tree.
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let backend_dir = std::path::Path::new(manifest_dir).join("../backend");
        let backend_dir = match backend_dir.canonicalize() {
            Ok(p) => p,
            Err(_) => {
                eprintln!("Skipping integration test: backend dir not found");
                return;
            }
        };
        let backend_dir = backend_dir.to_str().expect("backend dir not utf-8");

        let python = match find_python(Some(backend_dir)) {
            Ok(p) => p,
            Err(_) => {
                eprintln!("Skipping integration test: python not found");
                return;
            }
        };

        let mut mgr = SidecarManager::new();

        // Start
        mgr.start(&python, backend_dir)
            .expect("Failed to start sidecar");
        assert!(mgr.is_running());

        // Health check
        let response = mgr
            .send_message(json!({"type": "health"}))
            .expect("Health check failed");
        assert_eq!(response["type"], "health");
        assert_eq!(response["status"], "ok");

        // Stop
        mgr.stop().expect("Failed to stop sidecar");
        assert!(!mgr.is_running());
    }

    // -- find_backend_dir tests --
    //
    // These tests modify process-global env vars and MUST run inside
    // a single test to avoid races with the parallel test runner.

    #[test]
    fn test_find_backend_dir_env_var_cases() {
        // Use a mutex to serialise access to the env var.  This is a
        // process-global resource shared between test threads.
        use std::sync::Mutex;
        static ENV_LOCK: Mutex<()> = Mutex::new(());
        let _guard = ENV_LOCK.lock().expect("env lock poisoned");

        // Valid directory
        let tmp = std::env::temp_dir();
        let tmp_str = tmp.to_str().expect("temp dir not utf-8");
        unsafe { std::env::set_var("SECOND_BACKEND_DIR", tmp_str) };
        let result = find_backend_dir();
        unsafe { std::env::remove_var("SECOND_BACKEND_DIR") };
        assert!(result.is_ok(), "expected Ok, got: {result:?}");
        assert_eq!(result.unwrap(), tmp_str);

        // Invalid directory
        unsafe { std::env::set_var("SECOND_BACKEND_DIR", "/no/such/dir/xyz") };
        let result = find_backend_dir();
        unsafe { std::env::remove_var("SECOND_BACKEND_DIR") };
        assert!(result.is_err(), "expected Err, got: {result:?}");
        assert!(result.unwrap_err().contains("does not exist"));
    }
}
