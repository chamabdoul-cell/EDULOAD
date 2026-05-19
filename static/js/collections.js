// ── Collections and history UI ────────────────────────────────────
import { t } from './i18n.js';
import { apiFetch, $, esc, showMsg } from './api.js';
import { openViewer, currentFiles } from './download.js';

// ── History ───────────────────────────────────────────────────────
export async function loadHistory() {
  try { const r = await apiFetch('/api/history'); renderHistory(await r.json()); } catch(e) {}
}

function renderHistory(items) {
  const el = $('historyList');
  if (!items.length) {
    el.innerHTML = `<div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--muted);padding:8px 0">${t('no_history')}</div>`;
    return;
  }
  el.innerHTML = items.map(h => {
    const date      = (h.ts || '').slice(0, 10);
    const size      = h.size_kb ? `${h.size_kb} KB` : '';
    const fileExists = currentFiles.some(f => f.name === h.filename);
    return `<div class="hist-item" data-action="view-history" data-filename="${esc(h.filename)}" data-exists="${fileExists}">
      <div class="hist-title" title="${esc(h.title||h.filename)}">${esc(h.title||h.filename||'—')}</div>
      <div class="hist-meta">
        <span class="hist-source">${esc(h.source||'')}</span>
        <span>${date}</span>
        ${size ? `<span>${size}</span>` : ''}
        ${!fileExists ? `<span style="color:#c0614a">${t('file_missing')}</span>` : ''}
      </div>
      ${h.tags ? `<div class="hist-tags"># ${esc(h.tags)}</div>` : ''}
      <div class="hist-actions">
        <button class="icon-btn" data-action="add-to-collection" data-id="${h.id}" title="Add to collection">🗂</button>
        <button class="icon-btn del" data-action="delete-history" data-id="${h.id}" title="Remove">🗑</button>
      </div>
    </div>`;
  }).join('');
}

async function deleteHistory(id) {
  await apiFetch(`/api/history/${id}`, {method:'DELETE'});
  loadHistory();
}

// ── Collections ───────────────────────────────────────────────────
export async function loadCollections() {
  try { const r = await apiFetch('/api/collections'); renderCollections(await r.json()); } catch(e) {}
}

function renderCollections(cols) {
  const el = $('collectionsList');
  if (!cols.length) {
    el.innerHTML = `<div style="font-family:'IBM Plex Mono',monospace;font-size:0.72rem;color:var(--muted);padding:8px 0">${t('no_collections')}</div>`;
    return;
  }
  el.innerHTML = cols.map(c => `
    <div class="coll-item">
      <div class="coll-name">
        <span>${esc(c.name)}</span>
        <button class="icon-btn del" data-action="delete-collection" data-id="${c.id}" title="Delete">🗑</button>
      </div>
      ${c.description ? `<div class="coll-desc">${esc(c.description)}</div>` : ''}
      <div style="margin-top:6px">
        <button class="icon-btn" data-action="view-collection" data-id="${c.id}" style="font-size:0.68rem;padding:3px 8px">👁 View items</button>
      </div>
    </div>`).join('');
}

async function deleteCollection(id) {
  if (!confirm(t('coll_delete_confirm'))) return;
  await apiFetch(`/api/collections/${id}`, {method:'DELETE'});
  loadCollections();
}

async function viewCollection(id) {
  try {
    const d     = await (await apiFetch(`/api/collections/${id}`)).json();
    const items = d.items || [];
    alert(`Collection: ${d.collection.name}\n\n${items.length ? items.map(i=>`• ${i.title||i.filename||'?'}`).join('\n') : '(empty)'}`);
  } catch(e) {}
}

function showAddToCollection(historyId) {
  $('addToCollHistoryId').value = historyId;
  $('addToCollMsg').className = 'msg';
  apiFetch('/api/collections').then(r=>r.json()).then(cols => {
    $('addToCollSelect').innerHTML = '<option value="">— select —</option>' +
      cols.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');
    $('addToCollModalBg').classList.add('open');
  });
}

export function initCollections() {
  // Event delegation for history list
  $('historyList').addEventListener('click', e => {
    // action buttons take priority — check them first to avoid bubbling into view-history
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    e.stopPropagation();
    const { action, id, filename, exists } = btn.dataset;
    if (action === 'view-history') {
      if (!filename) return;
      if (exists === 'true') { const ext = filename.split('.').pop().toLowerCase(); openViewer(filename, ext); }
      else if (confirm('File is missing. Switch to URL tab to re-download?')) document.querySelector('[data-tab="url"]').click();
    }
    if (action === 'add-to-collection') showAddToCollection(id);
    if (action === 'delete-history')    deleteHistory(id);
  });

  // Event delegation for collections list
  $('collectionsList').addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const { action, id } = btn.dataset;
    if (action === 'delete-collection') deleteCollection(id);
    if (action === 'view-collection')   viewCollection(id);
  });

  // Refresh buttons
  $('btnRefreshHistory').addEventListener('click', loadHistory);
  $('btnRefreshCollections').addEventListener('click', loadCollections);

  // New collection modal
  $('btnNewCollection').addEventListener('click', () => {
    $('collName').value = $('collDesc').value = '';
    $('collModalMsg').className = 'msg';
    $('collModalBg').classList.add('open');
  });
  $('collModalCancel').addEventListener('click', () => $('collModalBg').classList.remove('open'));
  $('collModalBg').addEventListener('click', e => { if(e.target===$('collModalBg')) $('collModalBg').classList.remove('open'); });

  $('collModalConfirm').addEventListener('click', async () => {
    const name = $('collName').value.trim();
    const desc = $('collDesc').value.trim();
    if (!name) return showMsg($('collModalMsg'), 'err', t('coll_missing_name'));
    try {
      const r = await apiFetch('/api/collections', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({name, description: desc})
      });
      if (!r.ok) throw new Error((await r.json()).detail || 'failed');
      $('collModalBg').classList.remove('open');
      loadCollections();
    } catch(e) { showMsg($('collModalMsg'), 'err', e.message); }
  });

  // Add-to-collection modal
  $('addToCollCancel').addEventListener('click', () => $('addToCollModalBg').classList.remove('open'));
  $('addToCollModalBg').addEventListener('click', e => { if(e.target===$('addToCollModalBg')) $('addToCollModalBg').classList.remove('open'); });

  $('addToCollConfirm').addEventListener('click', async () => {
    const collId    = $('addToCollSelect').value;
    const historyId = $('addToCollHistoryId').value;
    if (!collId) return showMsg($('addToCollMsg'), 'err', t('add_to_coll_missing'));
    try {
      const r = await apiFetch(`/api/collections/${collId}/items`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({history_id: parseInt(historyId)})
      });
      if (!r.ok) throw new Error('failed');
      $('addToCollModalBg').classList.remove('open');
    } catch(e) { showMsg($('addToCollMsg'), 'err', e.message); }
  });
}
