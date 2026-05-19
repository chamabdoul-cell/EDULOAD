// ── Interactive Demo sidebar: context menu + AI panel ─────────────
import { apiFetch, esc } from './api.js';
import { t, currentLang } from './i18n.js';

// ─── State ────────────────────────────────────────────────────────
let _ctx = null;        // current context: {type, filename?, filetype?, text?}
let _chatHistory = [];  // running chat turns (last 6 kept)
let _chatText = "";     // passage used for chat session

// ─── i18n keys ────────────────────────────────────────────────────
const LABELS = {
  explain:      { en: "Text Explanation",  fr: "Explication textuelle" },
  summary:      { en: "Summary",           fr: "Résumé" },
  chat:         { en: "Interactive Demo",  fr: "Démo interactive" },
  presentation: { en: "Presentation",      fr: "Présentation" },
  flowchart:    { en: "Flowchart",         fr: "Organigramme" },
};

function _label(key) {
  const lang = currentLang || "fr";
  return LABELS[key]?.[lang] ?? key;
}

// ─── Context menu ─────────────────────────────────────────────────
const ACTIONS = ["explain", "summary", "chat", "presentation", "flowchart"];
const ICONS   = { explain:"💡", summary:"📄", chat:"🤖", presentation:"📊", flowchart:"🔀" };

function _buildContextMenu() {
  const el = document.createElement("div");
  el.id = "demo-context-menu";
  el.style.cssText = "display:none;position:fixed;z-index:9999;";
  const ul = document.createElement("ul");
  ul.style.cssText = [
    "list-style:none", "margin:0", "padding:4px 0",
    "background:var(--surface,#fff)", "border:1px solid var(--border,#ddd)",
    "border-radius:8px", "box-shadow:0 4px 16px rgba(0,0,0,0.15)",
    "min-width:190px", "font-size:0.82rem"
  ].join(";");
  ACTIONS.forEach(action => {
    const li = document.createElement("li");
    li.dataset.action = action;
    li.textContent = `${ICONS[action]} ${_label(action)}`;
    li.style.cssText = "padding:8px 16px;cursor:pointer;white-space:nowrap;";
    li.addEventListener("mouseenter", () => li.style.background = "var(--primary,#c8430b)");
    li.addEventListener("mouseleave", () => li.style.background = "");
    ul.appendChild(li);
  });
  el.appendChild(ul);
  document.body.appendChild(el);
  return el;
}

let _menu = null;

function _getMenu() {
  if (!_menu) _menu = document.getElementById("demo-context-menu") || _buildContextMenu();
  return _menu;
}

export function showDemoContextMenu(x, y, context) {
  _ctx = context;
  const menu = _getMenu();
  menu.style.display = "block";
  // Keep within viewport
  const vw = window.innerWidth, vh = window.innerHeight;
  const mw = 200, mh = ACTIONS.length * 38;
  menu.style.left = Math.min(x, vw - mw - 8) + "px";
  menu.style.top  = Math.min(y, vh - mh - 8) + "px";
}

function _hideMenu() {
  _getMenu().style.display = "none";
}

// ─── Sidebar ──────────────────────────────────────────────────────
function _buildSidebar() {
  const el = document.createElement("div");
  el.id = "demo-sidebar";
  el.className = "demo-sidebar demo-sidebar--hidden";
  el.innerHTML = `
    <div class="demo-sidebar__header">
      <span id="demo-sidebar-title" style="font-weight:600;font-size:0.9rem"></span>
      <button id="demo-sidebar-close" style="margin-left:auto;background:none;border:none;cursor:pointer;font-size:1.1rem;color:var(--fg,#222)">✕</button>
    </div>
    <div id="demo-sidebar-content" style="flex:1;overflow-y:auto;padding:12px 16px"></div>`;
  document.body.appendChild(el);

  const style = document.createElement("style");
  style.textContent = `
    .demo-sidebar {
      position:fixed; top:0; right:0;
      width:420px; max-width:95vw; height:100vh;
      background:var(--surface,#fff);
      box-shadow:-4px 0 24px rgba(0,0,0,0.18);
      z-index:1000; display:flex; flex-direction:column;
      transition:transform 0.28s ease; overflow-y:auto;
    }
    .demo-sidebar--hidden { transform:translateX(100%); }
    .demo-sidebar__header {
      display:flex; align-items:center; gap:8px;
      padding:14px 16px; border-bottom:1px solid var(--border,#ddd);
      background:var(--surface,#fff); position:sticky; top:0; z-index:1;
    }
    .demo-result-text { font-size:0.83rem; line-height:1.65; white-space:pre-wrap; }
    .demo-slide { border:1px solid var(--border,#ddd); border-radius:6px; padding:10px 14px; margin-bottom:10px; }
    .demo-slide__title { font-size:0.84rem; font-weight:700; margin:0 0 6px; }
    .demo-slide ul { margin:0; padding-left:18px; font-size:0.8rem; }
    .demo-chat-msg { font-size:0.8rem; margin-bottom:8px; padding:8px 10px; border-radius:6px; }
    .demo-chat-msg.user { background:var(--primary,#c8430b); color:#fff; align-self:flex-end; }
    .demo-chat-msg.assistant { background:var(--bg,#f8f5f1); }
    .demo-chat-wrap { display:flex; flex-direction:column; gap:4px; }
    .demo-chat-input { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px solid var(--border,#ddd); }
    .demo-chat-input textarea { flex:1; font-size:0.8rem; border:1px solid var(--border,#ddd); border-radius:6px; padding:6px; resize:none; font-family:inherit; }
    .demo-chat-input button { padding:6px 12px; background:var(--primary,#c8430b); color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.8rem; }
    .demo-spinner { text-align:center; padding:30px; font-size:0.85rem; color:var(--muted,#888); }
    @media(max-width:600px){ .demo-sidebar{ width:100vw; } }
  `;
  document.head.appendChild(style);

  document.getElementById("demo-sidebar-close").addEventListener("click", _closeSidebar);
  return el;
}

let _sidebar = null;

function _getSidebar() {
  if (!_sidebar) _sidebar = document.getElementById("demo-sidebar") || _buildSidebar();
  return _sidebar;
}

function _openSidebar(title) {
  const sb = _getSidebar();
  sb.classList.remove("demo-sidebar--hidden");
  document.getElementById("demo-sidebar-title").textContent = title;
  document.getElementById("demo-sidebar-content").innerHTML =
    `<div class="demo-spinner">⏳ Loading…</div>`;
}

function _closeSidebar() {
  _getSidebar().classList.add("demo-sidebar--hidden");
}

function _setContent(html) {
  document.getElementById("demo-sidebar-content").innerHTML = html;
}

// ─── Simple markdown → HTML ───────────────────────────────────────
function _md(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br>");
}

// ─── Mermaid lazy loader ──────────────────────────────────────────
let _mermaidLoaded = false;

function _loadMermaid() {
  return new Promise((resolve) => {
    if (_mermaidLoaded || window.mermaid) { _mermaidLoaded = true; resolve(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js";
    s.onload = () => { _mermaidLoaded = true; resolve(); };
    s.onerror = () => resolve();
    document.head.appendChild(s);
  });
}

// ─── Result renderers ─────────────────────────────────────────────
function _renderText(data) {
  _setContent(`<div class="demo-result-text">${_md(esc(data.result))}</div>`);
}

function _renderPresentation(data) {
  if (data.parse_error || !data.slides?.length) {
    _setContent(`<div class="demo-result-text">${_md(esc(data.result))}</div>`);
    return;
  }
  const html = data.slides.map(s => `
    <div class="demo-slide">
      <h3 class="demo-slide__title">Slide ${s.slide} — ${esc(s.title || "")}</h3>
      <ul>${(s.bullets || []).map(b => `<li>${esc(b)}</li>`).join("")}</ul>
    </div>`).join("");
  _setContent(html);
}

async function _renderFlowchart(data) {
  await _loadMermaid();
  const content = document.getElementById("demo-sidebar-content");
  if (!window.mermaid) {
    content.innerHTML = `<pre style="font-size:0.75rem;overflow-x:auto">${esc(data.result)}</pre>`;
    return;
  }
  content.innerHTML = `<div class="mermaid">${esc(data.result)}</div>`;
  try {
    await window.mermaid.run({ nodes: content.querySelectorAll(".mermaid") });
  } catch {
    content.innerHTML = `<pre style="font-size:0.75rem;overflow-x:auto">${esc(data.result)}</pre>`;
  }
}

function _renderChat(data, text, history) {
  const wrap = document.createElement("div");
  wrap.className = "demo-chat-wrap";
  history.forEach(turn => {
    const div = document.createElement("div");
    div.className = `demo-chat-msg ${turn.role}`;
    div.innerHTML = _md(esc(turn.content));
    wrap.appendChild(div);
  });
  const latest = document.createElement("div");
  latest.className = "demo-chat-msg assistant";
  latest.innerHTML = _md(esc(data.result));
  wrap.appendChild(latest);

  const inputBar = document.createElement("div");
  inputBar.className = "demo-chat-input";
  inputBar.innerHTML = `
    <textarea id="demo-chat-msg" rows="2" placeholder="Ask a follow-up…"></textarea>
    <button id="demo-chat-send">Send</button>`;

  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = "";
  content.appendChild(wrap);
  content.appendChild(inputBar);

  document.getElementById("demo-chat-send").addEventListener("click", () => _sendChat(text));
  document.getElementById("demo-chat-msg").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); _sendChat(text); }
  });
}

async function _sendChat(text) {
  const ta  = document.getElementById("demo-chat-msg");
  const msg = ta?.value.trim();
  if (!msg) return;
  ta.value = "";
  ta.disabled = true;
  document.getElementById("demo-chat-send").disabled = true;

  _chatHistory.push({ role: "user", content: msg });
  if (_chatHistory.length > 12) _chatHistory = _chatHistory.slice(-12);

  try {
    const r = await apiFetch("/api/demo", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "chat", text, message: msg,
        history: _chatHistory.slice(-6), language: currentLang || "fr"
      })
    });
    const data = await r.json();
    _chatHistory.push({ role: "assistant", content: data.result });
    _renderChat(data, text, _chatHistory.slice(-6));
  } catch {
    // restore on error
  } finally {
    if (ta) { ta.disabled = false; ta.focus(); }
    const btn = document.getElementById("demo-chat-send");
    if (btn) btn.disabled = false;
  }
}

// ─── Main action launcher ─────────────────────────────────────────
export async function launchDemoAction(action, context) {
  _openSidebar(_label(action));
  _chatHistory = [];

  let text = "";

  if (context.type === "file") {
    // Extract text from file
    try {
      const r = await apiFetch("/api/extract", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: context.filename, max_chars: 8000 })
      });
      if (!r.ok) throw new Error("extraction failed");
      const d = await r.json();
      text = d.chunks.map(c => c.text).join("\n\n").slice(0, 8000);
    } catch {
      _setContent(`<div style="color:var(--error,#c0392b);font-size:0.83rem">
        Could not extract text from this file. Try a .pdf, .txt, .md, .html, or .docx file.</div>`);
      return;
    }
  } else {
    text = context.text || "";
  }

  if (!text.trim()) {
    _setContent(`<div style="font-size:0.83rem;color:var(--muted,#888)">No text to process.</div>`);
    return;
  }

  if (action === "chat") _chatText = text;

  try {
    const payload = { action, text, language: currentLang || "fr" };
    if (action === "chat") payload.message = "Please introduce this document briefly.";
    const r = await apiFetch("/api/demo", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!r.ok) throw new Error("demo failed");
    const data = await r.json();

    if (action === "chat") {
      _chatHistory = [
        { role: "user", content: "Please introduce this document briefly." },
        { role: "assistant", content: data.result }
      ];
      _renderChat(data, text, _chatHistory);
    } else if (action === "presentation") {
      _renderPresentation(data);
    } else if (action === "flowchart") {
      await _renderFlowchart(data);
    } else {
      _renderText(data);
    }
  } catch {
    _setContent(`<div style="color:var(--error,#c0392b);font-size:0.83rem">
      Could not reach the AI backend. Check that Ollama is running or configure a DeepSeek API key.</div>`);
  }
}

// ─── Bootstrap ────────────────────────────────────────────────────
export function initDemo() {
  // Right-click on file entries → context menu
  document.addEventListener("contextmenu", e => {
    const fileEntry = e.target.closest("[data-filename]");
    if (!fileEntry) return;
    e.preventDefault();
    showDemoContextMenu(e.clientX, e.clientY, {
      type:     "file",
      filename: fileEntry.dataset.filename,
      filetype: fileEntry.dataset.filetype || ""
    });
  });

  // Text selection → context menu
  document.addEventListener("mouseup", e => {
    if (_getMenu().contains(e.target)) return;
    const sel  = window.getSelection();
    const text = sel?.toString().trim();
    if (text && text.length > 20) {
      const range = sel.getRangeAt(0);
      const rect  = range.getBoundingClientRect();
      showDemoContextMenu(rect.right, rect.bottom, { type: "selection", text });
    }
  });

  // Menu item click
  _getMenu().addEventListener("click", e => {
    const li = e.target.closest("[data-action]");
    if (!li || !_ctx) return;
    const action = li.dataset.action;
    _hideMenu();
    launchDemoAction(action, _ctx);
  });

  // Hide menu on outside click or Escape
  document.addEventListener("click", e => {
    if (!_getMenu().contains(e.target)) _hideMenu();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { _hideMenu(); _closeSidebar(); }
  });
}
