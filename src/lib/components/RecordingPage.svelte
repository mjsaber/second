<script lang="ts">
  import { appState } from '../stores/app.svelte.js';

  let timerInterval: ReturnType<typeof setInterval> | null = $state(null);

  let status = $derived(
    appState.isRecording ? 'Recording...' : 'Ready'
  );

  let minutes = $derived(Math.floor(appState.recordingDuration / 60));
  let seconds = $derived(appState.recordingDuration % 60);
  let formattedDuration = $derived(
    `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  );

  function toggleRecording(): void {
    if (appState.isRecording) {
      // Stop recording
      appState.isRecording = false;
      if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
      }
    } else {
      // Start recording
      appState.isRecording = true;
      appState.recordingDuration = 0;
      appState.transcript = [];
      timerInterval = setInterval(() => {
        appState.recordingDuration += 1;
      }, 1000);
    }
  }

  $effect(() => {
    return () => {
      if (timerInterval) {
        clearInterval(timerInterval);
      }
    };
  });
</script>

<div class="recording-page">
  <div class="recording-header">
    <h2>Recording</h2>
    <span class="status-badge" class:active={appState.isRecording}>
      {status}
    </span>
  </div>

  <div class="recording-controls">
    <div class="timer">{formattedDuration}</div>
    <button
      class="record-button"
      class:recording={appState.isRecording}
      onclick={toggleRecording}
    >
      {appState.isRecording ? 'Stop Recording' : 'Start Recording'}
    </button>
  </div>

  <div class="transcript-area">
    <h3>Live Transcript</h3>
    <div class="transcript-scroll">
      {#if appState.transcript.length === 0}
        <p class="transcript-placeholder">
          {appState.isRecording
            ? 'Waiting for speech...'
            : 'Transcript will appear here when recording starts.'}
        </p>
      {:else}
        {#each appState.transcript as segment}
          <div class="transcript-segment">
            {#if segment.speaker}
              <span class="speaker-label">{segment.speaker}:</span>
            {/if}
            <span class="segment-text">{segment.text}</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</div>

<style>
  .recording-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 24px;
  }

  .recording-header {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .recording-header h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
  }

  .status-badge {
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    background-color: var(--color-surface);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);
  }

  .status-badge.active {
    background-color: #fee2e2;
    color: #dc2626;
    border-color: #fca5a5;
  }

  :global([data-theme='dark']) .status-badge.active {
    background-color: #450a0a;
    color: #fca5a5;
    border-color: #7f1d1d;
  }

  .recording-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 32px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
  }

  .timer {
    font-size: 3rem;
    font-weight: 300;
    font-variant-numeric: tabular-nums;
    color: var(--color-text);
    letter-spacing: 0.05em;
  }

  .record-button {
    padding: 12px 32px;
    border-radius: 8px;
    border: none;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s ease, transform 0.1s ease;
    background-color: #2563eb;
    color: #ffffff;
  }

  .record-button:hover {
    background-color: #1d4ed8;
  }

  .record-button:active {
    transform: scale(0.98);
  }

  .record-button.recording {
    background-color: #dc2626;
  }

  .record-button.recording:hover {
    background-color: #b91c1c;
  }

  .transcript-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .transcript-area h3 {
    margin: 0 0 12px 0;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
  }

  .transcript-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
    min-height: 200px;
  }

  .transcript-placeholder {
    color: var(--color-text-secondary);
    font-style: italic;
    margin: 0;
  }

  .transcript-segment {
    padding: 6px 0;
    line-height: 1.5;
  }

  .speaker-label {
    font-weight: 600;
    color: #2563eb;
    margin-right: 6px;
  }

  .segment-text {
    color: var(--color-text);
  }
</style>
