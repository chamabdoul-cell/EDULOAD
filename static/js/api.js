// ── API — apiFetch helper and shared DOM utilities ────────────────
import { t } from './i18n.js';
import {
  getMultiUser, getAccessToken, getRefreshToken, setTokens, clearTokens, showLoginModal
} from './auth.js';

// ── DOM shorthand ──────────────────────────────────────────────────
export const $ = id => document.getElementById(id);

// ── Formatting helpers ─────────────────────────────────────────────
export const fmtBytes = b =>
  b > 1e6 ? (b/1e6).toFixed(1)+'MB' : b > 1e3 ? (b/1e3).toFixed(0)+'KB' : b+'B';

export const extIcon = e => (
  {'pdf':'📄','mp4':'🎬','mp3':'🎵','docx':'📝','doc':'📝','html':'🌐',
   'htm':'🌐','txt':'📃','epub':'📖','zip':'📦','srt':'💬'}[e] || '📁'
);

export const esc = s => {
  if (s == null) return '';
  if (Array.isArray(s)) s = s[0] ?? '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
};

export const VIEWABLE_EXTS = [
  'mp4','webm','mkv','avi','mov','mp3','ogg','wav','flac','pdf','html','htm','txt','srt','md'
];

// ── Toast-style inline message ────────────────────────────────────
export function showMsg(el, type, text) {
  el.className = 'msg ' + type;
  el.textContent = text;
  if (type !== 'err') setTimeout(() => { el.className='msg'; el.textContent=''; }, 5000);
}

// ── Token refresh ─────────────────────────────────────────────────
async function _refreshToken() {
  const rt = getRefreshToken();
  if (!rt) return false;
  try {
    const r = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({refresh_token: rt})
    });
    if (!r.ok) return false;
    const d = await r.json();
    setTokens(d.access_token, null);
    return true;
  } catch { return false; }
}

// ── Authenticated fetch with auto-refresh ─────────────────────────
export async function apiFetch(url, options = {}) {
  if (getMultiUser()) {
    const tok = getAccessToken();
    if (tok) options.headers = Object.assign({}, options.headers || {}, {'Authorization': 'Bearer ' + tok});
  }
  let r = await fetch(url, options);
  if (r.status === 401 && getMultiUser()) {
    const ok = await _refreshToken();
    if (ok) {
      options.headers = Object.assign({}, options.headers || {}, {'Authorization': 'Bearer ' + getAccessToken()});
      r = await fetch(url, options);
    } else {
      clearTokens();
      showLoginModal();
      throw new Error(t('session_expired'));
    }
  }
  return r;
}
