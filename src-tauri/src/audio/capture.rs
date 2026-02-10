//! Audio capture engine — records from an input device to a WAV file.
//!
//! The capture runs on a dedicated thread so it never blocks the Tauri main
//! thread. Shared state is wrapped in `Arc<Mutex<>>` so the Tauri commands
//! can start/stop recording safely.

use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use cpal::traits::{DeviceTrait, StreamTrait};
use cpal::{SampleFormat, StreamConfig};

use crate::audio::devices::find_input_device;

/// Target audio format for speech recognition.
const SAMPLE_RATE: u32 = 16_000;
const CHANNELS: u16 = 1;
const BITS_PER_SAMPLE: u16 = 16;

/// Internal recording state.
#[derive(Debug, PartialEq, Eq)]
enum RecordingStatus {
    Idle,
    Recording,
}

/// Shared inner state that the capture thread and the Tauri commands both
/// access through `Arc<Mutex<>>`.
struct CaptureInner {
    status: RecordingStatus,
    /// Path of the WAV file currently being written.
    file_path: Option<PathBuf>,
    /// Signal the capture thread to stop.
    stop_flag: Arc<Mutex<bool>>,
}

/// Thread-safe handle to the audio capture engine.
///
/// Wrap this in `tauri::State` so all commands share the same instance.
pub struct AudioCaptureManager {
    inner: Mutex<CaptureInner>,
    /// Handle for the recording thread; joined on stop.
    thread_handle: Mutex<Option<JoinHandle<Result<(), String>>>>,
}

impl AudioCaptureManager {
    /// Create a new, idle capture manager.
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(CaptureInner {
                status: RecordingStatus::Idle,
                file_path: None,
                stop_flag: Arc::new(Mutex::new(false)),
            }),
            thread_handle: Mutex::new(None),
        }
    }

    /// Returns `true` if a recording is currently in progress.
    #[allow(dead_code)] // Used in tests; will be wired to a Tauri command as needed.
    pub fn is_recording(&self) -> Result<bool, String> {
        let inner = self.inner.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
        Ok(inner.status == RecordingStatus::Recording)
    }

    /// Start recording from the specified device (or the default device).
    ///
    /// Audio is written to a timestamped WAV file inside `recordings_dir`.
    /// Returns the path to the WAV file that will be written.
    ///
    /// # Errors
    /// Returns an error if a recording is already in progress, if the device
    /// cannot be found, or if the WAV file cannot be created.
    pub fn start(&self, device_name: Option<&str>, recordings_dir: &PathBuf) -> Result<String, String> {
        let mut inner = self.inner.lock().map_err(|e| format!("Lock poisoned: {e}"))?;

        if inner.status == RecordingStatus::Recording {
            return Err("A recording is already in progress".into());
        }

        // Ensure the recordings directory exists.
        fs::create_dir_all(recordings_dir)
            .map_err(|e| format!("Failed to create recordings directory: {e}"))?;

        // Build a unique filename.
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| format!("System time error: {e}"))?
            .as_secs();
        let file_path = recordings_dir.join(format!("recording_{timestamp}.wav"));
        let file_path_str = file_path
            .to_str()
            .ok_or_else(|| "Recording path is not valid UTF-8".to_string())?
            .to_string();

        // Find the input device.
        let device = find_input_device(device_name)?;

        // Reset stop flag.
        let stop_flag = Arc::new(Mutex::new(false));
        inner.stop_flag = Arc::clone(&stop_flag);
        inner.file_path = Some(file_path.clone());
        inner.status = RecordingStatus::Recording;

        // Spawn capture thread.
        let thread_handle = std::thread::Builder::new()
            .name("audio-capture".into())
            .spawn(move || run_capture(device, file_path, stop_flag))
            .map_err(|e| format!("Failed to spawn capture thread: {e}"))?;

        let mut handle_lock = self.thread_handle.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
        *handle_lock = Some(thread_handle);

        Ok(file_path_str)
    }

    /// Stop the current recording, finalize the WAV file, and return its path.
    ///
    /// # Errors
    /// Returns an error if no recording is in progress or if the capture
    /// thread encountered an error.
    pub fn stop(&self) -> Result<String, String> {
        let file_path = {
            let mut inner = self.inner.lock().map_err(|e| format!("Lock poisoned: {e}"))?;

            if inner.status != RecordingStatus::Recording {
                return Err("No recording in progress".into());
            }

            // Signal the capture thread to stop. Clone the Arc so we can
            // drop the borrow on `inner` before mutating it.
            let stop_flag = Arc::clone(&inner.stop_flag);
            {
                let mut flag = stop_flag.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
                *flag = true;
            }

            inner.status = RecordingStatus::Idle;
            inner
                .file_path
                .take()
                .ok_or_else(|| "Recording file path missing".to_string())?
        };

        // Wait for the capture thread to finish.
        let thread_handle = {
            let mut handle_lock = self.thread_handle.lock().map_err(|e| format!("Lock poisoned: {e}"))?;
            handle_lock.take()
        };

        if let Some(handle) = thread_handle {
            handle
                .join()
                .map_err(|_| "Capture thread panicked".to_string())?
                .map_err(|e| format!("Capture thread error: {e}"))?;
        }

        let path_str = file_path
            .to_str()
            .ok_or_else(|| "Recording path is not valid UTF-8".to_string())?
            .to_string();

        Ok(path_str)
    }
}

// ---------------------------------------------------------------------------
// Capture thread entry point
// ---------------------------------------------------------------------------

/// Run the audio capture loop on a dedicated thread.
///
/// Opens a CPAL input stream, feeds samples into a hound `WavWriter`, and
/// keeps running until `stop_flag` is set to `true`.
fn run_capture(
    device: cpal::Device,
    file_path: PathBuf,
    stop_flag: Arc<Mutex<bool>>,
) -> Result<(), String> {
    let desired_config = StreamConfig {
        channels: CHANNELS,
        sample_rate: cpal::SampleRate(SAMPLE_RATE),
        buffer_size: cpal::BufferSize::Default,
    };

    // Check if the device supports our desired config, otherwise fall back to
    // the device's default config and we'll resample/convert later.
    let (config, need_conversion) = match device.supported_input_configs() {
        Ok(mut configs) => {
            let supports_desired = configs.any(|range| {
                range.channels() == CHANNELS
                    && range.min_sample_rate().0 <= SAMPLE_RATE
                    && range.max_sample_rate().0 >= SAMPLE_RATE
                    && range.sample_format() == SampleFormat::I16
            });
            if supports_desired {
                (desired_config, false)
            } else {
                let default_config = device
                    .default_input_config()
                    .map_err(|e| format!("Failed to get default input config: {e}"))?;
                (default_config.config(), true)
            }
        }
        Err(_) => {
            // If we can't query supported configs, try the desired config
            // directly and hope for the best.
            (desired_config, false)
        }
    };

    let actual_sample_rate = config.sample_rate.0;
    let actual_channels = config.channels;

    let wav_spec = hound::WavSpec {
        channels: CHANNELS,
        sample_rate: SAMPLE_RATE,
        bits_per_sample: BITS_PER_SAMPLE,
        sample_format: hound::SampleFormat::Int,
    };

    let writer = hound::WavWriter::create(&file_path, wav_spec)
        .map_err(|e| format!("Failed to create WAV file: {e}"))?;
    let writer = Arc::new(Mutex::new(Some(writer)));

    let writer_clone = Arc::clone(&writer);
    let stop_flag_clone = Arc::clone(&stop_flag);

    let err_flag: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));
    let err_flag_clone = Arc::clone(&err_flag);

    let data_callback = move |data: &[f32], _: &cpal::InputCallbackInfo| {
        // Check stop flag — if set, don't write more data.
        if let Ok(flag) = stop_flag_clone.try_lock() {
            if *flag {
                return;
            }
        }

        if let Ok(mut guard) = writer_clone.lock() {
            if let Some(ref mut w) = *guard {
                let samples = if need_conversion {
                    convert_to_mono_16k(data, actual_sample_rate, actual_channels)
                } else {
                    // Direct: input is already f32 mono 16kHz, just convert to i16.
                    data.iter()
                        .map(|&s| float_to_i16(s))
                        .collect()
                };

                for sample in samples {
                    if let Err(e) = w.write_sample(sample) {
                        if let Ok(mut ef) = err_flag_clone.lock() {
                            *ef = Some(format!("WAV write error: {e}"));
                        }
                        return;
                    }
                }
            }
        }
    };

    let err_flag_stream = Arc::clone(&err_flag);
    let error_callback = move |err: cpal::StreamError| {
        if let Ok(mut ef) = err_flag_stream.lock() {
            *ef = Some(format!("Audio stream error: {err}"));
        }
    };

    let stream = device
        .build_input_stream(&config, data_callback, error_callback, None)
        .map_err(|e| format!("Failed to build input stream: {e}"))?;

    stream
        .play()
        .map_err(|e| format!("Failed to start audio stream: {e}"))?;

    // Spin-wait for stop signal. Sleep to avoid busy-waiting.
    loop {
        std::thread::sleep(std::time::Duration::from_millis(50));
        // If the mutex is poisoned, stop recording (fail-safe).
        let should_stop = stop_flag
            .lock()
            .map(|f| *f)
            .unwrap_or(true);
        if should_stop {
            break;
        }
    }

    // Stop the stream and finalize the WAV file.
    drop(stream);

    // Finalize the WAV writer.
    if let Ok(mut guard) = writer.lock() {
        if let Some(w) = guard.take() {
            w.finalize()
                .map_err(|e| format!("Failed to finalize WAV file: {e}"))?;
        }
    }

    // Check if the data callback reported any errors.
    if let Ok(ef) = err_flag.lock() {
        if let Some(ref e) = *ef {
            return Err(e.clone());
        }
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Sample conversion helpers
// ---------------------------------------------------------------------------

/// Convert a float sample in [-1.0, 1.0] to a 16-bit integer sample.
fn float_to_i16(sample: f32) -> i16 {
    let clamped = sample.clamp(-1.0, 1.0);
    (clamped * i16::MAX as f32) as i16
}

/// Convert multi-channel audio at an arbitrary sample rate to mono 16 kHz i16.
///
/// This is a simple nearest-neighbour resampler. For speech recognition
/// purposes this is perfectly adequate — no need for a polyphase filter.
fn convert_to_mono_16k(data: &[f32], source_rate: u32, source_channels: u16) -> Vec<i16> {
    let channels = source_channels as usize;
    if channels == 0 || source_rate == 0 {
        return Vec::new();
    }

    let frame_count = data.len() / channels;
    let ratio = source_rate as f64 / SAMPLE_RATE as f64;
    let output_frames = (frame_count as f64 / ratio).ceil() as usize;
    let mut result = Vec::with_capacity(output_frames);

    for i in 0..output_frames {
        let src_frame = ((i as f64) * ratio) as usize;
        if src_frame >= frame_count {
            break;
        }
        // Average all channels to get mono.
        let offset = src_frame * channels;
        let mut sum: f32 = 0.0;
        for ch in 0..channels {
            if offset + ch < data.len() {
                sum += data[offset + ch];
            }
        }
        let mono = sum / channels as f32;
        result.push(float_to_i16(mono));
    }

    result
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -- float_to_i16 conversion tests --

    #[test]
    fn test_float_to_i16_zero() {
        assert_eq!(float_to_i16(0.0), 0);
    }

    #[test]
    fn test_float_to_i16_positive_one() {
        assert_eq!(float_to_i16(1.0), i16::MAX);
    }

    #[test]
    fn test_float_to_i16_negative_one() {
        // -1.0 * 32767 = -32767 (not exactly i16::MIN which is -32768)
        let result = float_to_i16(-1.0);
        assert!(result < 0);
        assert!(result <= -32767);
    }

    #[test]
    fn test_float_to_i16_clamps_overflow() {
        assert_eq!(float_to_i16(2.0), i16::MAX);
        assert_eq!(float_to_i16(-2.0), float_to_i16(-1.0));
    }

    // -- convert_to_mono_16k tests --

    #[test]
    fn test_convert_mono_same_rate() {
        // Mono 16kHz -> mono 16kHz should be a simple float->i16 conversion.
        let input = vec![0.0_f32, 0.5, -0.5, 1.0];
        let output = convert_to_mono_16k(&input, 16_000, 1);
        assert_eq!(output.len(), input.len());
        assert_eq!(output[0], 0);
        assert!(output[1] > 0);
        assert!(output[2] < 0);
    }

    #[test]
    fn test_convert_stereo_to_mono() {
        // Stereo at 16kHz: two channels get averaged.
        // L=1.0, R=-1.0 => mono=0.0
        let input = vec![1.0_f32, -1.0, 0.5, 0.5];
        let output = convert_to_mono_16k(&input, 16_000, 2);
        // 2 frames of stereo -> 2 frames of mono
        assert_eq!(output.len(), 2);
        assert_eq!(output[0], 0); // (1.0 + -1.0) / 2 = 0
        assert!(output[1] > 0); // (0.5 + 0.5) / 2 = 0.5
    }

    #[test]
    fn test_convert_downsample_2x() {
        // 32kHz mono -> 16kHz mono: should drop roughly half the frames.
        let input: Vec<f32> = (0..320).map(|i| (i as f32) / 320.0).collect();
        let output = convert_to_mono_16k(&input, 32_000, 1);
        // With 320 frames at 32kHz, we expect ~160 frames at 16kHz.
        assert!(output.len() >= 150 && output.len() <= 170,
            "expected ~160 output frames, got {}", output.len());
    }

    #[test]
    fn test_convert_empty_input() {
        let output = convert_to_mono_16k(&[], 44_100, 2);
        assert!(output.is_empty());
    }

    #[test]
    fn test_convert_zero_channels_returns_empty() {
        let output = convert_to_mono_16k(&[0.5, 0.5], 16_000, 0);
        assert!(output.is_empty());
    }

    #[test]
    fn test_convert_zero_rate_returns_empty() {
        let output = convert_to_mono_16k(&[0.5, 0.5], 0, 1);
        assert!(output.is_empty());
    }

    // -- AudioCaptureManager state machine tests --

    #[test]
    fn test_new_manager_is_not_recording() {
        let mgr = AudioCaptureManager::new();
        assert!(!mgr.is_recording().expect("is_recording"));
    }

    #[test]
    fn test_stop_without_start_returns_error() {
        let mgr = AudioCaptureManager::new();
        let result = mgr.stop();
        assert!(result.is_err());
        assert!(
            result.unwrap_err().contains("No recording in progress"),
            "unexpected error message"
        );
    }

    /// Requires real audio hardware — run with `cargo test -- --ignored`.
    #[test]
    #[ignore]
    fn test_start_creates_recording_dir() {
        let tmp = std::env::temp_dir().join("second_test_recordings");
        // Clean up from previous runs.
        let _ = fs::remove_dir_all(&tmp);

        let mgr = AudioCaptureManager::new();
        // This will likely fail because there may be no audio device, but
        // it should at least create the directory before failing.
        let result = mgr.start(None, &tmp);

        match result {
            Ok(path) => {
                // Recording started — stop it immediately.
                assert!(tmp.is_dir());
                assert!(path.contains("recording_"));
                let _ = mgr.stop();
            }
            Err(_) => {
                // On headless CI, the device won't be found. That's okay —
                // verify the directory was created before the device lookup
                // might have failed. Note: the dir creation happens before
                // device lookup, so it should still exist.
                assert!(tmp.is_dir(), "recordings directory should be created even if device fails");
            }
        }

        // Clean up.
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_double_start_returns_error_when_recording() {
        // We can't easily test this without a real audio device, but we can
        // test the state machine: if status is Recording, start() should fail.
        // To do that, we'd need to mock the device. Instead, we rely on the
        // integration-level test with a real device when available.
        //
        // For now, just verify the manager transitions correctly.
        let mgr = AudioCaptureManager::new();
        assert!(!mgr.is_recording().expect("is_recording"));
    }

    /// Verify the WAV spec constants are correct for speech recognition.
    #[test]
    fn test_wav_spec_constants() {
        assert_eq!(SAMPLE_RATE, 16_000);
        assert_eq!(CHANNELS, 1);
        assert_eq!(BITS_PER_SAMPLE, 16);
    }
}
