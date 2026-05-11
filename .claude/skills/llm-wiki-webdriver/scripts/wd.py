#!/usr/bin/env python3
"""WebDriver helper for LLM Wiki Tauri app.

Usage:
    python3 wd.py <command> [args...]

Commands:
    status              Check if WebDriver is running
    screenshot <path>   Save a screenshot to the given path
    current             Show what's currently visible (headings, view, project)
    tree                List knowledge tree items (entities + concepts)
    click <name>        Click a knowledge tree item by its display name
    read-page           Read the content of the currently displayed wiki page
    navigate <view>     Switch to a view (wiki, search, settings, graph, review, lint, sources)
    llm-config          Show the current LLM provider configuration
    project             Show the loaded project info
    chat <message>      Type a message into the chat input
    run-js <js>         Execute JavaScript in the WKWebView and print the result
"""

import json
import sys
import time
import base64
import urllib.request
import urllib.error

WD_URL = "http://127.0.0.1:4445"


def wd(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{WD_URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:500]}
    except urllib.error.URLError as e:
        return {"error": str(e)}


class Session:
    def __init__(self):
        resp = wd("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
        val = resp.get("value", {})
        self.sid = val.get("sessionId")
        if not self.sid:
            print(f"Failed to create session: {resp}", file=sys.stderr)
            sys.exit(1)

    def close(self):
        if self.sid:
            wd("DELETE", f"/session/{self.sid}")

    def js(self, script: str) -> object:
        resp = wd("POST", f"/session/{self.sid}/execute/sync", {
            "script": script, "args": []
        })
        return resp.get("value")

    def find(self, using: str, value: str) -> list[str]:
        resp = wd("POST", f"/session/{self.sid}/elements", {
            "using": using, "value": value
        })
        return [next(iter(el.values())) for el in resp.get("value", [])]

    def find_one(self, using: str, value: str) -> str | None:
        resp = wd("POST", f"/session/{self.sid}/element", {
            "using": using, "value": value
        })
        val = resp.get("value")
        if isinstance(val, dict) and "error" not in val:
            return next(iter(val.values()), None)
        return None

    def text(self, element_id: str) -> str:
        resp = wd("GET", f"/session/{self.sid}/element/{element_id}/text")
        return resp.get("value", "")

    def click_el(self, element_id: str):
        wd("POST", f"/session/{self.sid}/element/{element_id}/click", {})

    def screenshot(self) -> bytes:
        resp = wd("GET", f"/session/{self.sid}/screenshot")
        return base64.b64decode(resp.get("value", ""))


def cmd_status():
    resp = wd("GET", "/status")
    ready = resp.get("value", {}).get("ready", False)
    if ready:
        print("WebDriver is running and ready on port 4445")
    else:
        print(f"WebDriver not ready: {resp}")
    return 0 if ready else 1


def cmd_screenshot(path: str):
    s = Session()
    try:
        img = s.screenshot()
        with open(path, "wb") as f:
            f.write(img)
        print(f"Screenshot saved to {path} ({len(img)} bytes)")
    finally:
        s.close()


def cmd_current():
    s = Session()
    try:
        time.sleep(1)
        info = s.js('''
            const h1s = Array.from(document.querySelectorAll("h1"))
                .map(h => h.textContent.trim()).filter(t => t);
            const h2s = Array.from(document.querySelectorAll("h2"))
                .map(h => h.textContent.trim()).filter(t => t).slice(0, 8);
            const chatInput = document.querySelector('[placeholder*="message"]');
            const chatText = chatInput ? chatInput.value : null;
            return { h1s, h2s, chatInput: chatText };
        ''')

        s.js('''
            import("/src/stores/wiki-store.ts").then(mod => {
                const st = mod.useWikiStore.getState();
                window.__wdResult = {
                    project: st.project,
                    activeView: st.activeView,
                    selectedFile: st.selectedFile
                };
            });
        ''')
        time.sleep(1)
        state = s.js("return window.__wdResult")

        if state:
            proj = state.get("project")
            if proj:
                print(f"Project: {proj['name']} ({proj['path']})")
            print(f"Active view: {state.get('activeView', '?')}")
            sel = state.get("selectedFile")
            if sel:
                print(f"Selected file: {sel}")

        if info:
            for h in info.get("h1s", []):
                print(f"H1: {h}")
            for h in info.get("h2s", []):
                print(f"  H2: {h}")
            ci = info.get("chatInput")
            if ci:
                print(f"Chat input: \"{ci}\"")
    finally:
        s.close()


def cmd_tree():
    s = Session()
    try:
        time.sleep(1)
        items = s.js('''
            const spans = document.querySelectorAll("span");
            const result = [];
            for (const sp of spans) {
                const t = sp.textContent.trim();
                if (t.length > 1 && t.length < 60 && sp.children.length === 0) {
                    result.push(t);
                }
            }
            return [...new Set(result)];
        ''')
        if items:
            for item in items:
                print(f"  {item}")
        else:
            print("No tree items found")
    finally:
        s.close()


def cmd_click(name: str):
    s = Session()
    try:
        els = s.find("xpath", f'//span[text()="{name}"]')
        if not els:
            els = s.find("xpath", f'//span[contains(text(), "{name}")]')
        if els:
            s.click_el(els[0])
            time.sleep(1)
            h1s = s.js('return Array.from(document.querySelectorAll("h1")).map(h => h.textContent.trim()).filter(t => t)')
            print(f"Clicked \"{name}\"")
            if h1s:
                print(f"Page now shows: {h1s}")
        else:
            print(f"Element \"{name}\" not found in the UI")
    finally:
        s.close()


def cmd_read_page():
    s = Session()
    try:
        time.sleep(1)
        content = s.js('''
            const headings = Array.from(document.querySelectorAll("h1, h2, h3"))
                .map(h => ({ tag: h.tagName, text: h.textContent.trim() }));
            const paras = Array.from(document.querySelectorAll("p"))
                .map(p => p.textContent.trim()).filter(t => t.length > 10);
            const lists = Array.from(document.querySelectorAll("li"))
                .map(li => li.textContent.trim()).filter(t => t.length > 5 && t.length < 300);
            return { headings, paragraphs: paras, listItems: lists };
        ''')
        if content:
            for h in content.get("headings", []):
                prefix = "#" * int(h["tag"][1])
                print(f"{prefix} {h['text']}")
            print()
            for p in content.get("paragraphs", []):
                print(p[:200])
                print()
            if content.get("listItems"):
                print("List items:")
                for li in content["listItems"][:20]:
                    print(f"  - {li[:150]}")
    finally:
        s.close()


def cmd_navigate(view: str):
    view_map = {
        "wiki": "wiki", "search": "search", "settings": "settings",
        "graph": "graph", "review": "review", "lint": "lint", "sources": "sources"
    }
    if view not in view_map:
        print(f"Unknown view: {view}. Choose from: {', '.join(view_map.keys())}")
        return

    s = Session()
    try:
        s.js(f'''
            import("/src/stores/wiki-store.ts").then(mod => {{
                mod.useWikiStore.getState().setActiveView("{view_map[view]}");
            }});
        ''')
        time.sleep(1)
        print(f"Navigated to {view}")
    finally:
        s.close()


def cmd_llm_config():
    s = Session()
    try:
        s.js('''
            import("/src/stores/wiki-store.ts").then(mod => {
                mod.useWikiStore.getState().setActiveView("settings");
            });
        ''')
        time.sleep(2)

        config = s.js('''
            const items = [];
            const all = document.querySelectorAll("*");
            for (const el of all) {
                const t = el.textContent.trim();
                if (el.children.length === 0 && t.length > 0 && t.length < 200) {
                    if (t.toLowerCase().includes("claude") || t.toLowerCase().includes("model") ||
                        t.toLowerCase().includes("active") || t.toLowerCase().includes("cli") ||
                        t.toLowerCase().includes("provider") || t.toLowerCase().includes("api") ||
                        t.toLowerCase().includes("context") || t.toLowerCase().includes("reasoning") ||
                        t.toLowerCase().includes("openai") || t.toLowerCase().includes("anthropic") ||
                        t.toLowerCase().includes("ollama") || t.toLowerCase().includes("version") ||
                        t.toLowerCase().includes("binary") || t.toLowerCase().includes("status")) {
                        items.push(el.tagName + ": " + t);
                    }
                }
            }
            return [...new Set(items)].slice(0, 30);
        ''')
        if config:
            for item in config:
                print(f"  {item}")
    finally:
        s.close()


def cmd_project():
    s = Session()
    try:
        s.js('''
            import("/src/stores/wiki-store.ts").then(mod => {
                const st = mod.useWikiStore.getState();
                window.__wdResult = JSON.stringify(st.project, null, 2);
            });
        ''')
        time.sleep(1)
        result = s.js("return window.__wdResult")
        print(result or "No project loaded")
    finally:
        s.close()


def cmd_chat(message: str):
    s = Session()
    try:
        el = s.find_one("css selector", '[placeholder*="message"]')
        if el:
            wd("POST", f"/session/{s.sid}/element/{el}/value", {"text": message})
            print(f"Typed: \"{message}\"")
        else:
            print("Chat input not found — are you on the wiki/chat view?")
    finally:
        s.close()


def cmd_run_js(js_code: str):
    s = Session()
    try:
        result = s.js(f"return {js_code}")
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
    finally:
        s.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "status": lambda: cmd_status(),
        "screenshot": lambda: cmd_screenshot(args[0] if args else "wiki-screenshot.png"),
        "current": lambda: cmd_current(),
        "tree": lambda: cmd_tree(),
        "click": lambda: cmd_click(args[0] if args else ""),
        "read-page": lambda: cmd_read_page(),
        "navigate": lambda: cmd_navigate(args[0] if args else "wiki"),
        "llm-config": lambda: cmd_llm_config(),
        "project": lambda: cmd_project(),
        "chat": lambda: cmd_chat(" ".join(args) if args else ""),
        "run-js": lambda: cmd_run_js(" ".join(args) if args else "document.title"),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
