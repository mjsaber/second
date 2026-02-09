export type Page = 'recording' | 'summaries' | 'settings';

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

export interface SummaryEntry {
  id: number;
  date: string;
  speakerName: string;
  preview: string;
}

export interface AppSettings {
  llmProvider: 'claude' | 'openai' | 'gemini' | 'ollama';
  apiKey: string;
  audioDevice: string;
  audioRetention: 'keep' | 'delete';
}
