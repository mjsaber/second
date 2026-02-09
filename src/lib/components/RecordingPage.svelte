<script lang="ts">
  import { appState } from '../stores/app.svelte.js';
  import type { ProcessingState, TranscriptSegment, DetectedSpeaker } from '../types/index.js';
  import {
    startSidecar,
    stopSidecar,
    sendToSidecar,
    diarize,
    summarize,
  } from '../services/sidecar.js';

  let timerInterval: ReturnType<typeof setInterval> | null = $state(null);
  let labelingInterval: ReturnType<typeof setInterval> | null = $state(null);
  let alive = $state(true);
  let errorMessage = $state('');
  let transcriptContainer: HTMLDivElement | undefined = $state(undefined);
  let isStarting = $state(false);

  // ---------- Derived state ----------

  let statusLabel = $derived(
    appState.processingState === 'idle'
      ? 'Ready'
      : appState.processingState === 'recording'
        ? 'Recording'
        : 'Processing'
  );

  let statusKind = $derived(
    appState.processingState === 'recording'
      ? 'recording' as const
      : appState.processingState !== 'idle'
        ? 'processing' as const
        : 'idle' as const
  );

  let minutes = $derived(Math.floor(appState.recordingDuration / 60));
  let seconds = $derived(appState.recordingDuration % 60);
  let formattedDuration = $derived(
    `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  );

  let processingDescription = $derived(
    appState.processingState === 'diarizing'
      ? 'Identifying speakers...'
      : appState.processingState === 'labeling'
        ? 'Waiting for speaker labels...'
        : appState.processingState === 'summarizing'
          ? 'Generating summary...'
          : appState.processingState === 'complete'
            ? 'Processing complete!'
            : ''
  );

  let isProcessing = $derived(
    appState.processingState === 'diarizing' ||
    appState.processingState === 'summarizing'
  );

  let canStartRecording = $derived(
    !appState.isRecording &&
    appState.processingState === 'idle' &&
    !isStarting
  );

  // ---------- Auto-scroll transcript ----------

  $effect(() => {
    // Re-run whenever transcript length changes
    const _len = appState.transcript.length;
    if (transcriptContainer) {
      transcriptContainer.scrollTop = transcriptContainer.scrollHeight;
    }
  });

  // ---------- Cleanup on unmount ----------

  $effect(() => {
    return () => {
      alive = false;
      if (timerInterval) {
        clearInterval(timerInterval);
      }
      if (labelingInterval) {
        clearInterval(labelingInterval);
      }
    };
  });

  // ---------- Actions ----------

  function clearError(): void {
    errorMessage = '';
  }

  async function handleStartRecording(): Promise<void> {
    clearError();
    isStarting = true;

    try {
      // Connect to sidecar if not already connected
      if (!appState.sidecarConnected) {
        await startSidecar();
        appState.sidecarConnected = true;
      }

      // Tell the sidecar to begin recording
      await sendToSidecar({ type: 'start_recording', device: appState.settings.audioDevice });

      // Update state
      appState.isRecording = true;
      appState.recordingDuration = 0;
      appState.transcript = [];
      appState.processingState = 'recording';
      appState.currentMeeting = {
        id: Date.now(),
        title: `Meeting ${new Date().toLocaleString()}`,
        status: 'recording',
        startedAt: new Date().toISOString(),
      };

      // Start the timer
      timerInterval = setInterval(() => {
        appState.recordingDuration += 1;
      }, 1000);

      // Start polling for transcript segments
      pollTranscript();
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : String(err);
      appState.isRecording = false;
      appState.processingState = 'idle';
      appState.sidecarConnected = false;
    } finally {
      isStarting = false;
    }
  }

  async function pollTranscript(): Promise<void> {
    while (appState.isRecording && alive) {
      try {
        const response = await sendToSidecar({ type: 'get_transcript' });
        if (response.segments && Array.isArray(response.segments)) {
          const newSegments = response.segments as TranscriptSegment[];
          if (newSegments.length > appState.transcript.length) {
            appState.transcript = newSegments;
          }
        }
      } catch {
        // Ignore polling errors while recording — the sidecar may just
        // not have new data yet.
      }
      // Poll every 1 second
      await new Promise((r) => setTimeout(r, 1000));
    }
  }

  async function handleStopRecording(): Promise<void> {
    clearError();

    // Stop the timer
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }

    appState.isRecording = false;

    try {
      // Tell sidecar to stop recording and get the audio path
      const stopResponse = await sendToSidecar({ type: 'stop_recording' });
      const audioPath = (stopResponse.audio_path as string) ?? '';

      // Update meeting
      if (appState.currentMeeting) {
        appState.currentMeeting = {
          ...appState.currentMeeting,
          status: 'processing',
          endedAt: new Date().toISOString(),
          audioPath,
        };
      }

      // ---- Diarization ----
      appState.processingState = 'diarizing';

      const diarizeResult = await diarize(audioPath);

      // Update transcript with speaker-assigned segments
      if (diarizeResult.segments && Array.isArray(diarizeResult.segments)) {
        appState.transcript = diarizeResult.segments as TranscriptSegment[];
      }

      // Parse detected speakers for labeling
      if (diarizeResult.speakers && Array.isArray(diarizeResult.speakers)) {
        appState.detectedSpeakers = diarizeResult.speakers as DetectedSpeaker[];
      } else {
        // Build from unique speaker labels in transcript
        const speakerLabels = new Set<string>();
        for (const seg of appState.transcript) {
          if (seg.speaker) speakerLabels.add(seg.speaker);
        }
        appState.detectedSpeakers = Array.from(speakerLabels).map((label) => ({
          label,
          suggestedName: null,
          confidence: 0,
          excerpts: appState.transcript
            .filter((s) => s.speaker === label)
            .slice(0, 3)
            .map((s) => s.text),
        }));
      }

      // ---- Speaker Labeling ----
      appState.processingState = 'labeling';
      appState.showLabelingModal = true;

      // Wait for the user to finish labeling (the modal sets showLabelingModal = false)
      await waitForLabeling();

      // ---- Summarization ----
      appState.processingState = 'summarizing';

      const fullTranscript = appState.transcript
        .map((seg) => (seg.speaker ? `${seg.speaker}: ${seg.text}` : seg.text))
        .join('\n');

      await summarize(
        fullTranscript,
        appState.settings.llmProvider,
        appState.settings.modelName,
        appState.settings.apiKey,
      );

      // ---- Complete ----
      appState.processingState = 'complete';

      if (appState.currentMeeting) {
        appState.currentMeeting = {
          ...appState.currentMeeting,
          status: 'completed',
        };
      }
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : String(err);
      appState.processingState = 'idle';
    }
  }

  function waitForLabeling(): Promise<void> {
    return new Promise((resolve) => {
      labelingInterval = setInterval(() => {
        if (!appState.showLabelingModal) {
          if (labelingInterval) clearInterval(labelingInterval);
          labelingInterval = null;
          resolve();
        }
      }, 200);
    });
  }

  function dismissComplete(): void {
    appState.processingState = 'idle';
    appState.currentMeeting = null;
  }
</script>

<div class="recording-page">
  <!-- Header -->
  <div class="recording-header">
    <h2>Recording</h2>
    <span
      class="status-badge"
      class:recording={statusKind === 'recording'}
      class:processing={statusKind === 'processing'}
    >
      {statusLabel}
    </span>
  </div>

  <!-- Error banner -->
  {#if errorMessage}
    <div class="error-banner">
      <span class="error-text">{errorMessage}</span>
      <button class="error-dismiss" onclick={clearError} type="button">Dismiss</button>
    </div>
  {/if}

  <!-- Controls card -->
  <div class="recording-controls">
    <div class="timer">{formattedDuration}</div>

    {#if canStartRecording}
      <button
        class="record-button"
        onclick={handleStartRecording}
      >
        Start Recording
      </button>
    {:else if appState.isRecording}
      <button
        class="record-button recording"
        onclick={handleStopRecording}
      >
        Stop Recording
      </button>
    {:else if isStarting}
      <button class="record-button" disabled>
        Connecting...
      </button>
    {/if}
  </div>

  <!-- Processing progress -->
  {#if appState.processingState !== 'idle' && appState.processingState !== 'recording'}
    <div class="processing-section">
      <h3>Processing</h3>
      <div class="processing-steps">
        <div class="step" class:active={appState.processingState === 'diarizing'} class:done={['labeling', 'summarizing', 'complete'].includes(appState.processingState)}>
          <span class="step-indicator">
            {#if appState.processingState === 'diarizing'}
              <span class="spinner"></span>
            {:else if ['labeling', 'summarizing', 'complete'].includes(appState.processingState)}
              <span class="checkmark">&#10003;</span>
            {:else}
              <span class="step-dot"></span>
            {/if}
          </span>
          <span class="step-label">Identify speakers</span>
        </div>

        <div class="step" class:active={appState.processingState === 'labeling'} class:done={['summarizing', 'complete'].includes(appState.processingState)}>
          <span class="step-indicator">
            {#if appState.processingState === 'labeling'}
              <span class="spinner"></span>
            {:else if ['summarizing', 'complete'].includes(appState.processingState)}
              <span class="checkmark">&#10003;</span>
            {:else}
              <span class="step-dot"></span>
            {/if}
          </span>
          <span class="step-label">Label speakers</span>
        </div>

        <div class="step" class:active={appState.processingState === 'summarizing'} class:done={appState.processingState === 'complete'}>
          <span class="step-indicator">
            {#if appState.processingState === 'summarizing'}
              <span class="spinner"></span>
            {:else if appState.processingState === 'complete'}
              <span class="checkmark">&#10003;</span>
            {:else}
              <span class="step-dot"></span>
            {/if}
          </span>
          <span class="step-label">Generate summary</span>
        </div>
      </div>

      {#if processingDescription}
        <p class="processing-description">{processingDescription}</p>
      {/if}

      {#if appState.processingState === 'complete'}
        <button class="done-button" onclick={dismissComplete}>
          Done
        </button>
      {/if}
    </div>
  {/if}

  <!-- Live transcript -->
  <div class="transcript-area">
    <h3>Live Transcript</h3>
    <div class="transcript-scroll" bind:this={transcriptContainer}>
      {#if appState.transcript.length === 0}
        <p class="transcript-placeholder">
          {#if appState.isRecording}
            Waiting for speech...
          {:else if appState.processingState !== 'idle'}
            Processing transcript...
          {:else}
            Transcript will appear here when recording starts.
          {/if}
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

  /* ---------- Header ---------- */

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

  .status-badge.recording {
    background-color: #fee2e2;
    color: #dc2626;
    border-color: #fca5a5;
    animation: pulse-recording 2s ease-in-out infinite;
  }

  @media (prefers-color-scheme: dark) {
    .status-badge.recording {
      background-color: #450a0a;
      color: #fca5a5;
      border-color: #7f1d1d;
    }
  }

  .status-badge.processing {
    background-color: #dbeafe;
    color: #2563eb;
    border-color: #93c5fd;
  }

  @media (prefers-color-scheme: dark) {
    .status-badge.processing {
      background-color: #172554;
      color: #93c5fd;
      border-color: #1e3a8a;
    }
  }

  @keyframes pulse-recording {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  /* ---------- Error banner ---------- */

  .error-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 16px;
    background-color: #fef2f2;
    border: 1px solid #fca5a5;
    border-radius: 8px;
    color: #dc2626;
  }

  @media (prefers-color-scheme: dark) {
    .error-banner {
      background-color: #450a0a;
      border-color: #7f1d1d;
      color: #fca5a5;
    }
  }

  .error-text {
    font-size: 0.875rem;
    line-height: 1.4;
  }

  .error-dismiss {
    flex-shrink: 0;
    padding: 4px 12px;
    border: 1px solid currentColor;
    border-radius: 6px;
    background: none;
    color: inherit;
    font-size: 0.75rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    opacity: 0.8;
    transition: opacity 0.1s ease;
  }

  .error-dismiss:hover {
    opacity: 1;
  }

  /* ---------- Controls card ---------- */

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
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.15s ease, transform 0.1s ease;
    background-color: #2563eb;
    color: #ffffff;
  }

  .record-button:hover:not(:disabled) {
    background-color: #1d4ed8;
  }

  .record-button:active:not(:disabled) {
    transform: scale(0.98);
  }

  .record-button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .record-button.recording {
    background-color: #dc2626;
  }

  .record-button.recording:hover {
    background-color: #b91c1c;
  }

  /* ---------- Processing section ---------- */

  .processing-section {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px 24px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
  }

  .processing-section h3 {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
  }

  .processing-steps {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .step {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }

  .step.active {
    color: #2563eb;
    font-weight: 500;
  }

  .step.done {
    color: #16a34a;
  }

  @media (prefers-color-scheme: dark) {
    .step.active {
      color: #93c5fd;
    }
    .step.done {
      color: #4ade80;
    }
  }

  .step-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .step-dot {
    display: block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: var(--color-border);
  }

  .checkmark {
    font-size: 0.875rem;
    font-weight: 700;
    line-height: 1;
  }

  .spinner {
    display: block;
    width: 16px;
    height: 16px;
    border: 2px solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .processing-description {
    margin: 0;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    font-style: italic;
  }

  .done-button {
    align-self: flex-start;
    padding: 8px 20px;
    border-radius: 8px;
    border: none;
    background-color: #2563eb;
    color: #ffffff;
    font-size: 0.8125rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.15s ease, transform 0.1s ease;
  }

  .done-button:hover {
    background-color: #1d4ed8;
  }

  .done-button:active {
    transform: scale(0.98);
  }

  /* ---------- Transcript area ---------- */

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

  @media (prefers-color-scheme: dark) {
    .speaker-label {
      color: #93c5fd;
    }
  }

  .segment-text {
    color: var(--color-text);
  }
</style>
