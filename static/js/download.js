// ── Download — file list, progress, queue, viewer, convert ────────
import { t, currentLang } from './i18n.js';
import { apiFetch, $, fmtBytes, extIcon, esc, VIEWABLE_EXTS, showMsg, notify } from './api.js';
import { shouldOpenViewer, openViewer as openLinkViewer } from './viewer.js';
import { openDemoForFile } from './demo.js';

export let currentFiles = [];
export const activeEvtSources = {};

// ─── Tool hints (3.2) ─────────────────────────────────────────────
const TOOL_HINTS = {
  ffmpeg: {
    desc: "Video → MP3 conversion and audio processing",
    linux: "sudo apt install ffmpeg",
    macos: "brew install ffmpeg",
    docker: "Already included in the Dockerfile",
  },
  pandoc: {
    desc: "DOCX → PDF and HTML → PDF conversion",
    linux: "sudo apt install pandoc",
    macos: "brew install pandoc",
    docker: "Add: RUN apt-get install -y pandoc in Dockerfile",
  },
};

let _toolPopover = null;

function _showToolPopover(name, ok, anchorEl) {
  if (_toolPopover) _toolPopover.remove();
  const hint = TOOL_HINTS[name];
  const rect = anchorEl.getBoundingClientRect();
  _toolPopover = document.createElement("div");
  _toolPopover.style.cssText = [
    "position:fixed", `top:${rect.bottom + 6}px`, `left:${rect.left}px`,
    "z-index:9000", "background:var(--panel,#1a1814)", "color:#e8e3d8",
    "border:1px solid var(--border,#3a3628)", "border-radius:8px",
    "padding:12px 16px", "font-size:0.75rem", "max-width:260px",
    "box-shadow:0 4px 16px rgba(0,0,0,.35)", "font-family:'IBM Plex Mono',monospace",
    "line-height:1.6",
  ].join(";");
  _toolPopover.innerHTML = ok
    ? `<strong>${name}</strong> ✓ installed<br><span style="color:var(--muted,#8a8070)">${hint?.desc || ""}</span>`
    : `<strong>${name}</strong> ✗ not found
       ${hint ? `<br><span style="color:var(--muted,#8a8070)">${hint.desc}</span>
       <br><br><strong>Linux:</strong> <code>${hint.linux}</code>
       <br><strong>macOS:</strong> <code>${hint.macos}</code>
       <br><strong>Docker:</strong> ${hint.docker}` : ""}`;
  document.body.appendChild(_toolPopover);
  // Close on next click outside
  setTimeout(() => document.addEventListener("click", function _cls() {
    _toolPopover?.remove(); _toolPopover = null;
    document.removeEventListener("click", _cls);
  }), 0);
}

// ─── File list filter/sort state (2.1) ───────────────────────────
let _fileFilter = "";
let _fileSort   = "name-az";

function _applyFilterSort(files) {
  let result = files;
  if (_fileFilter) {
    const q = _fileFilter.toLowerCase();
    result = result.filter(f => f.name.toLowerCase().includes(q));
  }
  switch (_fileSort) {
    case "name-az":   result = [...result].sort((a,b) => a.name.localeCompare(b.name)); break;
    case "name-za":   result = [...result].sort((a,b) => b.name.localeCompare(a.name)); break;
    case "largest":   result = [...result].sort((a,b) => b.size - a.size); break;
    case "smallest":  result = [...result].sort((a,b) => a.size - b.size); break;
    // "newest" / "oldest" require mtime which API doesn't provide — fall through to name
    default: break;
  }
  return result;
}

// ─── File list renderer ───────────────────────────────────────────
export function renderFileList(files) {
  currentFiles = files;
  const list = $('dlList');
  const filtered = _applyFilterSort(files);
  if (!filtered.length) {
    list.innerHTML = `<div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--muted);padding:8px 0">${
      _fileFilter ? "No matching files." : t('no_files')
    }</div>`;
    return;
  }
  const tpl = document.getElementById('tpl-file-item');
  list.innerHTML = '';
  for (const f of filtered) {
    const node = document.importNode(tpl.content, true);
    const root = node.querySelector('.dl-item') || node.firstElementChild;
    if (root) { root.dataset.filename = f.name; root.dataset.filetype = f.ext; }
    node.querySelector('.dl-icon').textContent = extIcon(f.ext);
    const nameEl = node.querySelector('.dl-name');
    nameEl.textContent = f.name; nameEl.title = f.name;
    node.querySelector('.dl-size').textContent = fmtBytes(f.size);
    const viewBtn = node.querySelector('[data-action="view"]');
    viewBtn.dataset.name = f.name; viewBtn.dataset.ext = f.ext;
    const saveA = node.querySelector('[data-action="save"]');
    saveA.href = `/api/file/${encodeURIComponent(f.name)}`; saveA.download = f.name;
    node.querySelector('[data-action="delete-file"]').dataset.name = f.name;
    const aiBtn = node.querySelector('[data-action="demo-ai"]');
    if (aiBtn) { aiBtn.dataset.name = f.name; aiBtn.title = t('ai_action_btn') || 'AI'; }
    list.appendChild(node);
  }
}

export function populateConvertSelect(files) {
  const sel = $('convertFile');
  sel.innerHTML = '<option value="">— select file —</option>' +
    files.map(f => `<option value="${esc(f.name)}">${esc(f.name)}</option>`).join('');
}

export async function deleteFile(name) {
  await apiFetch(`/api/file/${encodeURIComponent(name)}`, {method:'DELETE'});
  loadStatus();
}

// ─── Progress tracking (SSE) ──────────────────────────────────────
export function trackProgress(jobId, opts) {
  if (activeEvtSources[jobId]) activeEvtSources[jobId].close();
  const es = new EventSource(`/api/progress/${jobId}`);
  activeEvtSources[jobId] = es;

  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if (opts.wrapEl) opts.wrapEl.classList.add('active');

    if (d.status === 'queued') {
      if (opts.pctEl)  opts.pctEl.textContent = `Queued (pos ${d.position ?? '?'})`;
      if (opts.fillEl) opts.fillEl.style.width = '0%';
    } else if (d.status === 'running') {
      const pct = d.progress || 0;
      if (opts.fillEl)  opts.fillEl.style.width  = pct + '%';
      // Show "Resuming…" label when picking up a partial download (1.3)
      const pctLabel = d.resumed && pct < 5 ? 'Resuming…' : pct.toFixed(1) + '%';
      if (opts.pctEl)   opts.pctEl.textContent   = pctLabel;
      if (opts.speedEl) opts.speedEl.textContent = d.speed || '';
      if (opts.etaEl)   opts.etaEl.textContent   = d.eta ? 'ETA ' + d.eta : '';
    } else if (d.status === 'done') {
      if (opts.fillEl)  opts.fillEl.style.width  = '100%';
      if (opts.pctEl)   opts.pctEl.textContent   = '100%';
      if (opts.speedEl) opts.speedEl.textContent = '';
      if (opts.etaEl)   opts.etaEl.textContent   = '';
      if (opts.doneEl)  opts.doneEl.textContent  = `✓ ${d.file || 'Done'}`;
      es.close(); delete activeEvtSources[jobId];
      loadStatus();
      if (d.file && window.autoOpenViewer) {
        const ext = d.file.split('.').pop().toLowerCase();
        if (VIEWABLE_EXTS.includes(ext)) openViewer(d.file, ext);
      }
      notify(`✓ Downloaded: ${d.file || 'file'}`, 'success');
      if (opts.onDone) opts.onDone(d);
    } else if (d.status === 'error') {
      if (opts.pctEl) opts.pctEl.textContent = '✗ Error: ' + (d.error || 'unknown');
      es.close(); delete activeEvtSources[jobId];
      notify(`Download failed: ${d.error || 'unknown error'}`, 'error');
      if (opts.onError) opts.onError(d);
    }
    renderQueuePanel();
  };
  es.onerror = () => { es.close(); delete activeEvtSources[jobId]; };
}

// ─── Queue panel ──────────────────────────────────────────────────
export function renderQueuePanel() {
  apiFetch('/api/queue').then(r => r.json()).then(jobs => {
    const section = $('queueSection');
    const listEl  = $('queueList');
    const active  = jobs.filter(j => ['queued','running','done','error'].includes(j.status));
    if (!active.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    listEl.innerHTML = active.map(j => {
      const short = j.url.length > 40 ? j.url.slice(0,38) + '…' : j.url;
      const bar   = j.status === 'running'
        ? `<div class="progress-bar" style="margin-top:4px"><div class="progress-fill" style="width:${j.progress||0}%"></div></div>`
        : '';
      const cancelBtn = j.status === 'queued'
        ? `<button class="icon-btn" data-action="cancel-job" data-id="${esc(j.job_id)}" title="Cancel" style="font-size:0.6rem">✕</button>`
        : '';
      const resumeTag = j.resumed ? `<span style="font-family:'IBM Plex Mono',monospace;font-size:0.58rem;color:var(--teal)">↺resume</span>` : '';
      return `<div class="queue-item">
        <span class="q-url" title="${esc(j.url)}">${esc(short)}</span>
        ${resumeTag}
        <span class="q-status ${j.status}">${j.status}</span>
        ${cancelBtn}
      </div>${bar}`;
    }).join('');
  }).catch(() => {});
}

export async function cancelJob(jobId) {
  await apiFetch(`/api/queue/${jobId}`, {method:'DELETE'});
  renderQueuePanel();
}

// ─── Status (tool badges + file list) ────────────────────────────
export async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    const { setMultiUser, showLoginModal, getAccessToken } = await import('./auth.js');
    setMultiUser(d.app_mode === 'multi_user');
    if (d.app_mode === 'multi_user') {
      document.getElementById('btnLogout').style.display = '';
      if (!getAccessToken()) { showLoginModal(); return; }
    } else {
      const adminTab = document.getElementById('adminTab');
      if (adminTab) adminTab.style.display = '';
    }

    currentFiles = d.files || [];
    const tb = $('toolBadges');
    tb.innerHTML = '';
    const aiLabel = d.ollama_available
      ? `Ollama (${d.ollama_model || 'mistral'})`
      : (d.deepseek_configured ? 'DeepSeek' : 'Keyword mode');
    const aiOk = d.ollama_available || d.deepseek_configured;
    [[aiLabel, aiOk, null], ['ffmpeg', d.tools.ffmpeg, 'ffmpeg'], ['pandoc', d.tools.pandoc, 'pandoc']]
      .forEach(([n, ok, hintKey]) => {
        const b = document.createElement(hintKey ? 'button' : 'span');
        b.className = 'tool-badge ' + (ok ? 'ok' : 'miss');
        b.textContent = ok ? `✓ ${n}` : `✗ ${n}`;
        if (hintKey) {
          b.style.cursor = 'pointer';
          b.title = 'Click for info';
          b.setAttribute('aria-label', `${n}: ${ok ? 'installed' : 'missing'}`);
          b.addEventListener('click', (e) => { e.stopPropagation(); _showToolPopover(hintKey, ok, b); });
        }
        tb.appendChild(b);
      });
    renderFileList(d.files);
    populateConvertSelect(d.files);
    if (d.market_segment === 'global-north') {
      document.getElementById('disclaimer-block').style.display = 'block';
      document.getElementById('gn-sources').style.display = 'block';
    }
    const seg = document.getElementById('market-segment-select');
    if (seg && d.market_segment) seg.value = d.market_segment;
    return d;
  } catch(e) {}
}

// ─── YouTube helpers ──────────────────────────────────────────────
function ytVideoId(url) {
  try {
    const u    = new URL(url);
    const host = u.hostname.replace(/^www\./, '');
    if (host === 'youtu.be') return u.pathname.slice(1).split('?')[0];
    if (host.includes('youtube.com')) {
      if (u.searchParams.get('v')) return u.searchParams.get('v');
      const m = u.pathname.match(/\/(?:embed|shorts|v)\/([^/?]+)/);
      if (m) return m[1];
    }
  } catch(_) {}
  return null;
}

export function openYouTubeViewer(videoId) {
  _clearPdfObject();
  $('viewerVideo').pause?.();
  $('viewerAudio').pause?.();
  $('viewerVideo').style.display = $('viewerAudio').style.display =
  $('viewerText').style.display  = 'none';
  $('viewerPlaceholder').style.display = 'none';
  const f = $('viewerIframe');
  f.src = `https://www.youtube.com/embed/${videoId}`;
  f.style.display = 'block';
  $('viewerTitle').textContent = 'YouTube';
  $('viewerExtLink').href = `https://www.youtube.com/watch?v=${videoId}`;
  $('viewerExtLink').style.display = 'inline-flex';
}

// ─── Subtitle helper ──────────────────────────────────────────────
function srtToVtt(srt) {
  return 'WEBVTT\n\n' + srt
    .replace(/\r\n/g, '\n')
    .replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2')
    .trim();
}

function _clearPdfObject() {
  const obj = document.querySelector('.pdf-object');
  if (obj) { obj.data = 'about:blank'; obj.style.display = 'none'; }
}

// ─── Mobile full-screen viewer modal (1.2) ───────────────────────
function _getMobileViewer() {
  return document.getElementById('mobile-viewer-overlay');
}

// ─── Viewer ───────────────────────────────────────────────────────

// Opens an external URL in the right-side viewer panel (not the full-screen overlay)
export function openViewerUrl(url, title) {
  if (window.innerWidth <= 768) {
    const mv    = _getMobileViewer();
    const titleEl = document.getElementById('mvTitle');
    const body  = document.getElementById('mvBody');
    if (titleEl) titleEl.textContent = title || url;
    if (body) {
      body.innerHTML = '';
      const iframe = document.createElement('iframe');
      iframe.src = url;
      iframe.style.cssText = 'width:100%;height:100%;border:none';
      iframe.sandbox = 'allow-scripts allow-same-origin allow-forms allow-popups';
      body.appendChild(iframe);
    }
    mv?.classList.add('open');
    return;
  }
  // Desktop: right-side viewer panel
  const ext = (() => {
    try { const p = new URL(url).pathname; return p.split('.').pop().toLowerCase(); } catch { return ''; }
  })();
  $('viewerTitle').textContent = title || url;
  $('viewerPlaceholder').style.display = 'none';
  $('viewerVideo').style.display = $('viewerAudio').style.display =
  $('viewerText').style.display = 'none';
  _clearPdfObject();
  const extLink = $('viewerExtLink');
  extLink.href = url; extLink.style.display = 'inline-flex';
  const cvBtn = $('viewerConvertBtn');
  if (cvBtn) cvBtn.style.display = 'none';

  if (ext === 'pdf') {
    const body = $('viewerBody');
    let obj = body.querySelector('.pdf-object');
    if (!obj) {
      obj = document.createElement('object');
      obj.className = 'pdf-object';
      obj.style.cssText = 'width:100%;height:100%;border:none;display:block';
      body.appendChild(obj);
    }
    obj.data = url + '#toolbar=1&view=FitH';
    obj.type = 'application/pdf';
    obj.style.display = 'block';
    obj.innerHTML = `<div style="padding:24px;text-align:center;color:var(--muted)">
      <p>PDF cannot be displayed inline.</p>
      <a href="${url}" target="_blank" class="card-btn" style="margin-top:12px;display:inline-block">Open PDF in new tab ↗</a>
    </div>`;
  } else {
    const f = $('viewerIframe');
    f.src = url;
    f.style.display = 'block';
  }
}

export async function openViewer(name, ext) {
  // On mobile: use full-screen overlay instead of the side panel (1.2)
  if (window.innerWidth <= 768) {
    _openMobileViewer(name, ext);
    return;
  }
  _openDesktopViewer(name, ext);
}

async function _openMobileViewer(name, ext) {
  const mv    = _getMobileViewer();
  const title = document.getElementById('mvTitle');
  const body  = document.getElementById('mvBody');
  title.textContent = name;
  body.innerHTML = '';
  mv.classList.add('open');
  const url = `/api/file/${encodeURIComponent(name)}`;

  if (['mp4','webm','mkv','avi','mov'].includes(ext)) {
    const v = document.createElement('video');
    v.controls = true; v.src = url;
    v.style.cssText = 'width:100%;max-height:100%';
    body.appendChild(v);
  } else if (['mp3','ogg','wav','flac','aac'].includes(ext)) {
    const a = document.createElement('audio');
    a.controls = true; a.src = url; a.style.width = '90%';
    body.appendChild(a);
  } else if (ext === 'pdf') {
    const iframe = document.createElement('iframe');
    iframe.src = url; iframe.style.cssText = 'width:100%;height:100%;border:none';
    body.appendChild(iframe);
  } else if (['txt','srt','md'].includes(ext)) {
    const pre = document.createElement('div');
    pre.style.cssText = 'padding:16px;font-family:"Lora",serif;font-size:0.88rem;line-height:1.7;width:100%;overflow:auto';
    apiFetch(url).then(r => r.text()).then(txt => { pre.textContent = txt; });
    body.appendChild(pre);
  } else {
    body.innerHTML = `<div style="text-align:center;padding:32px;color:var(--muted)">
      <div style="font-size:2.5rem">${extIcon(ext)}</div>
      <a href="${url}" download style="display:inline-block;margin-top:12px;padding:8px 16px;background:var(--accent);color:#fff;border-radius:6px;text-decoration:none">Download file</a>
    </div>`;
  }
}

async function _openDesktopViewer(name, ext) {
  const url = `/api/file/${encodeURIComponent(name)}`;
  $('viewerTitle').textContent = name;
  $('viewerPlaceholder').style.display = 'none';
  $('viewerVideo').style.display = $('viewerAudio').style.display =
  $('viewerIframe').style.display = $('viewerText').style.display = 'none';

  const extLink = $('viewerExtLink');
  extLink.href = url; extLink.style.display = 'inline-flex';

  // Show convert button in viewer toolbar (3.5)
  _updateViewerConvertBtn(name, ext);

  if (['mp4','webm','mkv','avi','mov'].includes(ext)) {
    const v = $('viewerVideo');
    [...v.querySelectorAll('track')].forEach(t => t.remove());
    v.src = url; v.style.display = 'block';
    const stem    = name.replace(/\.[^.]+$/, '');
    const srtFile = currentFiles.find(f => f.ext === 'srt' && f.name.startsWith(stem));
    if (srtFile) {
      try {
        const resp  = await apiFetch(`/api/file/${encodeURIComponent(srtFile.name)}`);
        const vtt   = srtToVtt(await resp.text());
        const blob  = new Blob([vtt], {type:'text/vtt'});
        const track = document.createElement('track');
        track.kind = 'subtitles'; track.src = URL.createObjectURL(blob); track.default = true;
        v.appendChild(track);
      } catch(_) {}
    }
  } else if (['mp3','ogg','wav','flac','aac'].includes(ext)) {
    const a = $('viewerAudio'); a.src = url; a.style.display = 'block';
  } else if (ext === 'pdf') {
    const body = $('viewerBody');
    let obj = body.querySelector('.pdf-object');
    if (!obj) {
      obj = document.createElement('object');
      obj.className = 'pdf-object';
      obj.style.cssText = 'width:100%;height:100%;border:none;display:block';
      body.appendChild(obj);
    }
    obj.data = url + '#toolbar=1&view=FitH';
    obj.type = 'application/pdf';
    obj.style.display = 'block';
    obj.innerHTML = `<div style="padding:24px;text-align:center;color:var(--muted)">
      <p>PDF cannot be displayed inline.</p>
      <a href="${url}" target="_blank" class="card-btn" style="margin-top:12px;display:inline-block">Open PDF in new tab ↗</a>
    </div>`;
  } else if (['html','htm'].includes(ext)) {
    const f = $('viewerIframe'); f.src = url; f.style.display = 'block';
  } else if (['txt','srt','md'].includes(ext)) {
    apiFetch(url).then(r => r.text()).then(txt => {
      const d = $('viewerText'); d.textContent = txt; d.style.display = 'block';
    });
  } else {
    $('viewerPlaceholder').style.display = 'flex';
    $('viewerPlaceholder').innerHTML = `<div class="vp-icon">${extIcon(ext)}</div><p>No preview — <a href="${url}" download>save file</a></p>`;
  }
}

// ─── Convert button in viewer toolbar (3.5) ──────────────────────
const CONVERT_OPTIONS = {
  mp4:  ['mp3'],
  webm: ['mp3'],
  mkv:  ['mp3'],
  avi:  ['mp3'],
  mov:  ['mp3'],
  pdf:  ['docx'],
  html: ['pdf'],
  htm:  ['pdf'],
  md:   ['pdf'],
  docx: ['pdf'],
  doc:  ['pdf'],
};

let _currentViewerFile = null;

function _updateViewerConvertBtn(name, ext) {
  _currentViewerFile = { name, ext };
  const btn = $('viewerConvertBtn');
  if (!btn) return;
  const opts = CONVERT_OPTIONS[ext] || [];
  if (!opts.length) { btn.style.display = 'none'; return; }
  btn.style.display = 'inline-flex';
  btn.dataset.name  = name;
  btn.dataset.ext   = ext;
}

async function _viewerConvert(name, ext) {
  const opts = CONVERT_OPTIONS[ext] || [];
  if (!opts.length) return;
  const to = opts[0]; // single option for now; extend to dropdown if needed
  const btn = $('viewerConvertBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const r = await apiFetch('/api/convert', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({filename: name, to_fmt: to})
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Conversion failed');
    notify(`✓ Converted: ${d.file}`, 'success');
    loadStatus();
    if (window.autoOpenViewer) {
      const newExt = d.file.split('.').pop().toLowerCase();
      if (VIEWABLE_EXTS.includes(newExt)) openViewer(d.file, newExt);
    }
  } catch(e) {
    notify(`Conversion failed: ${e.message}`, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = t('convert_in_viewer') || 'Convert'; }
  }
}

// ─── Init (wires all download-related event listeners) ───────────
export function initDownload() {
  // Filter and sort controls for file list (2.1)
  const filterInput = $('fileFilterInput');
  const sortSelect  = $('fileSortSelect');
  if (filterInput) {
    filterInput.addEventListener('input', e => {
      _fileFilter = e.target.value;
      renderFileList(currentFiles);
    });
  }
  if (sortSelect) {
    sortSelect.addEventListener('change', e => {
      _fileSort = e.target.value;
      renderFileList(currentFiles);
    });
  }

  $('refreshFiles').addEventListener('click', loadStatus);
  $('btnClearDone').addEventListener('click', () => { renderQueuePanel(); loadStatus(); });

  // Event delegation for file list actions
  $('dlList').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const { action, name, ext } = btn.dataset;
    if (action === 'view')        openViewer(name, ext);
    if (action === 'delete-file') deleteFile(name);
    if (action === 'demo-ai')     openDemoForFile(name);
  });

  // Event delegation for queue cancel
  $('queueList').addEventListener('click', e => {
    const btn = e.target.closest('[data-action="cancel-job"]');
    if (btn) cancelJob(btn.dataset.id);
  });

  // Mobile viewer close
  const mvCloseBtn = $('mvClose');
  if (mvCloseBtn) mvCloseBtn.addEventListener('click', () => {
    _getMobileViewer()?.classList.remove('open');
  });

  // Viewer close
  $('closeViewer').addEventListener('click', () => {
    $('viewerVideo').pause?.(); $('viewerAudio').pause?.();
    $('viewerVideo').style.display = $('viewerAudio').style.display =
    $('viewerIframe').style.display = $('viewerText').style.display = 'none';
    $('viewerIframe').src = 'about:blank';
    _clearPdfObject();
    $('viewerExtLink').style.display = 'none';
    $('viewerPlaceholder').style.display = 'flex';
    $('viewerPlaceholder').innerHTML = `<div class="vp-icon">🔬</div><p>${t('viewer_placeholder')}</p>`;
    $('viewerTitle').textContent = t('viewer_no_file');
    _currentViewerFile = null;
    const cvBtn = $('viewerConvertBtn');
    if (cvBtn) cvBtn.style.display = 'none';
  });

  // Viewer convert button (3.5)
  const cvBtn = $('viewerConvertBtn');
  if (cvBtn) {
    cvBtn.addEventListener('click', () => {
      const { name, ext } = cvBtn.dataset;
      if (name && ext) _viewerConvert(name, ext);
    });
  }

  // URL input → show/hide play button
  $('urlInput').addEventListener('input', () => {
    const vid = ytVideoId($('urlInput').value.trim());
    $('btnPlay').style.display = vid ? '' : 'none';
  });
  $('btnPlay').addEventListener('click', () => {
    const vid = ytVideoId($('urlInput').value.trim());
    if (vid) openYouTubeViewer(vid);
  });

  // URL download
  $('btnDownload').addEventListener('click', async () => {
    const url = $('urlInput').value.trim();
    if (!url) return showMsg($('dlMsg'), 'err', t('url_required'));
    if (shouldOpenViewer(url)) { openLinkViewer(url, url); return; }
    $('dlSpin').classList.add('active');
    $('btnDownload').disabled = true;
    $('urlProgressFill').style.width = '0%';
    ['urlProgressPct','urlProgressSpeed','urlProgressEta','urlProgressDone'].forEach(id => { const el = $(id); if (el) el.textContent = ''; });
    try {
      const disclaimerAccepted = document.getElementById('disclaimer-accepted')?.checked ?? false;
      const r = await apiFetch('/api/download', {
        method:'POST',
        headers:{'Content-Type':'application/json','Accept-Language': currentLang},
        body: JSON.stringify({url, disclaimer_accepted: disclaimerAccepted})
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Download failed');
      trackProgress(d.job_id, {
        fillEl:  $('urlProgressFill'), pctEl:   $('urlProgressPct'),
        speedEl: $('urlProgressSpeed'), etaEl:  $('urlProgressEta'),
        doneEl:  $('urlProgressDone'), wrapEl:  $('urlProgress'),
        onDone:  () => { $('dlSpin').classList.remove('active'); $('btnDownload').disabled = false; },
        onError: data => { showMsg($('dlMsg'), 'err', data.error || 'Download failed'); $('dlSpin').classList.remove('active'); $('btnDownload').disabled = false; }
      });
      renderQueuePanel();
    } catch(e) {
      const msg = e.message || '';
      if (msg.includes('HTML') || msg.includes('401') || msg.includes('422')) {
        openLinkViewer(url, url);
      } else {
        showMsg($('dlMsg'), 'err', msg);
      }
      $('dlSpin').classList.remove('active');
      $('btnDownload').disabled = false;
    }
  });

  // Convert tab
  $('btnConvert').addEventListener('click', async () => {
    const file = $('convertFile').value;
    const to   = $('convertTo').value;
    if (!file) return showMsg($('convMsg'), 'err', t('convert_no_file'));
    $('convSpin').classList.add('active');
    $('btnConvert').disabled = true;
    try {
      const r = await apiFetch('/api/convert', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({filename: file, to_fmt: to})
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Conversion failed');
      showMsg($('convMsg'), 'ok', `✓ Created: ${d.file}`);
      loadStatus();
    } catch(e) {
      showMsg($('convMsg'), 'err', e.message);
    } finally {
      $('convSpin').classList.remove('active');
      $('btnConvert').disabled = false;
    }
  });
}
