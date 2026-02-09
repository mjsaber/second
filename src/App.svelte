<script lang="ts">
  import { appState } from './lib/stores/app.svelte.js';
  import type { Page } from './lib/types/index.js';
  import RecordingPage from './lib/components/RecordingPage.svelte';
  import SummariesPage from './lib/components/SummariesPage.svelte';
  import SettingsPage from './lib/components/SettingsPage.svelte';
  import SpeakerLabelingModal from './lib/components/SpeakerLabelingModal.svelte';

  interface NavItem {
    page: Page;
    label: string;
  }

  const navItems: NavItem[] = [
    { page: 'recording', label: 'Record' },
    { page: 'summaries', label: 'Summaries' },
    { page: 'settings', label: 'Settings' },
  ];

  function navigateTo(page: Page): void {
    appState.currentPage = page;
  }
</script>

<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1 class="app-title">Second</h1>
    </div>
    <nav class="sidebar-nav">
      {#each navItems as item}
        <button
          class="nav-item"
          class:active={appState.currentPage === item.page}
          onclick={() => navigateTo(item.page)}
        >
          {item.label}
        </button>
      {/each}
    </nav>
    <div class="sidebar-footer">
      <span class="connection-status" class:connected={appState.sidecarConnected}>
        {appState.sidecarConnected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  </aside>

  <main class="main-content">
    {#if appState.currentPage === 'recording'}
      <RecordingPage />
    {:else if appState.currentPage === 'summaries'}
      <SummariesPage />
    {:else if appState.currentPage === 'settings'}
      <SettingsPage />
    {/if}
  </main>
</div>

<SpeakerLabelingModal />

<style>
  .app-shell {
    display: flex;
    height: 100vh;
    overflow: hidden;
  }

  .sidebar {
    width: 200px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background-color: var(--sidebar-bg);
    color: var(--sidebar-text);
    border-right: 1px solid var(--sidebar-border);
    user-select: none;
    -webkit-user-select: none;
  }

  .sidebar-header {
    padding: 20px 16px 12px;
    /* Allow dragging the window from the sidebar header on macOS */
    -webkit-app-region: drag;
  }

  .app-title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--sidebar-text);
  }

  .sidebar-nav {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    padding: 8px 12px;
    border: none;
    border-radius: 6px;
    background: none;
    color: var(--sidebar-text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.1s ease, color 0.1s ease;
    text-align: left;
    -webkit-app-region: no-drag;
  }

  .nav-item:hover {
    background-color: var(--sidebar-hover);
    color: var(--sidebar-text);
  }

  .nav-item.active {
    background-color: var(--sidebar-active);
    color: var(--sidebar-text);
  }

  .sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--sidebar-border);
  }

  .connection-status {
    font-size: 0.6875rem;
    color: var(--sidebar-text-secondary);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .connection-status::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background-color: #ef4444;
  }

  .connection-status.connected::before {
    background-color: #22c55e;
  }

  .main-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
    background-color: var(--color-bg);
    color: var(--color-text);
  }
</style>
