<script lang="ts">
  import { invoke } from "@tauri-apps/api/core";

  let greetMsg = $state("");
  let name = $state("");

  async function greet() {
    greetMsg = await invoke("greet", { name });
  }
</script>

<main class="container">
  <h1>Welcome to Second</h1>

  <p>A local, privacy-first meeting note-taking tool.</p>

  <form class="row" onsubmit={(e) => { e.preventDefault(); greet(); }}>
    <input id="greet-input" placeholder="Enter a name..." bind:value={name} />
    <button type="submit">Greet</button>
  </form>

  <p>{greetMsg}</p>
</main>

<style>
  :root {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
    color: #0f0f0f;
    background-color: #f6f6f6;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      color: #f6f6f6;
      background-color: #2f2f2f;
    }
  }

  .container {
    margin: 0;
    padding-top: 10vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
  }

  .row {
    display: flex;
    justify-content: center;
    gap: 8px;
  }

  input,
  button {
    border-radius: 8px;
    border: 1px solid transparent;
    padding: 0.6em 1.2em;
    font-size: 1em;
    font-weight: 500;
    font-family: inherit;
    color: #0f0f0f;
    background-color: #ffffff;
    transition: border-color 0.25s;
    box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
  }

  button {
    cursor: pointer;
  }

  button:hover {
    border-color: #396cd8;
  }
  button:active {
    border-color: #396cd8;
    background-color: #e8e8e8;
  }

  input {
    outline: none;
  }

  @media (prefers-color-scheme: dark) {
    input,
    button {
      color: #f6f6f6;
      background-color: #0f0f0f98;
    }
    button:active {
      background-color: #0f0f0f69;
    }
  }
</style>
