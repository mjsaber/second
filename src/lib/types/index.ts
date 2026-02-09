export type Page = 'recording' | 'summaries' | 'settings';

export type ProcessingState =
  | 'idle'
  | 'recording'
  | 'diarizing'
  | 'labeling'
  | 'summarizing'
  | 'complete';

export interface TranscriptSegment {
  text: string;
  start: number;
  end: number;
  speaker?: string;
}

export interface Speaker {
  id: number;
  name: string;
  meetingCount: number;
}

export interface Meeting {
  id: number;
  title: string;
  status: 'recording' | 'processing' | 'completed';
  startedAt: string;
  endedAt?: string;
  audioPath?: string;
}

export interface DetectedSpeaker {
  label: string;
  suggestedName: string | null;
  confidence: number;
  excerpts: string[];
}

export interface SummaryEntry {
  id: number;
  date: string;
  speakerName: string;
  preview: string;
}

export interface SummaryDetail {
  id: number;
  meetingId: number;
  provider: string;
  model: string;
  content: string;
  filePath?: string;
  createdAt: string;
}

export interface AppSettings {
  llmProvider: 'claude' | 'openai' | 'gemini' | 'ollama';
  modelName: string;
  apiKey: string;
  audioDevice: string;
  audioRetention: 'keep' | 'delete';
}
