// ── App entry point — initialisation and settings ─────────────────
import { applyTranslations, setLang, currentLang } from './i18n.js';
import { initAuth } from './auth.js';
import { $ } from './api.js';
import { loadStatus, renderQueuePanel, openYouTubeViewer } from './download.js';
import { initDownload } from './download.js';
import { initSearch } from './search.js';
import { loadHistory, loadCollections, initCollections } from './collections.js';
import { initDemo } from './demo.js';

// Inject fadeIn keyframe animation
const _st = document.createElement('style');
_st.textContent = '@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}';
document.head.appendChild(_st);

// ── Settings ──────────────────────────────────────────────────────
import { apiFetch, showMsg, esc } from './api.js';

let _settingsTimer = null;
function saveSetting(key, value) {
  clearTimeout(_settingsTimer);
  _settingsTimer = setTimeout(() => {
    apiFetch('/api/settings', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({[key]: value})
    });
  }, 600);
}

async function loadSettings() {
  try {
    const r = await apiFetch('/api/settings');
    const s = await r.json();
    if (s.dark_mode === 'true') {
      document.documentElement.setAttribute('data-theme', 'dark');
      $('settingDarkMode').checked = true;
    }
    if (s.download_dir)   $('settingDownloadDir').value   = s.download_dir;
    if (s.max_concurrent) $('settingMaxConcurrent').value = s.max_concurrent;
    if (s.auto_open_viewer !== undefined) {
      const val = s.auto_open_viewer !== 'false';
      $('settingAutoOpen').checked = val;
      window.autoOpenViewer = val;
    }
  } catch(e) {}
}

function initSettings() {
  $('btnSettings').addEventListener('click', () => $('settingsModalBg').classList.add('open'));
  $('settingsClose').addEventListener('click', () => $('settingsModalBg').classList.remove('open'));
  $('settingsModalBg').addEventListener('click', e => {
    if (e.target === $('settingsModalBg')) $('settingsModalBg').classList.remove('open');
  });
  $('btnLang').addEventListener('click', () => setLang(currentLang === 'fr' ? 'en' : 'fr'));
  $('settingLangEn').addEventListener('click', () => setLang('en'));
  $('settingLangFr').addEventListener('click', () => setLang('fr'));
  $('settingDownloadDir').addEventListener('input',  e => saveSetting('download_dir', e.target.value));
  $('settingMaxConcurrent').addEventListener('change', e => saveSetting('max_concurrent', e.target.value));
  $('settingAutoOpen').addEventListener('change', e => {
    window.autoOpenViewer = e.target.checked;
    saveSetting('auto_open_viewer', String(e.target.checked));
  });
  $('settingDarkMode').addEventListener('change', e => {
    if (e.target.checked) document.documentElement.setAttribute('data-theme', 'dark');
    else document.documentElement.removeAttribute('data-theme');
    saveSetting('dark_mode', String(e.target.checked));
  });
}

// ── Admin analytics ───────────────────────────────────────────────
async function loadAdminAnalytics() {
  try {
    const r    = await apiFetch('/api/admin/impact');
    const data = await r.json();
    const el   = $('adminAnalytics');
    el.innerHTML = `
      <div style="font-size:0.75rem;line-height:1.8">
        <div><strong>${data.total_downloads}</strong> downloads · <strong>${data.total_users}</strong> users</div>
        <div style="margin-top:4px"><em>Active this week:</em> ${data.active_users_week ?? 0}</div>
        <div style="margin-top:6px;font-weight:600">Top queries</div>
        ${(data.top_queries || []).slice(0,5).map(q=>`<div style="padding:2px 0">${esc(q.query_stem)} <span style="color:var(--muted)">(${q.count})</span></div>`).join('')}
        <div style="margin-top:6px;font-weight:600">Top sources</div>
        ${(data.top_sources || []).map(s=>`<div style="padding:2px 0">${esc(s.source)} <span style="color:var(--muted)">(${s.n})</span></div>`).join('')}
      </div>`;
    drawAnalyticsChart(data.downloads_by_day || []);
  } catch(e) {}
}

function drawAnalyticsChart(byDay) {
  const canvas = $('analyticsChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!byDay.length) return;
  const counts = byDay.map(d => d.count);
  const max    = Math.max(...counts, 1);
  const w      = canvas.width, h = canvas.height;
  const bw     = Math.max(2, Math.floor((w - 20) / counts.length) - 2);
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#c8430b';
  counts.forEach((n, i) => {
    const bh = Math.round((n / max) * (h - 20));
    const x  = 10 + i * (bw + 2);
    const y  = h - bh;
    ctx.fillStyle = accent;
    ctx.fillRect(x, y, bw, bh);
  });
}

// ── Tabs ──────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
    tab.classList.add('active');
    $('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'history')     loadHistory();
    if (tab.dataset.tab === 'collections') loadCollections();
    if (tab.dataset.tab === 'admin')       loadAdminAnalytics();
  }));
}

// ── Branding ──────────────────────────────────────────────────────
function applyBranding(branding) {
  if (!branding) return;
  if (branding.primary_color)
    document.documentElement.style.setProperty('--accent', branding.primary_color);
  if (branding.logo_url) {
    const logo = document.querySelector('.brand-logo');
    if (logo) { logo.src = branding.logo_url; logo.style.display = 'block'; }
  }
}

// ── Sidebar toggle ────────────────────────────────────────────────
function initSidebarToggle() {
  const btn     = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  if (!btn || !sidebar) return;
  btn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
  });
}

// ── Resizable splitters ───────────────────────────────────────────
function initSplitters() {
  document.querySelectorAll('.splitter').forEach(splitter => {
    splitter.addEventListener('mousedown', e => {
      e.preventDefault();
      const leftPanel  = splitter.previousElementSibling;
      const rightPanel = splitter.nextElementSibling;
      const startX     = e.clientX;
      const leftStart  = leftPanel.getBoundingClientRect().width;
      const rightStart = rightPanel.getBoundingClientRect().width;
      splitter.classList.add('dragging');
      const onMove = mv => {
        const delta    = mv.clientX - startX;
        const newLeft  = Math.max(120, leftStart  + delta);
        const newRight = Math.max(160, rightStart - delta);
        leftPanel.style.flex  = `0 0 ${newLeft}px`;
        rightPanel.style.flex = `0 0 ${newRight}px`;
      };
      const onUp = () => {
        splitter.classList.remove('dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────
window.autoOpenViewer = true;
window.openYouTubeViewer = openYouTubeViewer;

applyTranslations();
initTabs();
initSidebarToggle();
initSplitters();
async function checkAdminAccess() {
  try {
    const r = await apiFetch('/api/admin/users');
    if (r.ok) $('adminTab').style.display = '';
  } catch(e) {}
}

initAuth({ onLoginSuccess: () => {
  loadStatus().then(s => {
    if (s && s.institution_branding) applyBranding(s.institution_branding);
  });
  loadSettings();
  checkAdminAccess();
}});
initDownload();
initSearch();
initCollections();
initDemo();
initSettings();
loadStatus().then(s => { if (s && s.institution_branding) applyBranding(s.institution_branding); });
loadSettings();
setInterval(loadStatus, 15000);
setInterval(renderQueuePanel, 2000);

// ── PWA service worker ────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}
