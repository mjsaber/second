<script lang="ts">
  import type { Speaker, SummaryEntry, SummaryDetail } from '../types/index.js';
  import {
    getAllSpeakers,
    getSummariesForSpeaker,
    getSummaryDetail,
    searchSummaries,
  } from '../services/sidecar.js';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let searchQuery = $state('');
  let selectedSpeakerId = $state<number | null>(null);
  let selectedSummaryId = $state<number | null>(null);
  let speakers = $state<Speaker[]>([]);
  let summaries = $state<SummaryEntry[]>([]);
  let summaryDetail = $state<SummaryDetail | null>(null);
  let loading = $state(false);
  let detailLoading = $state(false);

  // ---------------------------------------------------------------------------
  // Data fetching (placeholder — swap with real sidecar calls)
  // ---------------------------------------------------------------------------

  /** Fetch all speakers from the backend. */
  async function loadSpeakers(): Promise<void> {
    try {
      const response = await getAllSpeakers();
      const raw = (response.speakers ?? []) as Array<Record<string, unknown>>;
      speakers = raw.map((s) => ({
        id: s.id as number,
        name: s.name as string,
        meetingCount: (s.meeting_count as number) ?? 0,
      }));
    } catch {
      speakers = [];
    }
  }

  /** Fetch summaries for a specific speaker. */
  async function loadSummariesForSpeaker(speakerId: number): Promise<void> {
    loading = true;
    try {
      const speaker = speakers.find((s) => s.id === speakerId);
      const speakerName = speaker?.name ?? 'Unknown';
      const response = await getSummariesForSpeaker(speakerName);
      const raw = (response.summaries ?? []) as Array<Record<string, unknown>>;
      summaries = raw.map((s) => ({
        id: s.id as number,
        date: ((s.date as string) ?? (s.created_at as string) ?? '').split('T')[0],
        speakerName,
        preview: (s.preview_text as string) ?? ((s.content as string) ?? '').slice(0, 200),
      }));
    } catch {
      summaries = [];
    } finally {
      loading = false;
    }
  }

  /** Fetch full summary detail for a specific summary entry. */
  async function loadSummaryDetail(summaryId: number): Promise<void> {
    detailLoading = true;
    try {
      const response = await getSummaryDetail(summaryId);
      summaryDetail = {
        id: response.id as number,
        meetingId: response.meeting_id as number,
        provider: response.provider as string,
        model: response.model as string,
        content: response.content as string,
        filePath: response.file_path as string | undefined,
        createdAt: response.created_at as string,
      };
    } catch {
      summaryDetail = null;
    } finally {
      detailLoading = false;
    }
  }

  /** Search across all summaries using FTS. */
  async function searchAllSummaries(query: string): Promise<void> {
    if (!query.trim()) {
      summaries = [];
      return;
    }
    loading = true;
    try {
      const response = await searchSummaries(query);
      const raw = (response.results ?? []) as Array<Record<string, unknown>>;
      summaries = raw.map((r) => ({
        id: r.id as number,
        date: ((r.created_at as string) ?? '').split('T')[0],
        speakerName: (r.speaker_name as string) ?? '',
        preview: ((r.content as string) ?? '').slice(0, 200),
      }));
    } catch {
      summaries = [];
    } finally {
      loading = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  let filteredSpeakers = $derived(
    speakers.filter((s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );

  let isSearchMode = $derived(searchQuery.trim().length > 0 && selectedSpeakerId === null);

  let selectedSpeaker = $derived(
    selectedSpeakerId !== null
      ? speakers.find((s) => s.id === selectedSpeakerId) ?? null
      : null
  );

  let showingDetail = $derived(selectedSummaryId !== null && summaryDetail !== null);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Load speakers on mount
  $effect(() => {
    loadSpeakers();
  });

  // When a speaker is selected, load their summaries and clear detail view
  $effect(() => {
    if (selectedSpeakerId !== null) {
      selectedSummaryId = null;
      summaryDetail = null;
      loadSummariesForSpeaker(selectedSpeakerId);
    }
  });

  // When in search mode (no speaker selected, query present), run search
  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  $effect(() => {
    const query = searchQuery;
    const speakerId = selectedSpeakerId;

    if (speakerId === null && query.trim().length > 0) {
      // Debounce search
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        searchAllSummaries(query);
      }, 250);
    }

    return () => {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    };
  });

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function selectSpeaker(id: number): void {
    selectedSpeakerId = id;
    // Clear search when selecting a speaker
    searchQuery = '';
  }

  function deselectSpeaker(): void {
    selectedSpeakerId = null;
    selectedSummaryId = null;
    summaryDetail = null;
    summaries = [];
  }

  function selectSummary(id: number): void {
    selectedSummaryId = id;
    loadSummaryDetail(id);
  }

  function backToList(): void {
    selectedSummaryId = null;
    summaryDetail = null;
  }

  /** Format a date string into a readable form. */
  function formatDate(dateStr: string): string {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  /** Render basic markdown to HTML (headings, bold, italic, lists, code, paragraphs). */
  function renderMarkdown(md: string): string {
    const escaped = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    const lines = escaped.split('\n');
    const htmlLines: string[] = [];
    let inList = false;
    let inOrderedList = false;

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];

      // Close lists if current line isn't a list item
      if (inList && !line.match(/^- /)) {
        htmlLines.push('</ul>');
        inList = false;
      }
      if (inOrderedList && !line.match(/^\d+\. /)) {
        htmlLines.push('</ol>');
        inOrderedList = false;
      }

      // Headings
      if (line.match(/^### /)) {
        line = `<h4>${applyInlineFormatting(line.slice(4))}</h4>`;
        htmlLines.push(line);
        continue;
      }
      if (line.match(/^## /)) {
        line = `<h3>${applyInlineFormatting(line.slice(3))}</h3>`;
        htmlLines.push(line);
        continue;
      }
      if (line.match(/^# /)) {
        line = `<h2>${applyInlineFormatting(line.slice(2))}</h2>`;
        htmlLines.push(line);
        continue;
      }

      // Unordered list items
      if (line.match(/^- /)) {
        if (!inList) {
          htmlLines.push('<ul>');
          inList = true;
        }
        htmlLines.push(`<li>${applyInlineFormatting(line.slice(2))}</li>`);
        continue;
      }

      // Ordered list items
      const orderedMatch = line.match(/^(\d+)\. /);
      if (orderedMatch) {
        if (!inOrderedList) {
          htmlLines.push('<ol>');
          inOrderedList = true;
        }
        htmlLines.push(`<li>${applyInlineFormatting(line.slice(orderedMatch[0].length))}</li>`);
        continue;
      }

      // Empty line
      if (line.trim() === '') {
        htmlLines.push('');
        continue;
      }

      // Regular paragraph
      htmlLines.push(`<p>${applyInlineFormatting(line)}</p>`);
    }

    // Close any open lists
    if (inList) htmlLines.push('</ul>');
    if (inOrderedList) htmlLines.push('</ol>');

    return htmlLines.join('\n');
  }

  /** Apply inline markdown formatting: bold, italic, inline code. */
  function applyInlineFormatting(text: string): string {
    return text
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>');
  }
</script>

<div class="summaries-page">
  <div class="summaries-header">
    <h2>Summaries</h2>
  </div>

  <div class="search-bar">
    <input
      type="text"
      placeholder="Search all summaries..."
      bind:value={searchQuery}
      class="search-input"
    />
  </div>

  <div class="summaries-content">
    <!-- Left panel: Speaker list -->
    <div class="speakers-panel">
      <h3>Speakers</h3>
      {#if speakers.length === 0}
        <div class="empty-state-small">
          <p>No meetings recorded yet. Start a recording to see summaries here.</p>
        </div>
      {:else}
        <ul class="speaker-list">
          {#each filteredSpeakers as speaker}
            <li>
              <button
                class="speaker-item"
                class:selected={selectedSpeakerId === speaker.id}
                onclick={() => selectSpeaker(speaker.id)}
              >
                <span class="speaker-name">{speaker.name}</span>
                <span class="meeting-count">{speaker.meetingCount} {speaker.meetingCount === 1 ? 'meeting' : 'meetings'}</span>
              </button>
            </li>
          {/each}
          {#if filteredSpeakers.length === 0 && searchQuery.trim().length > 0}
            <li class="no-speaker-match">
              <p>No speakers matching "{searchQuery}"</p>
            </li>
          {/if}
        </ul>
      {/if}
    </div>

    <!-- Right panel: Summary list or detail -->
    <div class="summary-panel">
      {#if showingDetail && summaryDetail}
        <!-- Detail view: full summary content -->
        <div class="detail-view">
          <button class="back-button" onclick={backToList}>
            <span class="back-arrow">&larr;</span> Back to summaries
          </button>
          <div class="detail-header">
            <span class="detail-date">{formatDate(summaryDetail.createdAt.split('T')[0])}</span>
            <span class="detail-meta">
              {summaryDetail.provider} / {summaryDetail.model}
            </span>
          </div>
          <div class="detail-content">
            {@html renderMarkdown(summaryDetail.content)}
          </div>
        </div>
      {:else if detailLoading}
        <div class="empty-state">
          <p>Loading summary...</p>
        </div>
      {:else if isSearchMode}
        <!-- Search results mode -->
        {#if loading}
          <div class="empty-state">
            <p>Searching...</p>
          </div>
        {:else if summaries.length === 0}
          <div class="empty-state">
            <p>No results matching your search.</p>
          </div>
        {:else}
          <div class="results-header">
            <span class="results-count">{summaries.length} result{summaries.length === 1 ? '' : 's'} for "{searchQuery}"</span>
          </div>
          <div class="summary-list">
            {#each summaries as entry}
              <button
                class="summary-card"
                onclick={() => selectSummary(entry.id)}
              >
                <div class="summary-card-top">
                  <span class="summary-date">{formatDate(entry.date)}</span>
                  <span class="summary-speaker-badge">{entry.speakerName}</span>
                </div>
                <div class="summary-preview">{entry.preview}</div>
              </button>
            {/each}
          </div>
        {/if}
      {:else if selectedSpeakerId === null}
        <!-- No speaker selected -->
        <div class="empty-state">
          <p>Select a speaker to view their meeting summaries.</p>
        </div>
      {:else if loading}
        <div class="empty-state">
          <p>Loading summaries...</p>
        </div>
      {:else if summaries.length === 0}
        <!-- Speaker selected but no summaries -->
        <div class="empty-state">
          <p>No summaries for this speaker.</p>
        </div>
      {:else}
        <!-- Summary list for selected speaker -->
        <div class="panel-header">
          <span class="panel-title">{selectedSpeaker?.name ?? 'Speaker'}</span>
          <button class="deselect-button" onclick={deselectSpeaker}>Clear</button>
        </div>
        <div class="summary-list">
          {#each summaries as entry}
            <button
              class="summary-card"
              onclick={() => selectSummary(entry.id)}
            >
              <div class="summary-card-top">
                <span class="summary-date">{formatDate(entry.date)}</span>
              </div>
              <div class="summary-preview">{entry.preview}</div>
            </button>
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

  /* ---- Search bar ---- */

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

  /* ---- Content layout ---- */

  .summaries-content {
    flex: 1;
    display: flex;
    gap: 16px;
    min-height: 0;
  }

  /* ---- Speakers panel (left) ---- */

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

  .speaker-item.selected .meeting-count {
    color: rgba(255, 255, 255, 0.8);
  }

  .speaker-name {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .meeting-count {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    flex-shrink: 0;
  }

  .no-speaker-match {
    padding: 12px;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
    font-style: italic;
  }

  .no-speaker-match p {
    margin: 0;
  }

  .empty-state-small {
    padding: 16px 12px;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
    line-height: 1.5;
  }

  .empty-state-small p {
    margin: 0;
  }

  /* ---- Summary panel (right) ---- */

  .summary-panel {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--color-text-secondary);
    font-style: italic;
  }

  .empty-state p {
    margin: 0;
  }

  /* ---- Panel header (speaker selected) ---- */

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    flex-shrink: 0;
  }

  .panel-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .deselect-button {
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: none;
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.1s ease, color 0.1s ease;
  }

  .deselect-button:hover {
    background-color: var(--color-surface);
    color: var(--color-text);
  }

  /* ---- Search results header ---- */

  .results-header {
    margin-bottom: 12px;
    flex-shrink: 0;
  }

  .results-count {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
  }

  /* ---- Summary list ---- */

  .summary-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .summary-card {
    display: block;
    width: 100%;
    padding: 16px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
    cursor: pointer;
    font-family: inherit;
    text-align: left;
    color: var(--color-text);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }

  .summary-card:hover {
    border-color: #2563eb;
    box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.2);
  }

  .summary-card-top {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  .summary-date {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .summary-speaker-badge {
    font-size: 0.6875rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 10px;
    background-color: rgba(37, 99, 235, 0.1);
    color: #2563eb;
  }

  @media (prefers-color-scheme: dark) {
    .summary-speaker-badge {
      background-color: rgba(37, 99, 235, 0.2);
      color: #60a5fa;
    }
  }

  .summary-preview {
    font-size: 0.875rem;
    line-height: 1.5;
    color: var(--color-text);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* ---- Detail view ---- */

  .detail-view {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
  }

  .back-button {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid var(--color-border);
    background: none;
    color: var(--color-text-secondary);
    font-size: 0.8125rem;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.1s ease, color 0.1s ease;
    align-self: flex-start;
    flex-shrink: 0;
  }

  .back-button:hover {
    background-color: var(--color-surface);
    color: var(--color-text);
  }

  .back-arrow {
    font-size: 1rem;
    line-height: 1;
  }

  .detail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }

  .detail-date {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .detail-meta {
    font-size: 0.6875rem;
    color: var(--color-text-secondary);
    padding: 2px 8px;
    border-radius: 6px;
    background-color: var(--color-surface);
    border: 1px solid var(--color-border);
  }

  .detail-content {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    background-color: var(--color-surface);
    border-radius: 12px;
    border: 1px solid var(--color-border);
    line-height: 1.6;
    font-size: 0.875rem;
  }

  /* Markdown rendered content styles */
  .detail-content :global(h2) {
    margin: 0 0 12px 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .detail-content :global(h3) {
    margin: 20px 0 8px 0;
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .detail-content :global(h4) {
    margin: 16px 0 6px 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .detail-content :global(p) {
    margin: 0 0 8px 0;
    color: var(--color-text);
  }

  .detail-content :global(ul),
  .detail-content :global(ol) {
    margin: 0 0 12px 0;
    padding-left: 20px;
  }

  .detail-content :global(li) {
    margin-bottom: 4px;
    color: var(--color-text);
  }

  .detail-content :global(strong) {
    font-weight: 600;
    color: var(--color-text);
  }

  .detail-content :global(em) {
    font-style: italic;
  }

  .detail-content :global(code) {
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 0.8125rem;
    padding: 2px 6px;
    border-radius: 4px;
    background-color: var(--color-bg);
    border: 1px solid var(--color-border);
    color: #2563eb;
  }

  @media (prefers-color-scheme: dark) {
    .detail-content :global(code) {
      color: #60a5fa;
    }
  }
</style>
