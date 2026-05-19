// ── Auth — token management and login modal ───────────────────────
import { t } from './i18n.js';

export let _multiUser = false;
export function setMultiUser(val) { _multiUser = val; }
export function getMultiUser()    { return _multiUser; }

export function getAccessToken()  { return localStorage.getItem('access_token'); }
export function getRefreshToken() { return localStorage.getItem('refresh_token'); }

export function setTokens(access, refresh) {
  localStorage.setItem('access_token', access);
  if (refresh) localStorage.setItem('refresh_token', refresh);
}

export function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

export function showLoginModal() {
  document.getElementById('loginModalBg').classList.add('open');
  document.getElementById('btnLogout').style.display = 'none';
}

export function hideLoginModal() {
  document.getElementById('loginModalBg').classList.remove('open');
  document.getElementById('btnLogout').style.display = '';
}

// Wired up by app.js after all modules load
export function initAuth({ onLoginSuccess }) {
  const btnLogin    = document.getElementById('btnLogin');
  const btnLogout   = document.getElementById('btnLogout');
  const pwInput     = document.getElementById('loginPassword');
  const msgEl       = document.getElementById('loginMsg');

  async function doLogin() {
    const email    = document.getElementById('loginEmail').value.trim();
    const password = pwInput.value;
    if (!email || !password) return;
    btnLogin.disabled = true;
    const showMsg = (type, text) => {
      msgEl.className = 'msg ' + type; msgEl.textContent = text;
    };
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email, password})
      });
      if (r.status === 401) { showMsg('err', t('login_error_invalid')); return; }
      if (!r.ok) throw new Error('network');
      const d = await r.json();
      setTokens(d.access_token, d.refresh_token);
      pwInput.value = '';
      msgEl.className = 'msg';
      hideLoginModal();
      onLoginSuccess();
    } catch {
      showMsg('err', t('login_error_network'));
    } finally {
      btnLogin.disabled = false;
    }
  }

  btnLogin.addEventListener('click', doLogin);
  pwInput.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

  btnLogout.addEventListener('click', () => {
    clearTokens();
    showLoginModal();
  });
}
