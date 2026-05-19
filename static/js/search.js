// ── Search — form, results, URL download, quick-download modal ────
import { t } from './i18n.js';
import { apiFetch, $, esc, showMsg } from './api.js';
import { trackProgress, renderQueuePanel } from './download.js';

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
    const openUrl = r.url || r.link || '';
    const pdfUrl  = r.pdf_url || '';
    const authors = Array.isArray(r.authors) ? r.authors.slice(0, 3).join(', ') : (r.authors || '');
    const journal = Array.isArray(r.journal) ? (r.journal[0] || '') : (r.journal || '');
    const byline  = [authors, r.year ? String(r.year) : '', journal ? `<em>${esc(journal)}</em>` : '', esc(r.source || '')]
      .filter(Boolean).join(' · ');
    const snippet  = Array.isArray(r.snippet) ? (r.snippet[0] || '') : (r.snippet || '');
    const titleHtml = openUrl
      ? `<a class="result-title-link" href="${esc(openUrl)}" target="_blank" rel="noopener noreferrer">${esc(r.title || '—')}</a>`
      : pdfUrl
        ? `<a class="result-title-link" href="${esc(pdfUrl)}" target="_blank" rel="noopener noreferrer">${esc(r.title || '—')}</a>`
        : `<span class="result-title-plain">${esc(r.title || '—')}</span>`;
    return `
    <div class="result-item" style="animation:fadeIn 0.12s ${i*0.02}s both">
      <div class="result-title">${titleHtml}</div>
      ${byline  ? `<div class="result-byline">${byline}</div>` : ''}
      ${snippet ? `<div class="card-snippet">${esc(snippet)}</div>` : ''}
      ${pdfUrl  ? `<button class="card-btn dl" style="margin-top:6px" data-action="quick-download" data-url="${esc(pdfUrl)}">⬇ Download PDF</button>` : ''}
    </div>`;
  }).join('');
}

export function quickDownload(url) {
  $('modalUrl').value = url;
  $('modalMsg').className = 'msg';
  $('modalProgressDone').textContent = $('modalProgressPct').textContent = '';
  $('modalProgressFill').style.width = '0%';
  $('modalProgress').classList.remove('active');
  $('modalConfirm').disabled = false;
  $('modalBg').classList.add('open');
}

export function initSearch() {
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
    $('searchSpin').classList.add('active');
    $('btnSearch').disabled = true;
    try {
      const r = await apiFetch('/api/search', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({query: text, sources, limit: 50, lang})
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      allResults = d.results || [];
      activeFilter = 'all';
      renderResults();
      const langHint = d.detected_lang === 'fr' ? ' 🇫🇷' : d.detected_lang === 'en' ? ' 🇬🇧' : '';
      const msg = allResults.length
        ? `${allResults.length} résultats / results${langHint}`
        : 'Aucun résultat / No results';
      showMsg($('searchMsg'), allResults.length ? 'ok' : 'err', msg);
    } catch(e) {
      showMsg($('searchMsg'), 'err', 'Search failed: ' + e.message);
    } finally {
      $('searchSpin').classList.remove('active');
      $('btnSearch').disabled = false;
    }
  });

  // Event delegation for quick-download buttons in results
  $('resultsGrid').addEventListener('click', e => {
    const btn = e.target.closest('[data-action="quick-download"]');
    if (btn) quickDownload(btn.dataset.url);
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
      showMsg($('modalMsg'), 'err', e.message);
      $('modalSpin').classList.remove('active');
      $('modalConfirm').disabled = false;
    }
  });
}
