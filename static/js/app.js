// ── App entry point — initialisation and settings ─────────────────
import { applyTranslations, setLang, currentLang } from './i18n.js';
import { initAuth } from './auth.js';
import { $ } from './api.js';
import { loadStatus, renderQueuePanel } from './download.js';
import { initDownload } from './download.js';
import { initSearch } from './search.js';
import { loadHistory, loadCollections, initCollections } from './collections.js';

// Inject fadeIn keyframe animation
const _st = document.createElement('style');
_st.textContent = '@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}';
document.head.appendChild(_st);

// ── Settings ──────────────────────────────────────────────────────
import { apiFetch, showMsg } from './api.js';

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

// ── Tabs ──────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
    tab.classList.add('active');
    $('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'history')     loadHistory();
    if (tab.dataset.tab === 'collections') loadCollections();
  }));
}

// ── Bootstrap ─────────────────────────────────────────────────────
window.autoOpenViewer = true;

applyTranslations();
initTabs();
initAuth({ onLoginSuccess: () => { loadStatus(); loadSettings(); } });
initDownload();
initSearch();
initCollections();
initSettings();
loadStatus();
loadSettings();
setInterval(loadStatus, 15000);
setInterval(renderQueuePanel, 2000);

// ── PWA service worker ────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}
