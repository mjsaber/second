<script lang="ts">
  import type { AppSettings } from '../types/index.js';
  import { appState } from '../stores/app.svelte.js';

  let showApiKey = $state(false);
  let saveMessage = $state('');
  let saveTimeout: ReturnType<typeof setTimeout> | null = $state(null);

  // Cleanup timeout on unmount
  $effect(() => {
    return () => {
      if (saveTimeout) clearTimeout(saveTimeout);
    };
  });

  const modelPlaceholders: Record<AppSettings['llmProvider'], string> = {
    claude: 'claude-sonnet-4-5-20250929',
    openai: 'gpt-4o',
    gemini: 'gemini-2.0-flash',
    ollama: 'llama3.2',
  };

  let currentPlaceholder = $derived(modelPlaceholders[appState.settings.llmProvider]);
  let isOllama = $derived(appState.settings.llmProvider === 'ollama');

  function handleSave(): void {
    // Settings are already bound to appState.settings via bind:value/bind:group,
    // so the store is always in sync. We just need to show feedback
    // and (TODO) persist via sidecar.
    console.log('Settings saved:', {
      ...appState.settings,
      apiKey: appState.settings.apiKey ? '***' : '',
    });

    // TODO: persist to SQLite via sidecar
    // await sendToSidecar({
    //   type: 'save_settings',
    //   settings: { ...appState.settings, apiKey: appState.settings.apiKey },
    // });

    // Show success feedback
    if (saveTimeout) {
      clearTimeout(saveTimeout);
    }
    saveMessage = 'Settings saved';
    saveTimeout = setTimeout(() => {
      saveMessage = '';
      saveTimeout = null;
    }, 2000);
  }
</script>

<div class="settings-page">
  <div class="settings-header">
    <h2>Settings</h2>
  </div>

  <div class="settings-content">
    <!-- LLM Provider -->
    <section class="settings-section">
      <h3>LLM Provider</h3>
      <p class="section-description">
        Choose which language model to use for generating meeting summaries.
      </p>
      <div class="radio-group">
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="claude"
            bind:group={appState.settings.llmProvider}
          />
          <span class="radio-label">Claude</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="openai"
            bind:group={appState.settings.llmProvider}
          />
          <span class="radio-label">OpenAI</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="gemini"
            bind:group={appState.settings.llmProvider}
          />
          <span class="radio-label">Gemini</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="ollama"
            bind:group={appState.settings.llmProvider}
          />
          <span class="radio-label">Ollama (Local)</span>
        </label>
      </div>

      <div class="form-field">
        <label class="field-label" for="model-name">Model Name</label>
        <input
          id="model-name"
          type="text"
          placeholder={currentPlaceholder}
          bind:value={appState.settings.modelName}
          class="text-input"
        />
      </div>
    </section>

    <!-- API Key -->
    <section class="settings-section">
      <h3>API Key</h3>
      <p class="section-description">
        Enter your API key for the selected provider.
        {#if isOllama}
          <span class="note">Not required for Ollama.</span>
        {/if}
      </p>
      <div class="api-key-field">
        <input
          type={showApiKey ? 'text' : 'password'}
          placeholder="Enter API key..."
          bind:value={appState.settings.apiKey}
          class="text-input"
          disabled={isOllama}
        />
        <button
          class="toggle-visibility"
          onclick={() => (showApiKey = !showApiKey)}
          type="button"
          disabled={isOllama}
        >
          {showApiKey ? 'Hide' : 'Show'}
        </button>
      </div>
    </section>

    <!-- Audio -->
    <section class="settings-section">
      <h3>Audio</h3>
      <p class="section-description">
        Configure audio input device and retention settings.
      </p>
      <div class="form-field">
        <label class="field-label" for="audio-device">Input Device</label>
        <select
          id="audio-device"
          bind:value={appState.settings.audioDevice}
          class="select-input"
        >
          <option value="default">System Default</option>
          <!-- TODO: enumerate real audio devices -->
        </select>
      </div>
      <div class="form-field">
        <label class="field-label" for="audio-retention">Audio Retention</label>
        <select
          id="audio-retention"
          bind:value={appState.settings.audioRetention}
          class="select-input"
        >
          <option value="keep">Keep recordings</option>
          <option value="delete">Delete after processing</option>
        </select>
      </div>
    </section>

    <!-- Save -->
    <div class="settings-actions">
      <button class="save-button" onclick={handleSave}>
        Save Settings
      </button>
      {#if saveMessage}
        <span class="save-feedback">{saveMessage}</span>
      {/if}
    </div>

    <!-- Speaker Management -->
    <section class="settings-section speaker-section">
      <h3>Speaker Management</h3>
      <p class="section-description">
        Manage known speakers, edit names, and remove outdated entries.
      </p>
      <div class="speaker-action">
        <button
          class="speaker-button"
          disabled
          title="Coming soon"
        >
          Manage Speakers
        </button>
        <span class="coming-soon-label">Coming soon</span>
      </div>
    </section>
  </div>
</div>

<style>
  .settings-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 24px;
  }

  .settings-header h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
  }

  .settings-content {
    display: flex;
    flex-direction: column;
    gap: 32px;
    max-width: 560px;
    overflow-y: auto;
    padding-bottom: 32px;
  }

  .settings-section {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .settings-section h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .section-description {
    margin: 0;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    line-height: 1.4;
  }

  .note {
    font-style: italic;
    opacity: 0.85;
  }

  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .radio-option {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.1s ease;
  }

  .radio-option:hover {
    background-color: var(--color-surface);
  }

  .radio-option input[type='radio'] {
    accent-color: #2563eb;
  }

  .radio-label {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .api-key-field {
    display: flex;
    gap: 8px;
  }

  .text-input {
    flex: 1;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-surface);
    color: var(--color-text);
    font-size: 0.875rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s ease;
  }

  .text-input:focus {
    border-color: #2563eb;
  }

  .text-input::placeholder {
    color: var(--color-text-secondary);
  }

  .text-input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .toggle-visibility {
    padding: 10px 16px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-surface);
    color: var(--color-text);
    font-size: 0.8125rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.1s ease;
    white-space: nowrap;
  }

  .toggle-visibility:hover {
    background-color: var(--color-border);
  }

  .toggle-visibility:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .form-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .select-input {
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-surface);
    color: var(--color-text);
    font-size: 0.875rem;
    font-family: inherit;
    outline: none;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }

  .select-input:focus {
    border-color: #2563eb;
  }

  .settings-actions {
    display: flex;
    align-items: center;
    gap: 16px;
    padding-top: 8px;
  }

  .save-button {
    padding: 10px 24px;
    border-radius: 8px;
    border: none;
    background-color: #2563eb;
    color: #ffffff;
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.15s ease, transform 0.1s ease;
  }

  .save-button:hover {
    background-color: #1d4ed8;
  }

  .save-button:active {
    transform: scale(0.98);
  }

  .save-feedback {
    font-size: 0.8125rem;
    font-weight: 500;
    color: #16a34a;
    animation: fade-in 0.15s ease-out;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
      transform: translateX(-4px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .speaker-section {
    border-top: 1px solid var(--color-border);
    padding-top: 24px;
  }

  .speaker-action {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .speaker-button {
    padding: 10px 20px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-surface);
    color: var(--color-text);
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.1s ease;
  }

  .speaker-button:hover:not(:disabled) {
    background-color: var(--color-border);
  }

  .speaker-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .coming-soon-label {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    font-style: italic;
  }
</style>
