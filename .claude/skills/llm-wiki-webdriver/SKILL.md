---
name: llm-wiki-webdriver
description: >
  Debug and automate the LLM Wiki Tauri desktop app via WebDriver. Use this skill whenever the user
  mentions LLM Wiki, llm_wiki, wiki app, wiki GUI, wiki UI, wiki webdriver, wiki screenshot, wiki
  settings, checking what page is open in the wiki, navigating wiki entities or concepts, reading
  wiki content through the app, taking a screenshot of the wiki, or automating any interaction with
  the LLM Wiki desktop application. Also trigger when the user wants to inspect, debug, or verify
  the wiki app's state — LLM provider config, knowledge tree contents, chat history, or document
  preview. This skill provides the bridge between Claude Code and the running Tauri app's WKWebView
  via the W3C WebDriver protocol.
---

# LLM Wiki WebDriver

Control and inspect the LLM Wiki Tauri desktop app from Claude Code via WebDriver.

## Architecture

LLM Wiki is a Tauri v2 app (Rust backend + React/TypeScript frontend) that renders in macOS WKWebView. The `tauri-plugin-webdriver` plugin embeds a W3C WebDriver server inside the app on **port 4445**, giving full DOM access to the web content running inside the actual desktop application.

```
Claude Code ──HTTP──▶ WebDriver (:4445) ──▶ WKWebView DOM
                                           (real Tauri app with live IPC)
```

This is not a browser — it's the actual running desktop app. Tauri IPC is live, the Rust backend responds, and the knowledge tree shows real wiki data from disk.

## Prerequisites

The LLM Wiki app must be running with WebDriver enabled:

```bash
# The app source is at ~/redhat/repos/llm_wiki
# tauri-plugin-webdriver is already added as a debug dependency

# 1. Start the Vite dev server (needed for Tauri dev mode)
cd <project-root> && npm run dev &

# 2. Launch the Tauri app
cd <project-root>/src-tauri && cargo run &

# 3. Verify WebDriver is ready
curl -s http://127.0.0.1:4445/status
# Should return: {"value":{"ready":true,...}}
```

If the app isn't running, start it using the steps above. The first `cargo run` after a clean checkout takes ~2.5 minutes to compile; subsequent runs are fast (~4s).

## How to Use

Run the helper script at `.claude/skills/llm-wiki-webdriver/scripts/wd.py` (relative to the repo root) for all WebDriver operations. It handles session lifecycle, error handling, and common patterns.

### Quick reference

```bash
# Check if WebDriver is running
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py status

# Take a screenshot and save it
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py screenshot /path/to/output.png

# Get what's currently visible (headings, active view, selected file)
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py current

# List all entities and concepts in the knowledge tree
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py tree

# Click a knowledge tree item by name
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py click "Granite Guardian"

# Read the content of the currently displayed wiki page
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py read-page

# Navigate to a specific view (wiki, search, settings, graph, review, lint, sources)
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py navigate settings

# Get the current LLM provider configuration
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py llm-config

# Get the project info (name, path, ID)
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py project

# Type into the chat input
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py chat "your message here"

# Execute arbitrary JavaScript inside the WKWebView
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py run-js 'document.title'
```

### Direct WebDriver HTTP API

For anything the helper script doesn't cover, use raw HTTP calls to the WebDriver endpoint. The full W3C WebDriver protocol is available:

```bash
# Create a session
curl -s -X POST http://127.0.0.1:4445/session \
  -H 'Content-Type: application/json' \
  -d '{"capabilities":{"alwaysMatch":{}}}'

# Find element by CSS selector (replace $SID with session ID)
curl -s -X POST http://127.0.0.1:4445/session/$SID/element \
  -H 'Content-Type: application/json' \
  -d '{"using":"css selector","value":"h1"}'

# Find element by XPath
curl -s -X POST http://127.0.0.1:4445/session/$SID/elements \
  -H 'Content-Type: application/json' \
  -d '{"using":"xpath","value":"//span[text()=\"AI Innovation Team\"]"}'

# Execute JavaScript (sync only — async is not supported by this plugin)
curl -s -X POST http://127.0.0.1:4445/session/$SID/execute/sync \
  -H 'Content-Type: application/json' \
  -d '{"script":"return document.title","args":[]}'

# Delete session when done
curl -s -X DELETE http://127.0.0.1:4445/session/$SID
```

### Accessing Zustand Store

The app's state is managed by Zustand. Access it via Vite's dynamic import inside `execute/sync`:

```javascript
// This works because the Vite dev server supports dynamic imports
import("/src/stores/wiki-store.ts").then(mod => {
    const state = mod.useWikiStore.getState();
    window.__wikiState = {
        project: state.project,
        activeView: state.activeView,
        selectedFile: state.selectedFile
    };
});
```

Note: `execute/sync` doesn't support returning Promises. Fire-and-forget the import, then read `window.__wikiState` in a follow-up call.

### Accessing Tauri IPC

The Rust backend is fully accessible via `window.__TAURI_INTERNALS__.invoke()`:

```javascript
// Read a wiki file from disk
window.__TAURI_INTERNALS__.invoke("read_file", {
    path: "/Users/yizheng/redhat/wiki/redhat/wiki/entities/ai-innovation-team.md"
}).then(content => { window.__fileContent = content; });

// List a directory
window.__TAURI_INTERNALS__.invoke("list_directory", {
    path: "/Users/yizheng/redhat/wiki/redhat/wiki/entities"
}).then(entries => { window.__dirEntries = entries; });
```

Same pattern: invoke in one call, read the result from the window in the next.

## Limitations

- **Async script execution is not supported** — `execute/async` returns HTTP 500. Use `execute/sync` with the fire-and-forget + window variable pattern instead.
- **Single session** — only one WebDriver session can be active at a time. Always delete your session when done.
- **No native window control** — WebDriver controls the web content inside WKWebView, not the macOS window itself (no resize, no menu bar, no native dialogs).
- **Debug builds only** — the WebDriver plugin is behind `#[cfg(debug_assertions)]` and excluded from production builds.
- **Port 4445** — the WebDriver listens on this port by default (configurable via `TAURI_WEBDRIVER_PORT` env var).

## Common Tasks

### Verify the wiki app is displaying the right content
```bash
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py current
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py screenshot ~/Desktop/wiki-check.png
```

### Check which LLM provider is active and its configuration
```bash
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py llm-config
```

### Navigate to a wiki page and read its content
```bash
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py click "AI Innovation Team"
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py read-page
```

### Take a screenshot for the user
```bash
python3 .claude/skills/llm-wiki-webdriver/scripts/wd.py screenshot ~/Desktop/wiki-screenshot.png
```
