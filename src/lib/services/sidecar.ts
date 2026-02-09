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
