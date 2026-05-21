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
  el.setAttribute("role", "menu");
  el.style.cssText = "display:none;position:fixed;z-index:9999;";
  const ul = document.createElement("ul");
  ul.style.cssText = [
    "list-style:none", "margin:0", "padding:4px 0",
    "background:var(--panel,#1a1814)", "border:1px solid var(--border,#ddd)",
    "border-radius:8px", "box-shadow:0 4px 16px rgba(0,0,0,0.15)",
    "min-width:190px", "font-size:0.82rem"
  ].join(";");
  ACTIONS.forEach((action, idx) => {
    const li = document.createElement("li");
    li.dataset.action = action;
    li.setAttribute("role", "menuitem");
    li.setAttribute("tabindex", idx === 0 ? "0" : "-1");
    li.textContent = `${ICONS[action]} ${_label(action)}`;
    li.style.cssText = "padding:8px 16px;cursor:pointer;white-space:nowrap;color:#e8e3d8;";
    li.addEventListener("mouseenter", () => { li.style.background = "var(--accent,#c8430b)"; li.style.color="#fff"; });
    li.addEventListener("mouseleave", () => { li.style.background = ""; li.style.color="#e8e3d8"; });
    li.addEventListener("keydown", e => {
      const items = [...ul.querySelectorAll("[role=menuitem]")];
      const i = items.indexOf(li);
      if (e.key === "ArrowDown") { e.preventDefault(); items[(i+1) % items.length].focus(); }
      if (e.key === "ArrowUp")   { e.preventDefault(); items[(i-1+items.length) % items.length].focus(); }
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); li.click(); }
    });
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
  const vw = window.innerWidth, vh = window.innerHeight;
  const mw = 200, mh = ACTIONS.length * 38;
  menu.style.left = Math.min(x, vw - mw - 8) + "px";
  menu.style.top  = Math.min(y, vh - mh - 8) + "px";
  // Focus first item for keyboard nav
  const first = menu.querySelector("[role=menuitem]");
  if (first) first.focus();
}

function _hideMenu() {
  _getMenu().style.display = "none";
}

// ─── Mobile bottom sheet (uses static #ai-bottom-sheet from HTML) ─
function _showBottomSheet() {
  document.getElementById("ai-bottom-sheet")?.classList.add("open");
  document.getElementById("ai-bottom-sheet-overlay")?.classList.add("open");
}
function _closeBottomSheet() {
  document.getElementById("ai-bottom-sheet")?.classList.remove("open");
  document.getElementById("ai-bottom-sheet-overlay")?.classList.remove("open");
}

// ─── FAB (uses static #ai-fab from HTML) ──────────────────────────
let _fab = null;

function _showFab(x, y, context) {
  if (!_fab) _fab = document.getElementById("ai-fab");
  if (!_fab) return;
  _fab.textContent = `✨ ${t("fab_analyse") || "Analyse"}`;
  const vw = window.innerWidth;
  _fab.style.left = Math.min(x, vw - 140) + "px";
  _fab.style.top  = (y + 6) + "px";
  _fab.style.display = "block";
  _fab._pendingCtx = context;
}

function _hideFab() {
  if (!_fab) _fab = document.getElementById("ai-fab");
  if (_fab) _fab.style.display = "none";
}

// ─── Sidebar ──────────────────────────────────────────────────────
function _buildSidebar() {
  const el = document.createElement("div");
  el.id = "demo-sidebar";
  el.className = "demo-sidebar demo-sidebar--hidden";
  el.innerHTML = `
    <div class="demo-sidebar__header">
      <span id="demo-sidebar-title" style="font-weight:600;font-size:0.9rem"></span>
      <button id="demo-sidebar-close" style="margin-left:auto;background:none;border:none;cursor:pointer;font-size:1.1rem;color:var(--fg,#222)" aria-label="Close">✕</button>
    </div>
    <div id="demo-sidebar-content" style="flex:1;overflow-y:auto;padding:12px 16px"></div>`;
  document.body.appendChild(el);

  const style = document.createElement("style");
  style.textContent = `
    .demo-sidebar {
      position:fixed; top:0; right:0;
      width:420px; max-width:95vw; height:100vh;
      background:var(--paper,#f5f2eb);
      box-shadow:-4px 0 24px rgba(0,0,0,0.18);
      z-index:1000; display:flex; flex-direction:column;
      transition:transform 0.28s ease; overflow-y:auto;
    }
    .demo-sidebar--hidden { transform:translateX(100%); }
    .demo-sidebar__header {
      display:flex; align-items:center; gap:8px;
      padding:14px 16px; border-bottom:1px solid var(--border,#ddd);
      background:var(--cream,#ede8db); position:sticky; top:0; z-index:1;
    }
    .demo-result-text { font-size:0.83rem; line-height:1.65; white-space:pre-wrap; }
    .demo-slide { border:1px solid var(--border,#ddd); border-radius:6px; padding:10px 14px; margin-bottom:10px; }
    .demo-slide__title { font-size:0.84rem; font-weight:700; margin:0 0 6px; }
    .demo-slide ul { margin:0; padding-left:18px; font-size:0.8rem; }
    .demo-chat-msg { font-size:0.8rem; margin-bottom:8px; padding:8px 10px; border-radius:6px; }
    .demo-chat-msg.user { background:var(--accent,#c8430b); color:#fff; align-self:flex-end; }
    .demo-chat-msg.assistant { background:var(--cream,#ede8db); }
    .demo-chat-wrap { display:flex; flex-direction:column; gap:4px; }
    .demo-chat-input { display:flex; gap:6px; margin-top:10px; padding-top:10px; border-top:1px solid var(--border,#ddd); }
    .demo-chat-input textarea { flex:1; font-size:0.8rem; border:1px solid var(--border,#ddd); border-radius:6px; padding:6px; resize:none; font-family:inherit; }
    .demo-chat-input button { padding:6px 12px; background:var(--accent,#c8430b); color:#fff; border:none; border-radius:6px; cursor:pointer; font-size:0.8rem; }
    .demo-spinner { text-align:center; padding:30px; font-size:0.85rem; color:var(--muted,#888); }
    .demo-truncation-warning {
      display:flex; align-items:flex-start; gap:8px;
      background:#fff3cd; color:#856404; border:1px solid #ffc107;
      border-radius:6px; padding:8px 10px; margin-bottom:12px; font-size:0.78rem;
    }
    .demo-truncation-warning button { margin-left:auto; background:none; border:none; cursor:pointer; color:#856404; font-size:0.85rem; padding:0 4px; }
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

// ─── Truncation warning banner ────────────────────────────────────
function _truncationBanner() {
  const div = document.createElement("div");
  div.className = "demo-truncation-warning";
  div.innerHTML = `<span>⚠️</span><span>${t("truncation_warning")}</span><button aria-label="Dismiss">✕</button>`;
  div.querySelector("button").addEventListener("click", () => div.remove());
  return div;
}

// ─── Mermaid lazy loader (local bundle) ──────────────────────────
let _mermaidLoaded = false;

function _loadMermaid() {
  return new Promise((resolve) => {
    if (_mermaidLoaded || window.mermaid) { _mermaidLoaded = true; resolve(); return; }
    const s = document.createElement("script");
    s.src = "/static/js/vendor/mermaid.min.js";
    s.onload  = () => { _mermaidLoaded = true; resolve(); };
    s.onerror = () => resolve(); // error boundary — fall back to raw text
    document.head.appendChild(s);
  });
}

// ─── Result renderers ─────────────────────────────────────────────
function _renderText(data, truncated) {
  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = "";
  if (truncated) content.appendChild(_truncationBanner());
  const div = document.createElement("div");
  div.className = "demo-result-text";
  div.innerHTML = _md(esc(data.result));
  content.appendChild(div);
}

function _renderPresentation(data, truncated) {
  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = "";
  if (truncated) content.appendChild(_truncationBanner());
  if (data.parse_error || !data.slides?.length) {
    const div = document.createElement("div");
    div.className = "demo-result-text";
    div.innerHTML = _md(esc(data.result));
    content.appendChild(div);
    return;
  }
  data.slides.forEach(s => {
    const slide = document.createElement("div");
    slide.className = "demo-slide";
    slide.innerHTML = `
      <h3 class="demo-slide__title">Slide ${s.slide} — ${esc(s.title || "")}</h3>
      <ul>${(s.bullets || []).map(b => `<li>${esc(b)}</li>`).join("")}</ul>`;
    content.appendChild(slide);
  });
}

async function _renderFlowchart(data, truncated) {
  await _loadMermaid();
  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = "";
  if (truncated) content.appendChild(_truncationBanner());
  if (!window.mermaid) {
    const pre = document.createElement("pre");
    pre.style.cssText = "font-size:0.75rem;overflow-x:auto";
    pre.textContent = data.result;
    content.appendChild(pre);
    return;
  }
  const diagram = document.createElement("div");
  diagram.className = "mermaid";
  diagram.textContent = data.result;
  content.appendChild(diagram);
  try {
    await window.mermaid.run({ nodes: [diagram] });
  } catch {
    diagram.replaceWith(Object.assign(document.createElement("pre"),
      { style: "font-size:0.75rem;overflow-x:auto", textContent: data.result }));
  }
}

function _renderChat(data, text, history, truncated) {
  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = "";
  if (truncated) content.appendChild(_truncationBanner());
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
    _renderChat(data, text, _chatHistory.slice(-6), false);
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
  let truncated = false;

  if (context.type === "file") {
    try {
      const r = await apiFetch("/api/extract", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: context.filename, max_chars: 8000 })
      });
      if (!r.ok) throw new Error("extraction failed");
      const d = await r.json();
      text      = d.chunks.map(c => c.text).join("\n\n").slice(0, 8000);
      truncated = !!d.truncated;
    } catch {
      _setContent(`<div style="color:var(--accent,#c8430b);font-size:0.83rem">
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
      _renderChat(data, text, _chatHistory, truncated);
    } else if (action === "presentation") {
      _renderPresentation(data, truncated);
    } else if (action === "flowchart") {
      await _renderFlowchart(data, truncated);
    } else {
      _renderText(data, truncated);
    }
  } catch {
    _setContent(`<div style="color:var(--accent,#c8430b);font-size:0.83rem">
      Could not reach the AI backend. Check that Ollama is running or configure a DeepSeek API key.</div>`);
  }
}

// ─── Direct trigger for file (replaces need for right-click) ──────
export function openDemoForFile(filename) {
  const filetype = (filename || "").split(".").pop().toLowerCase();
  _ctx = { type: "file", filename, filetype };
  const sb = _getSidebar();
  sb.classList.remove("demo-sidebar--hidden");
  document.getElementById("demo-sidebar-title").textContent = filename;
  const content = document.getElementById("demo-sidebar-content");
  content.innerHTML = `
    <div style="padding:4px 0 14px;font-size:0.82rem;color:var(--muted,#888)">${t("ai_action_btn") || "AI"} — choose an action:</div>
    <div style="display:flex;flex-direction:column;gap:8px">
      ${ACTIONS.map(a => `
        <button data-action="${a}" style="display:flex;align-items:center;gap:12px;padding:11px 14px;border:1px solid var(--border,#ddd);border-radius:6px;background:var(--cream,#ede8db);cursor:pointer;font-size:0.85rem;text-align:left;font-family:inherit;">
          <span style="font-size:1.2rem">${ICONS[a]}</span><span>${_label(a)}</span>
        </button>`).join("")}
    </div>`;
  content.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("mouseenter", () => btn.style.borderColor = "var(--accent,#c8430b)");
    btn.addEventListener("mouseleave", () => btn.style.borderColor = "var(--border,#ddd)");
    btn.addEventListener("click", () => launchDemoAction(btn.dataset.action, _ctx));
  });
}

// ─── Bootstrap ────────────────────────────────────────────────────
export function initDemo() {
  // Populate static bottom sheet buttons once
  const bsContainer = document.getElementById("ai-bottom-sheet-btns");
  if (bsContainer && !bsContainer.children.length) {
    ACTIONS.forEach(action => {
      const btn = document.createElement("button");
      btn.className = "demo-sheet-action";
      btn.dataset.action = action;
      btn.innerHTML = `<span style="font-size:1.3rem">${ICONS[action]}</span><span>${_label(action)}</span>`;
      btn.addEventListener("click", () => { _closeBottomSheet(); if (_ctx) launchDemoAction(action, _ctx); });
      bsContainer.appendChild(btn);
    });
  }
  // Wire static bottom sheet close button and overlay
  document.getElementById("ai-bottom-sheet-close")?.addEventListener("click", _closeBottomSheet);
  document.getElementById("ai-bottom-sheet-overlay")?.addEventListener("click", _closeBottomSheet);

  // Wire static FAB click
  const fab = document.getElementById("ai-fab");
  if (fab) {
    fab.addEventListener("click", () => {
      const pending = _fab?._pendingCtx;
      _hideFab();
      if (!pending) return;
      _ctx = pending;
      if (window.innerWidth <= 768) {
        _showBottomSheet();
      } else {
        showDemoContextMenu(parseFloat(fab.style.left), parseFloat(fab.style.top), _ctx);
      }
    });
  }

  // Right-click on file entries → context menu / bottom sheet
  document.addEventListener("contextmenu", e => {
    const fileEntry = e.target.closest("[data-filename]");
    if (!fileEntry) return;
    e.preventDefault();
    _ctx = { type: "file", filename: fileEntry.dataset.filename, filetype: fileEntry.dataset.filetype || "" };
    if (window.innerWidth <= 768) {
      _showBottomSheet();
    } else {
      showDemoContextMenu(e.clientX, e.clientY, _ctx);
    }
  });

  // Text selection → FAB or bottom sheet
  document.addEventListener("mouseup", e => {
    if (_getMenu().contains(e.target)) return;
    const sel  = window.getSelection();
    const text = sel?.toString().trim();
    if (text && text.length > 20) {
      const range = sel.getRangeAt(0);
      const rect  = range.getBoundingClientRect();
      const ctx   = { type: "selection", text };
      if (window.innerWidth <= 768) {
        _ctx = ctx;
        _showBottomSheet();
      } else {
        _showFab(rect.right, rect.bottom, ctx);
      }
    } else {
      _hideFab();
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
    if (!_getMenu().contains(e.target) && e.target !== _fab) _hideMenu();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { _hideMenu(); _closeSidebar(); _closeBottomSheet(); _hideFab(); }
  });
}
