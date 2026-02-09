import type {
  Page,
  ProcessingState,
  TranscriptSegment,
  Meeting,
  DetectedSpeaker,
  AppSettings,
} from '../types/index.js';

export const appState = $state({
  currentPage: 'recording' as Page,
  sidecarConnected: false,

  // Recording state
  isRecording: false,
  recordingDuration: 0,
  processingState: 'idle' as ProcessingState,
  currentMeeting: null as Meeting | null,
  transcript: [] as TranscriptSegment[],

  // Speaker labeling state (after diarization)
  detectedSpeakers: [] as DetectedSpeaker[],
  showLabelingModal: false,

  // Settings (loaded from DB on mount)
  settings: {
    llmProvider: 'claude',
    modelName: '',
    apiKey: '',
    audioDevice: 'default',
    audioRetention: 'keep',
  } as AppSettings,
});
