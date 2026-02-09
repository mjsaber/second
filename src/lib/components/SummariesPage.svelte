<script lang="ts">
  import type { Speaker, SummaryEntry } from '../types/index.js';

  let searchQuery = $state('');
  let selectedSpeakerId = $state<number | null>(null);

  const speakers: Speaker[] = [
    { id: 1, name: 'Alice Chen', meetingCount: 12 },
    { id: 2, name: 'Bob Martinez', meetingCount: 8 },
    { id: 3, name: 'Carol Kim', meetingCount: 5 },
    { id: 4, name: 'David Park', meetingCount: 3 },
  ];

  const summaries: SummaryEntry[] = [
    { id: 1, date: '2025-01-15', speakerName: 'Alice Chen', preview: 'Discussed Q1 roadmap priorities and team allocation for the new ML pipeline project.' },
    { id: 2, date: '2025-01-12', speakerName: 'Alice Chen', preview: 'Sprint review: completed 3 epics, 2 carry-overs to next sprint. Performance metrics improved 15%.' },
    { id: 3, date: '2025-01-10', speakerName: 'Bob Martinez', preview: 'API design review for v2 endpoints. Agreed on REST conventions and pagination approach.' },
    { id: 4, date: '2025-01-08', speakerName: 'Carol Kim', preview: 'UX research findings: users prefer sidebar navigation, want keyboard shortcuts.' },
  ];

  let filteredSpeakers = $derived(
    speakers.filter((s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );

  let selectedSummaries = $derived(
    selectedSpeakerId
      ? summaries.filter(
          (s) =>
            s.speakerName ===
            speakers.find((sp) => sp.id === selectedSpeakerId)?.name
        )
      : []
  );
</script>

<div class="summaries-page">
  <div class="summaries-header">
    <h2>Summaries</h2>
  </div>

  <div class="search-bar">
    <input
      type="text"
      placeholder="Search speakers..."
      bind:value={searchQuery}
      class="search-input"
    />
  </div>

  <div class="summaries-content">
    <div class="speakers-panel">
      <h3>Speakers</h3>
      <ul class="speaker-list">
        {#each filteredSpeakers as speaker}
          <li>
            <button
              class="speaker-item"
              class:selected={selectedSpeakerId === speaker.id}
              onclick={() => (selectedSpeakerId = speaker.id)}
            >
              <span class="speaker-name">{speaker.name}</span>
              <span class="meeting-count">{speaker.meetingCount} meetings</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>

    <div class="summary-panel">
      {#if selectedSpeakerId === null}
        <div class="empty-state">
          <p>Select a speaker to view summaries</p>
        </div>
      {:else if selectedSummaries.length === 0}
        <div class="empty-state">
          <p>No summaries found for this speaker.</p>
        </div>
      {:else}
        <div class="summary-list">
          {#each selectedSummaries as entry}
            <div class="summary-card">
              <div class="summary-date">{entry.date}</div>
              <div class="summary-preview">{entry.preview}</div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .summaries-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 16px;
  }

  .summaries-header h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
  }

  .search-bar {
    width: 100%;
  }

  .search-input {
    width: 100%;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid var(--color-border);
    background-color: var(--color-surface);
    color: var(--color-text);
    font-size: 0.875rem;
    font-family: inherit;
    outline: none;
    box-sizing: border-box;
    transition: border-color 0.15s ease;
  }

  .search-input:focus {
    border-color: #2563eb;
  }

  .search-input::placeholder {
    color: var(--color-text-secondary);
  }

  .summaries-content {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
  }

  .speakers-panel {
    width: 240px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .speakers-panel h3 {
    margin: 0 0 8px 0;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary);
  }

  .speaker-list {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
  }

  .speaker-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 10px 12px;
    border: none;
    border-radius: 8px;
    background: none;
    cursor: pointer;
    font-family: inherit;
    text-align: left;
    color: var(--color-text);
    transition: background-color 0.1s ease;
  }

  .speaker-item:hover {
    background-color: var(--color-surface);
  }

  .speaker-item.selected {
    background-color: #2563eb;
    color: #ffffff;
  }

  .speaker-name {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .meeting-count {
    font-size: 0.75rem;
    opacity: 0.7;
  }

  .summary-panel {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--color-text-secondary);
    font-style: italic;
  }

  .summary-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .summary-card {
    padding: 16px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
  }

  .summary-date {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    margin-bottom: 8px;
  }

  .summary-preview {
    font-size: 0.875rem;
    line-height: 1.5;
    color: var(--color-text);
  }
</style>
