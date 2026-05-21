// ── Search — form, results, URL download, quick-download modal ────
import { t } from './i18n.js';
import { apiFetch, $, esc, showMsg, notify } from './api.js';
import { trackProgress, renderQueuePanel, openViewerUrl } from './download.js';
import { shouldOpenViewer, openViewer as openLinkViewer } from './viewer.js';

const DEFAULT_SOURCES  = ['arxiv','openalex','doaj','gutenberg','archive','hal'];
const FR_SOURCES_EXTRA = ['hal','persee','openedition','erudit'];
const FR_STOPWORDS = new Set([
  'le','la','les','de','du','des','un','une','et','en','au','aux','sur',
  'avec','pour','par','que','qui','dans','est','sont','il','elle','nous',
  'vous','ils','elles','ce','se','ne','pas','plus','où','méthode','méthodes',
  'analyse','résultats','étude','approche','modèle','modèles','théorie',
  'éléments','finis','calcul','numérique','équation','solution','problème',
]);

function detectLang(text) {
  const words = text.toLowerCase().split(/\s+/);
  const hits  = words.filter(w => FR_STOPWORDS.has(w)).length;
  return hits >= 2 ? 'fr' : 'en';
}

let allResults   = [];
let activeFilter = 'all';

// ─── Recent search queries (3.3) ─────────────────────────────────
const MAX_RECENT = 10;

function _getRecent() {
  try { return JSON.parse(localStorage.getItem('scholara_recent_queries') || '[]'); }
  catch { return []; }
}

function _addRecent(query) {
  const prev = _getRecent().filter(q => q !== query);
  const next = [query, ...prev].slice(0, MAX_RECENT);
  localStorage.setItem('scholara_recent_queries', JSON.stringify(next));
  _renderRecentSearches();
}

function _clearRecent() {
  localStorage.removeItem('scholara_recent_queries');
  _renderRecentSearches();
}

function _renderRecentSearches() {
  const container = $('recentSearches');
  if (!container) return;
  const items = _getRecent();
  if (!items.length) { container.style.display = 'none'; return; }
  container.style.display = 'block';
  const list = $('recentList');
  if (list) {
    list.innerHTML = items.map(q =>
      `<span class="recent-chip" data-q="${esc(q)}" title="${esc(q)}">${esc(q.length > 28 ? q.slice(0,26) + '…' : q)}</span>`
    ).join('');
    list.querySelectorAll('.recent-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const nlInput = $('nlInput');
        if (nlInput) { nlInput.value = chip.dataset.q; nlInput.focus(); }
      });
    });
  }
}

// ─── Citation preview modal (2.4) ─────────────────────────────────
let _citeResultId = null;
let _citeCache    = {};
let _citeActiveTab = 'bibtex';

async function _openCiteModal(resultId) {
  _citeResultId   = resultId;
  _citeActiveTab  = 'bibtex';
  _citeCache      = {};
  const modal = $('citeModalBg');
  if (!modal) return;
  modal.classList.add('open');
  _renderCiteTab('bibtex');
  // Prefetch all three in parallel
  ['bibtex','ris','apa'].forEach(fmt => _fetchCite(fmt));
}

async function _fetchCite(fmt) {
  if (_citeCache[fmt] !== undefined) return;
  _citeCache[fmt] = '…loading…';
  try {
    const r = await apiFetch(`/api/cite/${_citeResultId}?format=${fmt}`);
    _citeCache[fmt] = r.ok ? await r.text() : `Error: ${r.status}`;
  } catch(e) {
    _citeCache[fmt] = `Error: ${e.message}`;
  }
  if (_citeActiveTab === fmt) _renderCiteTab(fmt);
}

function _renderCiteTab(fmt) {
  _citeActiveTab = fmt;
  const pre = $('citeContent');
  if (pre) pre.textContent = _citeCache[fmt] ?? '…loading…';
  document.querySelectorAll('.cite-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.citeFmt === fmt);
  });
}

// ─── Save to collection modal (2.5) ──────────────────────────────
let _pendingCollMeta = null; // {title, url, source, authors, year, journal}

export function showSaveToCollection(meta) {
  _pendingCollMeta = meta;
  const idEl  = $('addToCollHistoryId');
  const metaEl = $('addToCollPendingMeta');
  if (idEl)   idEl.value  = '';  // signal metadata path
  if (metaEl) metaEl.value = JSON.stringify(meta);
  const msg = $('addToCollMsg');
  if (msg) msg.className = 'msg';
  apiFetch('/api/collections').then(r => r.json()).then(cols => {
    const sel = $('addToCollSelect');
    if (sel) sel.innerHTML = '<option value="">— select —</option>' +
      cols.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
    $('addToCollModalBg').classList.add('open');
  });
}

// ─── Results renderer ─────────────────────────────────────────────
function renderResults() {
  const grid  = $('resultsGrid');
  const count = $('resCount');
  const pills = $('filterPills');

  const filtered = activeFilter === 'all' ? allResults
    : allResults.filter(r => r.source === activeFilter);

  const sources = [...new Set(allResults.map(r => r.source))];
  pills.innerHTML = ['All', ...sources].map(s => {
    const lbl    = s === 'All' ? 'all' : s;
    const active = activeFilter === lbl;
    return `<span class="pill${active?' active':''}" data-src="${lbl}">${
      s === 'All' ? `All (${allResults.length})` : `${allResults.find(r=>r.source===s)?.icon||''} ${s}`
    }</span>`;
  }).join('');
  pills.querySelectorAll('.pill').forEach(p => p.addEventListener('click', () => {
    activeFilter = p.dataset.src; renderResults();
  }));

  count.textContent   = filtered.length;
  count.style.display = filtered.length ? 'inline' : 'none';

  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state"><div class="big">🔍</div><p>${t('no_results')}</p></div>`;
    return;
  }

  grid.innerHTML = filtered.map((r, i) => {
    const openUrl  = r.url || r.link || '';
    const pdfUrl   = r.pdf_url || '';
    const ytId     = r.video_id || '';
    const authors  = Array.isArray(r.authors) ? r.authors.slice(0, 3).join(', ') : (r.authors || '');
    const journal  = Array.isArray(r.journal) ? (r.journal[0] || '') : (r.journal || '');
    const byline   = [authors, r.year ? String(r.year) : '', journal ? `<em>${esc(journal)}</em>` : '', esc(r.source || '')]
      .filter(Boolean).join(' · ');
    const snippet  = Array.isArray(r.snippet) ? (r.snippet[0] || '') : (r.snippet || '');
    const titleHtml = openUrl
      ? `<a class="result-title-link" href="${esc(openUrl)}" target="_self" rel="noopener noreferrer" data-action="open-link" data-url="${esc(openUrl)}" data-title="${esc(r.title || '')}">${esc(r.title || '—')}</a>`
      : pdfUrl
        ? `<a class="result-title-link" href="${esc(pdfUrl)}" target="_self" rel="noopener noreferrer" data-action="open-link" data-url="${esc(pdfUrl)}" data-title="${esc(r.title || '')}">${esc(r.title || '—')}</a>`
        : `<span class="result-title-plain">${esc(r.title || '—')}</span>`;
    const thumbHtml = ytId && r.thumbnail
      ? `<div style="position:relative;margin-bottom:6px;cursor:pointer" data-action="yt-play" data-vid="${esc(ytId)}">
           <img src="${esc(r.thumbnail)}" alt="" style="width:100%;border-radius:4px;display:block;max-height:140px;object-fit:cover">
           ${r.duration ? `<span style="position:absolute;bottom:4px;right:4px;background:rgba(0,0,0,.75);color:#fff;font-size:0.68rem;padding:1px 5px;border-radius:3px">${esc(r.duration)}</span>` : ''}
           <span style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:2rem;opacity:.85;pointer-events:none">▶</span>
         </div>`
      : '';
    const openInViewer = !ytId && openUrl && shouldOpenViewer(openUrl);
    // Cite button: only show if result has an id (history entry)
    const citeBtn = r.id
      ? `<button class="card-btn" data-action="cite-result" data-id="${r.id}">${t('cite_modal_title') || 'Cite'}</button>`
      : '';
    // Save to collection button (2.5)
    const saveMeta = JSON.stringify({
      title: r.title || '', url: openUrl || pdfUrl, source: r.source || '',
      authors: Array.isArray(r.authors) ? r.authors : [],
      year: r.year || null, journal: journal,
    }).replace(/"/g, '&quot;');
    const saveBtn = `<button class="card-btn" data-action="save-to-coll" data-meta="${saveMeta}" title="${t('save_to_collection')}">🗂 ${t('save_to_collection') || 'Save'}</button>`;

    const actionHtml = ytId
      ? `<div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
           <button class="card-btn" data-action="yt-play" data-vid="${esc(ytId)}">▶ Play</button>
           <button class="card-btn dl" data-action="yt-download" data-url="${esc(openUrl)}">⬇ Download</button>
           ${saveBtn}
         </div>`
      : `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
           ${openInViewer ? `<button class="card-btn" data-action="open-viewer" data-url="${esc(openUrl)}" data-title="${esc(r.title || '')}">${t('open_btn')}</button>` : ''}
           ${pdfUrl ? `<button class="card-btn dl" data-action="quick-download" data-url="${esc(pdfUrl)}">${t('download_pdf_btn')}</button>` : ''}
           ${citeBtn}
           ${saveBtn}
         </div>`;
    return `
    <div class="result-item" style="animation:fadeIn 0.12s ${i*0.02}s both">
      ${thumbHtml}
      <div class="result-title">${titleHtml}</div>
      ${byline  ? `<div class="result-byline">${byline}</div>` : ''}
      ${snippet ? `<div class="card-snippet">${esc(snippet)}</div>` : ''}
      ${actionHtml}
    </div>`;
  }).join('');

  // Persist results to sessionStorage for recovery after tab switch (3.3)
  try { sessionStorage.setItem('scholara_last_results', JSON.stringify(allResults)); } catch {}
}

export function quickDownload(url) {
  if (shouldOpenViewer(url)) { openLinkViewer(url, url); return; }
  $('modalUrl').value = url;
  $('modalMsg').className = 'msg';
  $('modalProgressDone').textContent = $('modalProgressPct').textContent = '';
  $('modalProgressFill').style.width = '0%';
  $('modalProgress').classList.remove('active');
  $('modalConfirm').disabled = false;
  $('modalBg').classList.add('open');
}

// Direct download from a result card — no modal, immediate POST /api/download
async function _downloadDirect(url) {
  try {
    const r = await apiFetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Download failed');
    renderQueuePanel();
    notify(`⬇ Download started`, 'info');
  } catch(e) {
    notify(`Download failed: ${e.message}`, 'error');
  }
}

export function initSearch() {
  // Restore last results from sessionStorage (3.3)
  try {
    const saved = sessionStorage.getItem('scholara_last_results');
    if (saved) { allResults = JSON.parse(saved); renderResults(); }
  } catch {}

  // Render recent searches on init (3.3)
  _renderRecentSearches();
  const clearRecentBtn = $('btnClearRecent');
  if (clearRecentBtn) clearRecentBtn.addEventListener('click', _clearRecent);

  // Search form
  $('btnSearch').addEventListener('click', async () => {
    const text = $('nlInput').value.trim();
    if (!text) return;
    const lang    = detectLang(text);
    const checked = [...document.querySelectorAll('input[name=src]:checked')].map(x => x.value);
    let sources   = checked.length ? checked : DEFAULT_SOURCES;
    if (lang === 'fr') {
      const extra = FR_SOURCES_EXTRA.filter(s => !sources.includes(s));
      sources = [...sources, ...extra];
    }
    const customJournal    = document.getElementById('custom-journal')?.value.trim() ?? '';
    const useGoogleScholar = document.getElementById('use-google-scholar')?.checked ?? false;
    let effectiveQuery = text;
    if (customJournal)    effectiveQuery += ` journal:"${customJournal}"`;
    if (useGoogleScholar) effectiveQuery += ' site:scholar.google.com';
    $('searchSpin').classList.add('active');
    $('btnSearch').disabled = true;
    try {
      const r = await apiFetch('/api/search', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({query: effectiveQuery, sources, limit: 50, lang})
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      allResults = d.results || [];
      activeFilter = 'all';
      renderResults();
      _addRecent(text); // persist query (3.3)
      const langHint = d.detected_lang === 'fr' ? ' 🇫🇷' : d.detected_lang === 'en' ? ' 🇬🇧' : '';
      const msg = allResults.length
        ? `${allResults.length} résultats / results${langHint}`
        : 'Aucun résultat / No results';
      showMsg($('searchMsg'), allResults.length ? 'ok' : 'err', msg);
    } catch(e) {
      notify(`Search failed: ${e.message}`, 'error');
      showMsg($('searchMsg'), 'err', 'Search failed: ' + e.message);
    } finally {
      $('searchSpin').classList.remove('active');
      $('btnSearch').disabled = false;
    }
  });

  // Event delegation for result card actions
  $('resultsGrid').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const { action, url, vid, id, meta } = btn.dataset;
    if (action === 'open-link') {
      e.preventDefault();
      openViewerUrl(url, btn.dataset.title || url);
    }
    if (action === 'open-viewer')    openViewerUrl(url, btn.dataset.title || url);
    if (action === 'quick-download') _downloadDirect(url);
    if (action === 'yt-play' && vid) window.openYouTubeViewer?.(vid);
    if (action === 'yt-download' && url) {
      const inp = $('urlInput');
      inp.value = url;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('[data-tab="url"]')?.click();
    }
    if (action === 'cite-result' && id) _openCiteModal(id);
    if (action === 'save-to-coll' && meta) {
      try { showSaveToCollection(JSON.parse(btn.dataset.meta.replace(/&quot;/g, '"'))); }
      catch {}
    }
  });

  // Citation modal tab switching (2.4)
  document.querySelectorAll('.cite-tab').forEach(btn => {
    btn.addEventListener('click', () => _renderCiteTab(btn.dataset.citeFmt));
  });

  // Citation copy button
  const copyBtn = $('citeCopyBtn');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const text = $('citeContent')?.textContent || '';
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = t('copied_feedback') || 'Copied!';
        setTimeout(() => { copyBtn.textContent = t('copy_btn') || 'Copy'; }, 2000);
      } catch {}
    });
  }

  // Citation download button (downloads active format)
  const dlBtn = $('citeDownloadBtn');
  if (dlBtn) {
    dlBtn.addEventListener('click', () => {
      const fmt  = _citeActiveTab;
      const text = _citeCache[fmt] || '';
      const blob = new Blob([text], {type:'text/plain'});
      const a    = document.createElement('a');
      a.href     = URL.createObjectURL(blob);
      a.download = `citation.${fmt === 'bibtex' ? 'bib' : fmt}`;
      a.click();
    });
  }

  // Close citation modal
  const citeClose = $('citeCloseBtn');
  const citeModalBg = $('citeModalBg');
  if (citeClose)   citeClose.addEventListener('click',   () => citeModalBg.classList.remove('open'));
  if (citeModalBg) citeModalBg.addEventListener('click', e => { if (e.target === citeModalBg) citeModalBg.classList.remove('open'); });

  // Custom context menu for result title links
  const _ctxMenu = document.getElementById('link-context-menu');
  let _ctxTarget = null;

  $('resultsGrid').addEventListener('contextmenu', e => {
    const link = e.target.closest('.result-title-link');
    if (!link) return;
    e.preventDefault();
    _ctxTarget = { url: link.dataset.url, title: link.dataset.title || link.dataset.url };
    _ctxMenu.style.display = 'block';
    const x = Math.min(e.clientX, window.innerWidth  - _ctxMenu.offsetWidth  - 8);
    const y = Math.min(e.clientY, window.innerHeight - _ctxMenu.offsetHeight - 8);
    _ctxMenu.style.left = x + 'px';
    _ctxMenu.style.top  = y + 'px';
  });

  _ctxMenu.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn || !_ctxTarget) return;
    _ctxMenu.style.display = 'none';
    const { action } = btn.dataset;
    if (action === 'ctx-open')     openViewerUrl(_ctxTarget.url, _ctxTarget.title);
    if (action === 'ctx-download') _downloadDirect(_ctxTarget.url);
    if (action === 'ctx-copy')     navigator.clipboard.writeText(_ctxTarget.url).catch(() => {});
  });

  document.addEventListener('click', e => {
    if (!_ctxMenu.contains(e.target)) _ctxMenu.style.display = 'none';
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') _ctxMenu.style.display = 'none';
  });

  // Quick download modal
  $('modalCancel').addEventListener('click', () => $('modalBg').classList.remove('open'));
  $('modalBg').addEventListener('click', e => { if(e.target===$('modalBg')) $('modalBg').classList.remove('open'); });

  $('modalConfirm').addEventListener('click', async () => {
    const url = $('modalUrl').value.trim();
    $('modalSpin').classList.add('active');
    $('modalConfirm').disabled = true;
    try {
      const disclaimerAccepted = document.getElementById('disclaimer-accepted')?.checked ?? false;
      const r = await apiFetch('/api/download', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({url, disclaimer_accepted: disclaimerAccepted})
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'failed');
      trackProgress(d.job_id, {
        fillEl:  $('modalProgressFill'), pctEl:   $('modalProgressPct'),
        speedEl: $('modalProgressSpeed'), etaEl:  $('modalProgressEta'),
        doneEl:  $('modalProgressDone'), wrapEl:  $('modalProgress'),
        onDone:  () => { $('modalSpin').classList.remove('active'); setTimeout(() => $('modalBg').classList.remove('open'), 1800); },
        onError: data => { showMsg($('modalMsg'), 'err', data.error || 'failed'); $('modalSpin').classList.remove('active'); $('modalConfirm').disabled = false; }
      });
      renderQueuePanel();
    } catch(e) {
      const msg = e.message || '';
      if (msg.includes('HTML') || msg.includes('401') || msg.includes('422')) {
        $('modalBg').classList.remove('open');
        openLinkViewer($('modalUrl').value.trim(), $('modalUrl').value.trim());
      } else {
        showMsg($('modalMsg'), 'err', msg);
      }
      $('modalSpin').classList.remove('active');
      $('modalConfirm').disabled = false;
    }
  });
}
