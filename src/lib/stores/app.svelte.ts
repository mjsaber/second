import type { Page, TranscriptSegment } from '../types/index.js';

export const appState = $state({
  currentPage: 'recording' as Page,
  isRecording: false,
  recordingDuration: 0,
  transcript: [] as TranscriptSegment[],
  sidecarConnected: false,
});
