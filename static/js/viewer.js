// ── In-app link viewer — external URL iframe overlay ──────────────
import { t } from './i18n.js';

export const VIEWER_DOMAINS = [
  'doi.org', 'dx.doi.org',
  'jstor.org', 'springer.com', 'springerlink.com',
  'wiley.com', 'onlinelibrary.wiley.com',
  'sciencedirect.com', 'elsevier.com',
  'tandfonline.com', 'taylorandfrancis.com',
  'nature.com', 'science.org',
  'cambridge.org', 'oxford.com', 'oxfordjournals.org',
  'researchgate.net',
];

export function isViewerDomain(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return VIEWER_DOMAINS.some(d => host === d || host.endsWith('.' + d));
  } catch (_) { return false; }
}

export function shouldOpenViewer(url) {
  if (isViewerDomain(url)) return true;
  try {
    const path = new URL(url).pathname;
    if (path.endsWith('/') || !path.includes('.')) return true;
    const ext = path.split('.').pop().toLowerCase();
    if (['html', 'htm'].includes(ext)) return true;
  } catch (_) {}
  return false;
}

export function openViewer(url, title) {
  const panel = document.getElementById('linkViewerPanel');
  if (!panel) return;
  document.getElementById('linkViewerTitle').textContent = title || url;
  document.getElementById('linkViewerUrlBar').value      = url;
  document.getElementById('linkViewerFrame').src         = url;
  panel.style.display = 'flex';
  document.getElementById('linkViewerClose').focus();
}

export function closeViewer() {
  const panel = document.getElementById('linkViewerPanel');
  if (!panel) return;
  panel.style.display = 'none';
  document.getElementById('linkViewerFrame').src = 'about:blank';
}

export function initViewer() {
  const panel = document.getElementById('linkViewerPanel');
  if (!panel) return;

  document.getElementById('linkViewerClose').addEventListener('click', closeViewer);

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && panel.style.display !== 'none') closeViewer();
  });

  document.getElementById('linkViewerBack').addEventListener('click', () => {
    try { document.getElementById('linkViewerFrame').contentWindow.history.back(); } catch (_) {}
  });

  document.getElementById('linkViewerFwd').addEventListener('click', () => {
    try { document.getElementById('linkViewerFrame').contentWindow.history.forward(); } catch (_) {}
  });

  document.getElementById('linkViewerReload').addEventListener('click', () => {
    const frame = document.getElementById('linkViewerFrame');
    try { frame.contentWindow.location.reload(); }
    catch (_) { const s = frame.src; frame.src = 'about:blank'; frame.src = s; }
  });

  document.getElementById('linkViewerFrame').addEventListener('load', () => {
    try {
      const cw = document.getElementById('linkViewerFrame').contentWindow;
      const loc = cw.location.href;
      if (loc && loc !== 'about:blank') {
        document.getElementById('linkViewerUrlBar').value = loc;
        const ttl = document.getElementById('linkViewerFrame').contentDocument?.title;
        if (ttl) document.getElementById('linkViewerTitle').textContent = ttl;
      }
    } catch (_) {} // cross-origin — silently ignore
  });

  document.getElementById('linkViewerUrlBar').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const url = e.target.value.trim();
      if (url) document.getElementById('linkViewerFrame').src = url;
    }
  });
}
