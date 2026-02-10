//! Audio input device enumeration using CPAL.

use cpal::traits::{DeviceTrait, HostTrait};

/// Information about an available audio input device.
#[derive(Debug, Clone, serde::Serialize)]
pub struct AudioDevice {
    pub name: String,
}

/// List all available audio input devices.
///
/// Returns a vector of [`AudioDevice`] structs, one for each input device
/// reported by the default CPAL host. Devices whose names cannot be read
/// are silently skipped.
///
/// # Errors
/// Returns an error if the CPAL host cannot enumerate input devices.
pub fn list_input_devices() -> Result<Vec<AudioDevice>, String> {
    let host = cpal::default_host();
    let devices = host
        .input_devices()
        .map_err(|e| format!("Failed to enumerate input devices: {e}"))?;

    let mut result = Vec::new();
    for device in devices {
        if let Ok(name) = device.name() {
            result.push(AudioDevice { name });
        }
    }

    Ok(result)
}

/// Find an input device by name, or return the default input device.
///
/// When `device_name` is `None`, the default input device is returned.
/// When a name is provided, the first device whose name matches exactly is
/// returned.
///
/// # Errors
/// Returns an error if no matching device can be found or if CPAL cannot
/// enumerate devices.
pub fn find_input_device(device_name: Option<&str>) -> Result<cpal::Device, String> {
    let host = cpal::default_host();

    match device_name {
        None => host
            .default_input_device()
            .ok_or_else(|| "No default input device available".to_string()),
        Some(name) => {
            let devices = host
                .input_devices()
                .map_err(|e| format!("Failed to enumerate input devices: {e}"))?;

            for device in devices {
                if let Ok(device_name) = device.name() {
                    if device_name == name {
                        return Ok(device);
                    }
                }
            }

            Err(format!("Input device '{name}' not found"))
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Device listing should not panic even when no audio devices are
    /// available (e.g. headless CI). It either succeeds with a list or
    /// returns a descriptive error.
    /// Requires real audio hardware — run with `cargo test -- --ignored`.
    #[test]
    #[ignore]
    fn test_list_input_devices_does_not_panic() {
        match list_input_devices() {
            Ok(devices) => {
                // Each returned device should have a non-empty name.
                for d in &devices {
                    assert!(!d.name.is_empty(), "device name should not be empty");
                }
            }
            Err(e) => {
                // Acceptable on headless systems.
                assert!(
                    !e.is_empty(),
                    "error message should not be empty"
                );
            }
        }
    }

    /// Requesting a device by a name that almost certainly doesn't exist
    /// should return a clear "not found" error.
    /// Requires real audio hardware — run with `cargo test -- --ignored`.
    #[test]
    #[ignore]
    fn test_find_device_nonexistent_returns_error() {
        let result = find_input_device(Some("__nonexistent_device_12345__"));
        assert!(result.is_err());
        let err = result.err().expect("expected Err variant");
        assert!(
            err.contains("not found"),
            "expected 'not found' in error, got: {err}"
        );
    }

    /// Requesting the default device should either succeed or return a
    /// descriptive error (e.g. on headless CI with no audio hardware).
    #[test]
    fn test_find_default_device_does_not_panic() {
        match find_input_device(None) {
            Ok(device) => {
                // Sanity-check: the device should have a readable name.
                assert!(device.name().is_ok());
            }
            Err(e) => {
                assert!(
                    e.contains("No default input device"),
                    "unexpected error: {e}"
                );
            }
        }
    }

    /// AudioDevice should serialize to JSON with a `name` field.
    #[test]
    fn test_audio_device_serialization() {
        let device = AudioDevice {
            name: "Built-in Microphone".to_string(),
        };
        let json = serde_json::to_value(&device).expect("serialize");
        assert_eq!(json["name"], "Built-in Microphone");
    }
}
