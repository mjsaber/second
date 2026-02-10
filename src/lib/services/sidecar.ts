/**
 * Tauri invoke wrappers for communicating with the Python sidecar.
 *
 * All functions call through the Rust Tauri commands defined in lib.rs,
 * which forward JSON messages to the Python backend via stdin/stdout.
 */

import { invoke } from '@tauri-apps/api/core';

/** Start the Python sidecar and verify it responds to a health check. */
export async function startSidecar(): Promise<string> {
  return invoke<string>('start_sidecar');
}

/** Stop the Python sidecar process. */
export async function stopSidecar(): Promise<void> {
  return invoke<void>('stop_sidecar');
}

/** Check if the sidecar process is running. */
export async function sidecarStatus(): Promise<boolean> {
  return invoke<boolean>('sidecar_status');
}

/** Send a health check and return the response. */
export async function sidecarHealth(): Promise<Record<string, unknown>> {
  return invoke<Record<string, unknown>>('sidecar_health');
}

/**
 * Send an arbitrary JSON message to the sidecar and return the parsed response.
 *
 * This is the low-level escape hatch. Prefer the typed wrappers below.
 */
export async function sendToSidecar(message: Record<string, unknown>): Promise<Record<string, unknown>> {
  return invoke<Record<string, unknown>>('send_to_sidecar', { message });
}

/** Request speaker identification from the sidecar. */
export async function identifySpeakers(
  embeddings: Record<string, number[]>,
  knownEmbeddings?: Record<string, number[]>,
): Promise<Record<string, unknown>> {
  const msg: Record<string, unknown> = {
    type: 'identify_speakers',
    embeddings,
  };
  if (knownEmbeddings) {
    msg.known_embeddings = knownEmbeddings;
  }
  return sendToSidecar(msg);
}

/** Request diarization of an audio file. */
export async function diarize(
  audioPath: string,
  numSpeakers?: number,
): Promise<Record<string, unknown>> {
  const msg: Record<string, unknown> = {
    type: 'diarize',
    audio_path: audioPath,
  };
  if (numSpeakers !== undefined) {
    msg.num_speakers = numSpeakers;
  }
  return sendToSidecar(msg);
}

/** Request LLM summarization of a transcript. */
export async function summarize(
  transcript: string,
  provider: string,
  model: string,
  apiKey: string,
): Promise<Record<string, unknown>> {
  return sendToSidecar({
    type: 'summarize',
    transcript,
    provider,
    model,
    api_key: apiKey,
  });
}

// ---------------------------------------------------------------------------
// Audio device commands (Rust Tauri commands)
// ---------------------------------------------------------------------------

/** List all available audio input device names. */
export async function listAudioDevices(): Promise<string[]> {
  return invoke<string[]>('list_audio_devices');
}

/** Start recording audio from the specified device (or the default device). */
export async function startAudioRecording(deviceName?: string): Promise<string> {
  return invoke<string>('start_audio_recording', { deviceName: deviceName ?? null });
}

/** Stop the current audio recording. Returns the path to the finalized WAV file. */
export async function stopAudioRecording(): Promise<string> {
  return invoke<string>('stop_audio_recording');
}

// ---------------------------------------------------------------------------
// Sidecar IPC wrappers (new handlers)
// ---------------------------------------------------------------------------

/** Persist a summary to the database and write it to disk. */
export async function saveSummary(params: {
  meetingId: number;
  provider: string;
  model: string;
  content: string;
  speakerNames: string[];
  date: string;
}): Promise<Record<string, unknown>> {
  return sendToSidecar({
    type: 'save_summary',
    meeting_id: params.meetingId,
    provider: params.provider,
    model: params.model,
    content: params.content,
    speaker_names: params.speakerNames,
    date: params.date,
  });
}

/** Fetch all speakers with their meeting counts. */
export async function getAllSpeakers(): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'get_all_speakers' });
}

/** Fetch summaries for a specific speaker by name. */
export async function getSummariesForSpeaker(speakerName: string): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'get_summaries_for_speaker', speaker_name: speakerName });
}

/** Fetch the full detail for a summary by ID. */
export async function getSummaryDetail(summaryId: number): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'get_summary_detail', summary_id: summaryId });
}

/** Search across all summaries using full-text search. */
export async function searchSummaries(query: string): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'search_summaries', query });
}

/** Persist settings to the database. */
export async function saveSettings(settings: Record<string, string>): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'save_settings', settings });
}

/** Load settings from the database. */
export async function loadSettings(): Promise<Record<string, unknown>> {
  return sendToSidecar({ type: 'load_settings' });
}
