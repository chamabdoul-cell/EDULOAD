// ── Download — file list, progress, queue, viewer, convert ────────
import { t, currentLang } from './i18n.js';
import { apiFetch, $, fmtBytes, extIcon, esc, VIEWABLE_EXTS, showMsg } from './api.js';

export let currentFiles = [];
export const activeEvtSources = {};

// ── File list (uses #tpl-file-item template) ──────────────────────
export function renderFileList(files) {
  currentFiles = files;
  const list = $('dlList');
  if (!files.length) {
    list.innerHTML = `<div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--muted);padding:8px 0">${t('no_files')}</div>`;
    return;
  }
  const tpl = document.getElementById('tpl-file-item');
  list.innerHTML = '';
  for (const f of files) {
    const node = document.importNode(tpl.content, true);
    node.querySelector('.dl-icon').textContent = extIcon(f.ext);
    const nameEl = node.querySelector('.dl-name');
    nameEl.textContent = f.name; nameEl.title = f.name;
    node.querySelector('.dl-size').textContent = fmtBytes(f.size);
    const viewBtn = node.querySelector('[data-action="view"]');
    viewBtn.dataset.name = f.name; viewBtn.dataset.ext = f.ext;
    const saveA = node.querySelector('[data-action="save"]');
    saveA.href = `/api/file/${encodeURIComponent(f.name)}`; saveA.download = f.name;
    node.querySelector('[data-action="delete-file"]').dataset.name = f.name;
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

// ── Progress tracking (SSE) ───────────────────────────────────────
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
      if (opts.pctEl)   opts.pctEl.textContent   = pct.toFixed(1) + '%';
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
      if (opts.onDone) opts.onDone(d);
    } else if (d.status === 'error') {
      if (opts.pctEl) opts.pctEl.textContent = '✗ Error: ' + (d.error || 'unknown');
      es.close(); delete activeEvtSources[jobId];
      if (opts.onError) opts.onError(d);
    }
    renderQueuePanel();
  };
  es.onerror = () => { es.close(); delete activeEvtSources[jobId]; };
}

// ── Queue panel ───────────────────────────────────────────────────
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
      return `<div class="queue-item">
        <span class="q-url" title="${esc(j.url)}">${esc(short)}</span>
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

// ── Status (tool badges + file list) ─────────────────────────────
export async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    // Auth gate (sets multiUser flag via auth module — accessed via import in app.js)
    const { setMultiUser, showLoginModal, getAccessToken } = await import('./auth.js');
    setMultiUser(d.app_mode === 'multi_user');
    if (d.app_mode === 'multi_user') {
      document.getElementById('btnLogout').style.display = '';
      if (!getAccessToken()) { showLoginModal(); return; }
    } else {
      // single_user is always admin
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
    [[aiLabel, aiOk], ['ffmpeg', d.tools.ffmpeg], ['pandoc', d.tools.pandoc]].forEach(([n,ok]) => {
      const b = document.createElement('span');
      b.className = 'tool-badge ' + (ok ? 'ok' : 'miss');
      b.textContent = ok ? `✓ ${n}` : `✗ ${n}`;
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

// ── Subtitle helper ───────────────────────────────────────────────
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

// ── Viewer ────────────────────────────────────────────────────────
export async function openViewer(name, ext) {
  const url = `/api/file/${encodeURIComponent(name)}`;
  $('viewerTitle').textContent = name;
  $('viewerPlaceholder').style.display = 'none';
  $('viewerVideo').style.display = $('viewerAudio').style.display =
  $('viewerIframe').style.display = $('viewerText').style.display = 'none';

  const extLink = $('viewerExtLink');
  extLink.href = url; extLink.style.display = 'inline-flex';

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

// ── Init (wires all download-related event listeners) ─────────────
export function initDownload() {
  $('refreshFiles').addEventListener('click', loadStatus);
  $('btnClearDone').addEventListener('click', () => { renderQueuePanel(); loadStatus(); });

  // Event delegation for file list actions
  $('dlList').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const { action, name, ext } = btn.dataset;
    if (action === 'view') openViewer(name, ext);
    if (action === 'delete-file') deleteFile(name);
  });

  // Event delegation for queue cancel
  $('queueList').addEventListener('click', e => {
    const btn = e.target.closest('[data-action="cancel-job"]');
    if (btn) cancelJob(btn.dataset.id);
  });

  // Close viewer
  $('closeViewer').addEventListener('click', () => {
    $('viewerVideo').pause?.(); $('viewerAudio').pause?.();
    $('viewerVideo').style.display = $('viewerAudio').style.display =
    $('viewerIframe').style.display = $('viewerText').style.display = 'none';
    _clearPdfObject();
    $('viewerExtLink').style.display = 'none';
    $('viewerPlaceholder').style.display = 'flex';
    $('viewerPlaceholder').innerHTML = `<div class="vp-icon">🔬</div><p>${t('viewer_placeholder')}</p>`;
    $('viewerTitle').textContent = t('viewer_no_file');
  });

  // URL download
  $('btnDownload').addEventListener('click', async () => {
    const url = $('urlInput').value.trim();
    if (!url) return showMsg($('dlMsg'), 'err', t('url_required'));
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
      showMsg($('dlMsg'), 'err', e.message);
      $('dlSpin').classList.remove('active');
      $('btnDownload').disabled = false;
    }
  });

  // Convert
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

