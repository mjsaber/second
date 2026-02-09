<script lang="ts">
  import { appState } from '../stores/app.svelte.js';
  import type { DetectedSpeaker } from '../types/index.js';

  // Local state: map from speaker label to the user-assigned name
  let speakerNames = $state<Record<string, string>>({});

  // Track which suggested names the user has confirmed
  let confirmedSuggestions = $state<Record<string, boolean>>({});

  // Initialize speakerNames when modal becomes visible or speakers change
  $effect(() => {
    if (appState.showLabelingModal && appState.detectedSpeakers.length > 0) {
      const names: Record<string, string> = {};
      const confirmed: Record<string, boolean> = {};
      for (const speaker of appState.detectedSpeakers) {
        names[speaker.label] = speaker.suggestedName ?? '';
        confirmed[speaker.label] = false;
      }
      speakerNames = names;
      confirmedSuggestions = confirmed;
    }
  });

  // Convert "SPEAKER_00" to 1-based "Speaker 1" display label
  function displayLabel(speaker: DetectedSpeaker, index: number): string {
    return `Speaker ${index + 1}`;
  }

  // Format confidence as a percentage string
  function formatConfidence(confidence: number): string {
    return `${Math.round(confidence * 100)}% match`;
  }

  // Check if all speakers have a non-empty name assigned
  let allLabeled = $derived(
    appState.detectedSpeakers.length > 0 &&
    appState.detectedSpeakers.every(
      (s) => (speakerNames[s.label] ?? '').trim().length > 0
    )
  );

  function confirmSuggestion(label: string): void {
    confirmedSuggestions[label] = true;
  }

  function handleConfirm(): void {
    if (!allLabeled) return;

    // Reassign the whole array so Svelte 5 picks up the change
    appState.transcript = appState.transcript.map((seg) => ({
      ...seg,
      speaker: seg.speaker && speakerNames[seg.speaker]
        ? speakerNames[seg.speaker].trim()
        : seg.speaker,
    }));

    appState.showLabelingModal = false;
    appState.processingState = 'summarizing';
  }

  function handleSkip(): void {
    // Build a lookup from raw label → generic name
    const labelToGeneric: Record<string, string> = {};
    for (let i = 0; i < appState.detectedSpeakers.length; i++) {
      labelToGeneric[appState.detectedSpeakers[i].label] = `Speaker ${i + 1}`;
    }

    // Reassign the whole array so Svelte 5 picks up the change
    appState.transcript = appState.transcript.map((seg) => ({
      ...seg,
      speaker: seg.speaker && labelToGeneric[seg.speaker]
        ? labelToGeneric[seg.speaker]
        : seg.speaker,
    }));

    appState.showLabelingModal = false;
    appState.processingState = 'summarizing';
  }

  function handleBackdropClick(event: MouseEvent): void {
    // Only close if clicking directly on the backdrop, not the modal card
    if (event.target === event.currentTarget) {
      // Do nothing -- we don't dismiss on backdrop click for this modal
      // since the user should explicitly confirm or skip
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      handleSkip();
    }
  }
</script>

{#if appState.showLabelingModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- svelte-ignore a11y_interactive_supports_focus -->
  <div
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="labeling-title"
    onclick={handleBackdropClick}
    onkeydown={handleKeydown}
  >
    <div class="modal-card">
      <div class="modal-header">
        <h2 id="labeling-title" class="modal-title">Who was in this meeting?</h2>
        <p class="modal-subtitle">
          Assign names to each detected speaker. Excerpts are shown to help identify them.
        </p>
      </div>

      <div class="speakers-list">
        {#each appState.detectedSpeakers as speaker, index}
          <div class="speaker-card">
            <div class="speaker-card-header">
              <span class="speaker-label-badge">{displayLabel(speaker, index)}</span>
              {#if speaker.suggestedName}
                <span class="confidence-badge">{formatConfidence(speaker.confidence)}</span>
              {:else}
                <span class="new-speaker-badge">New speaker</span>
              {/if}
            </div>

            {#if speaker.excerpts.length > 0}
              <div class="excerpts-box">
                {#each speaker.excerpts.slice(0, 3) as excerpt}
                  <p class="excerpt"><em>"{excerpt}"</em></p>
                {/each}
              </div>
            {/if}

            <div class="speaker-name-input-area">
              {#if speaker.suggestedName}
                <div class="suggested-match">
                  <span class="suggested-text">
                    Identified as <strong>{speaker.suggestedName}</strong>
                  </span>
                  {#if !confirmedSuggestions[speaker.label]}
                    <button
                      class="confirm-btn"
                      onclick={() => confirmSuggestion(speaker.label)}
                    >
                      Correct
                    </button>
                  {:else}
                    <span class="confirmed-check">Confirmed</span>
                  {/if}
                </div>
                <div class="override-field">
                  <label class="override-label" for="speaker-{speaker.label}">
                    Or enter a different name:
                  </label>
                  <input
                    id="speaker-{speaker.label}"
                    type="text"
                    class="name-input"
                    placeholder="Override name..."
                    bind:value={speakerNames[speaker.label]}
                  />
                </div>
              {:else}
                <div class="required-field">
                  <label class="required-label" for="speaker-{speaker.label}">
                    Speaker name
                  </label>
                  <input
                    id="speaker-{speaker.label}"
                    type="text"
                    class="name-input"
                    placeholder="Enter speaker name..."
                    bind:value={speakerNames[speaker.label]}
                  />
                </div>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      <div class="modal-footer">
        <button class="skip-btn" onclick={handleSkip}>
          Skip Labeling
        </button>
        <button
          class="confirm-labels-btn"
          disabled={!allLabeled}
          onclick={handleConfirm}
        >
          Confirm Labels
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: rgba(0, 0, 0, 0.5);
    animation: fade-in 0.2s ease-out;
  }

  .modal-card {
    width: 100%;
    max-width: 600px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    background-color: var(--color-bg);
    border-radius: 16px;
    padding: 32px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    animation: scale-in 0.2s ease-out;
  }

  .modal-header {
    margin-bottom: 24px;
    flex-shrink: 0;
  }

  .modal-title {
    margin: 0;
    font-size: 1.375rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .modal-subtitle {
    margin: 8px 0 0 0;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    line-height: 1.4;
  }

  .speakers-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
    padding-right: 4px;
  }

  .speaker-card {
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .speaker-card-header {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .speaker-label-badge {
    font-size: 0.8125rem;
    font-weight: 600;
    color: #2563eb;
    background-color: rgba(37, 99, 235, 0.1);
    padding: 3px 10px;
    border-radius: 6px;
  }

  @media (prefers-color-scheme: dark) {
    .speaker-label-badge {
      background-color: rgba(37, 99, 235, 0.2);
      color: #60a5fa;
    }
  }

  .confidence-badge {
    font-size: 0.6875rem;
    font-weight: 500;
    color: #16a34a;
    background-color: rgba(22, 163, 74, 0.1);
    padding: 2px 8px;
    border-radius: 4px;
  }

  @media (prefers-color-scheme: dark) {
    .confidence-badge {
      background-color: rgba(22, 163, 74, 0.2);
      color: #4ade80;
    }
  }

  .new-speaker-badge {
    font-size: 0.6875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    background-color: var(--color-border);
    padding: 2px 8px;
    border-radius: 4px;
  }

  .excerpts-box {
    background-color: var(--color-bg);
    border-radius: 8px;
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .excerpt {
    margin: 0;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    line-height: 1.45;
  }

  .speaker-name-input-area {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .suggested-match {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .suggested-text {
    font-size: 0.875rem;
    color: var(--color-text);
  }

  .confirm-btn {
    padding: 4px 14px;
    border-radius: 6px;
    border: none;
    background-color: #16a34a;
    color: #ffffff;
    font-size: 0.75rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.15s ease;
  }

  .confirm-btn:hover {
    background-color: #15803d;
  }

  .confirmed-check {
    font-size: 0.75rem;
    font-weight: 500;
    color: #16a34a;
  }

  @media (prefers-color-scheme: dark) {
    .confirmed-check {
      color: #4ade80;
    }
  }

  .override-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .override-label {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }

  .required-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .required-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .name-input {
    width: 100%;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-bg);
    color: var(--color-text);
    font-size: 0.875rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s ease;
    box-sizing: border-box;
  }

  .name-input:focus {
    border-color: #2563eb;
  }

  .name-input::placeholder {
    color: var(--color-text-secondary);
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
    flex-shrink: 0;
    padding-top: 16px;
    border-top: 1px solid var(--color-border);
  }

  .skip-btn {
    padding: 10px 20px;
    border-radius: 8px;
    border: none;
    background: none;
    color: var(--color-text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: color 0.15s ease, background-color 0.15s ease;
  }

  .skip-btn:hover {
    color: var(--color-text);
    background-color: var(--color-surface);
  }

  .confirm-labels-btn {
    padding: 10px 24px;
    border-radius: 8px;
    border: none;
    background-color: #2563eb;
    color: #ffffff;
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.15s ease, transform 0.1s ease, opacity 0.15s ease;
  }

  .confirm-labels-btn:hover:not(:disabled) {
    background-color: #1d4ed8;
  }

  .confirm-labels-btn:active:not(:disabled) {
    transform: scale(0.98);
  }

  .confirm-labels-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Animations */
  @keyframes fade-in {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @keyframes scale-in {
    from {
      opacity: 0;
      transform: scale(0.95);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }
</style>
