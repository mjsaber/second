<script lang="ts">
  import type { AppSettings } from '../types/index.js';

  let settings = $state<AppSettings>({
    llmProvider: 'claude',
    apiKey: '',
    audioDevice: 'default',
    audioRetention: 'keep',
  });

  let showApiKey = $state(false);

  function handleSave(): void {
    // Placeholder: will integrate with Tauri backend later
    console.log('Settings saved:', {
      ...settings,
      apiKey: settings.apiKey ? '***' : '',
    });
  }
</script>

<div class="settings-page">
  <div class="settings-header">
    <h2>Settings</h2>
  </div>

  <div class="settings-content">
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
            bind:group={settings.llmProvider}
          />
          <span class="radio-label">Claude</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="openai"
            bind:group={settings.llmProvider}
          />
          <span class="radio-label">OpenAI</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="gemini"
            bind:group={settings.llmProvider}
          />
          <span class="radio-label">Gemini</span>
        </label>
        <label class="radio-option">
          <input
            type="radio"
            name="llmProvider"
            value="ollama"
            bind:group={settings.llmProvider}
          />
          <span class="radio-label">Ollama (Local)</span>
        </label>
      </div>
    </section>

    <section class="settings-section">
      <h3>API Key</h3>
      <p class="section-description">
        Enter your API key for the selected provider. Not required for Ollama.
      </p>
      <div class="api-key-field">
        <input
          type={showApiKey ? 'text' : 'password'}
          placeholder="Enter API key..."
          bind:value={settings.apiKey}
          class="text-input"
        />
        <button
          class="toggle-visibility"
          onclick={() => (showApiKey = !showApiKey)}
          type="button"
        >
          {showApiKey ? 'Hide' : 'Show'}
        </button>
      </div>
    </section>

    <section class="settings-section">
      <h3>Audio</h3>
      <p class="section-description">
        Configure audio input device and retention settings.
      </p>
      <div class="form-field">
        <label class="field-label" for="audio-device">Input Device</label>
        <select
          id="audio-device"
          bind:value={settings.audioDevice}
          class="select-input"
        >
          <option value="default">System Default</option>
        </select>
      </div>
      <div class="form-field">
        <label class="field-label" for="audio-retention">Audio Retention</label>
        <select
          id="audio-retention"
          bind:value={settings.audioRetention}
          class="select-input"
        >
          <option value="keep">Keep recordings</option>
          <option value="delete">Delete after processing</option>
        </select>
      </div>
    </section>

    <div class="settings-actions">
      <button class="save-button" onclick={handleSave}>
        Save Settings
      </button>
    </div>
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
</style>
