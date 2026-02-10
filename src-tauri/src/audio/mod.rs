//! Audio capture module for recording microphone input to WAV files.
//!
//! Provides device enumeration, audio capture via CPAL, and WAV writing via
//! hound. The capture runs on a dedicated thread and communicates with the
//! main thread through shared state protected by `Arc<Mutex<>>`.

pub mod capture;
pub mod devices;
