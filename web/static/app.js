/* Board Game Library — web client JS */

// ── Modal helpers ──────────────────────────────────────────────────────────
let _modalLastFocus = null;

function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  _modalLastFocus = document.activeElement;     // restore focus on close
  el.hidden = false;

  const dlg = el.querySelector('.modal');
  if (dlg) {
    dlg.setAttribute('role', 'dialog');
    dlg.setAttribute('aria-modal', 'true');
    dlg.setAttribute('tabindex', '-1');
    const h = dlg.querySelector('.modal-header h3, h3');
    if (h && h.textContent) dlg.setAttribute('aria-label', h.textContent.trim());
    const x = dlg.querySelector('.modal-close');
    if (x && !x.getAttribute('aria-label')) x.setAttribute('aria-label', 'Close dialog');
  }
  // Move focus into the dialog (first real control, else the dialog itself).
  const focusable = el.querySelector(
    'input:not([type=hidden]), select, textarea, button:not(.modal-close)');
  (focusable || dlg || el).focus();
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.hidden = true;
  if (_modalLastFocus && _modalLastFocus.focus) _modalLastFocus.focus();
  _modalLastFocus = null;
}

// ── Winner dropdown (populated from the listed players) ─────────────────────
// Fills a <select> with the players currently typed in `playersStr` (comma-
// separated) plus "All", preserving the current/custom selection.
function syncWinnerOptions(playersStr, selectEl, currentVal) {
  if (!selectEl) return;
  const names = (playersStr || '').split(',').map(s => s.trim()).filter(Boolean);
  const opts = ['', ...names, 'All'];
  if (currentVal && currentVal !== 'All' && !names.includes(currentVal)) {
    opts.splice(1, 0, currentVal);   // keep a pre-existing custom winner
  }
  selectEl.innerHTML = '';
  opts.forEach(v => {
    const o = document.createElement('option');
    o.value = v;
    o.textContent = v === '' ? '— none —' : (v === 'All' ? 'All (everyone won)' : v);
    if (v === (currentVal || '')) o.selected = true;
    selectEl.appendChild(o);
  });
}

// Live-bind a players text input to a winner <select>.
function bindWinner(playersInputId, winnerSelectId) {
  const pin = document.getElementById(playersInputId);
  const sel = document.getElementById(winnerSelectId);
  if (!pin || !sel) return;
  pin.addEventListener('input', () => syncWinnerOptions(pin.value, sel, sel.value));
  syncWinnerOptions(pin.value, sel, sel.value);
}

function _dismissModal(m) {
  m.hidden = true;
  if (_modalLastFocus && _modalLastFocus.focus) _modalLastFocus.focus();
  _modalLastFocus = null;
}

// Close modal when clicking backdrop
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-backdrop')) _dismissModal(e.target);
});

// Close modal on Escape; trap Tab focus inside the open modal so keyboard
// users can't tab out into the (still-present) page content behind it.
const FOCUSABLE_SEL = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), ' +
  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop:not([hidden])').forEach(_dismissModal);
    return;
  }
  if (e.key !== 'Tab') return;
  const backdrop = document.querySelector('.modal-backdrop:not([hidden])');
  const dlg = backdrop && backdrop.querySelector('.modal');
  if (!dlg) return;
  const focusables = Array.from(dlg.querySelectorAll(FOCUSABLE_SEL)).filter(el => el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0], last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  } else if (!dlg.contains(document.activeElement)) {
    // Focus somehow escaped the dialog (or landed on the dialog wrapper) —
    // pull it back in rather than letting Tab continue into page content.
    e.preventDefault(); first.focus();
  }
});

// ── BGG game search ────────────────────────────────────────────────────────

// Renders a list of BGG search results as keyboard-and-screen-reader-accessible
// "buttons" (role="button" + tabindex + Enter/Space activation), shared by the
// Add Game modal and the Log Play "search BGG" flow.
function renderSearchResults(container, items, onSelect, extraHint) {
  container.innerHTML = '';
  items.forEach(g => {
    const div = document.createElement('div');
    div.className = 'search-result-item';
    div.setAttribute('role', 'button');
    div.setAttribute('tabindex', '0');
    div.setAttribute('aria-label', g.name + (g.year ? ` (${g.year})` : ''));
    div.appendChild(document.createTextNode(g.name));
    if (g.year) {
      const yr = document.createElement('span');
      yr.className = 'search-result-year';
      yr.textContent = ` (${g.year})`;
      div.appendChild(yr);
    }
    if (extraHint) {
      const hint = document.createElement('small');
      hint.className = 'muted';
      hint.textContent = ' ' + extraHint;
      div.appendChild(hint);
    }
    const activate = () => onSelect(g);
    div.addEventListener('click', activate);
    div.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
    });
    container.appendChild(div);
  });
}

async function bggSearch() {
  const input   = document.getElementById('bgg-search-input');
  const results = document.getElementById('bgg-search-results');
  const q = input.value.trim();
  if (!q) return;

  results.innerHTML = '<p class="muted" style="padding:8px">Searching…</p>';
  document.getElementById('add-game-form').hidden = true;

  try {
    const res  = await fetch('/api/search?q=' + encodeURIComponent(q));
    const data = await res.json();

    if (data.error) {
      results.innerHTML = `<p class="muted" style="padding:8px;color:#b71c1c">${data.error}</p>`;
      return;
    }
    if (!data.length) {
      results.innerHTML = '<p class="muted" style="padding:8px">No results found.</p>';
      return;
    }

    renderSearchResults(results, data, g => bggSelectGame(g.id, g.name));
  } catch(e) {
    results.innerHTML = `<p class="muted" style="padding:8px;color:#b71c1c">Search failed: ${e}</p>`;
  }
}

async function bggSelectGame(bggId, name) {
  const results = document.getElementById('bgg-search-results');
  const form    = document.getElementById('add-game-form');
  const preview = document.getElementById('add-game-preview');

  results.innerHTML = '<p class="muted" style="padding:8px">Loading details…</p>';

  try {
    const res  = await fetch('/api/game/' + bggId);
    const data = await res.json();

    if (data.error) {
      results.innerHTML = `<p style="padding:8px;color:#b71c1c">${data.error}</p>`;
      return;
    }

    results.innerHTML = '';
    document.getElementById('add-bgg-id').value = bggId;

    const parts = [];
    if (data.year)        parts.push(data.year);
    if (data.min_players) parts.push(`${data.min_players}–${data.max_players} players`);
    if (data.playing_time) parts.push(`${data.playing_time} min`);
    if (data.weight)      parts.push(`Complexity ${data.weight.toFixed(1)}/5`);

    preview.innerHTML = `
      <h4>${data.name}${data.is_expansion ? ' <small style="color:#7b1fa2">(Expansion)</small>' : ''}</h4>
      <p>${parts.join(' · ')}</p>
      ${data.description ? `<p style="margin-top:6px">${data.description}…</p>` : ''}
    `;
    form.hidden = false;
  } catch(e) {
    results.innerHTML = `<p style="padding:8px;color:#b71c1c">Failed: ${e}</p>`;
  }
}

// Allow pressing Enter in BGG search input
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('bgg-search-input');
  if (input) {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); bggSearch(); }
    });
  }
});

// ── Sync status polling ────────────────────────────────────────────────────
function pollSyncStatus() {
  fetch('/api/sync_status')
    .then(r => r.json())
    .then(s => {
      const badge = document.querySelector('.sync-badge');
      if (badge) {
        badge.textContent = s.running ? '⟳ ' + s.message : s.message;
      }
      if (s.running) setTimeout(pollSyncStatus, 2000);
    })
    .catch(() => {});
}

// Start polling if a sync is shown as running
document.addEventListener('DOMContentLoaded', () => {
  if (document.querySelector('.sync-badge.spinning')) {
    setTimeout(pollSyncStatus, 2000);
  }
});

// ── Auto-dismiss flash messages ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .5s'; }, 3500);
    setTimeout(() => el.remove(), 4000);
  });
});

// ── Colour theme picker ─────────────────────────────────────────────────────
function applyTheme(name) {
  const t = (window.BGL_THEMES || {})[name];
  if (!t) return;
  window.bglSetThemeVars(t);
  try { localStorage.setItem('bgl_theme', name); } catch (e) {}
  document.querySelectorAll('.theme-swatch').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === name);
  });
}

// ── Sortable data tables — click a <th> to sort by that column ─────────────
// A <td> can set data-sort="raw value" to sort by something other than its
// displayed text (e.g. a number without a unit suffix). Add class="no-sort"
// to a <th> to exclude it (e.g. an actions column).
function sortTable(table, colIndex) {
  const tbody = table.tBodies[0];
  if (!tbody) return;
  const rows = Array.from(tbody.rows);
  const state = table._sortState || {};
  const reverse = state.col === colIndex ? !state.rev : false;
  table._sortState = { col: colIndex, rev: reverse };

  const cellVal = row => {
    const cell = row.cells[colIndex];
    return ((cell && (cell.dataset.sort ?? cell.textContent)) || '').trim();
  };
  rows.sort((a, b) => {
    const av = cellVal(a), bv = cellVal(b);
    const an = parseFloat(av), bn = parseFloat(bv);
    const bothNumeric = av !== '' && bv !== '' && /^-?[\d.]+$/.test(av) && /^-?[\d.]+$/.test(bv);
    const cmp = bothNumeric ? (an - bn) : av.toLowerCase().localeCompare(bv.toLowerCase());
    return reverse ? -cmp : cmp;
  });
  rows.forEach(r => tbody.appendChild(r));

  table.querySelectorAll('th[data-sort-idx]').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (parseInt(th.dataset.sortIdx, 10) === colIndex) {
      th.classList.add(reverse ? 'sort-desc' : 'sort-asc');
    }
  });
}

function makeSortableTable(table) {
  const headRow = table.tHead && table.tHead.rows[0];
  if (!headRow) return;
  Array.from(headRow.cells).forEach((th, idx) => {
    if (th.classList.contains('no-sort') || !th.textContent.trim()) return;
    th.dataset.sortIdx = idx;
    th.classList.add('sortable-col');
    th.tabIndex = 0;
    th.setAttribute('role', 'button');
    th.setAttribute('aria-label', `Sort by ${th.textContent.trim()}`);
    th.addEventListener('click', () => sortTable(table, idx));
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortTable(table, idx); }
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('table.sortable').forEach(makeSortableTable);
});

// ── Member list sort (card grid, not a <table>) ─────────────────────────────
function sortMemberList(by) {
  const list = document.getElementById('member-list');
  if (!list) return;
  const cards = Array.from(list.children);
  cards.sort((a, b) => {
    if (by === 'since') return (a.dataset.since || '').localeCompare(b.dataset.since || '');
    if (by === 'out')   return (parseInt(b.dataset.out, 10) || 0) - (parseInt(a.dataset.out, 10) || 0);
    // 'name' sorts by last name, then first — matches the server's default order.
    const aKey = `${(a.dataset.last || '').toLowerCase()} ${(a.dataset.first || '').toLowerCase()}`;
    const bKey = `${(b.dataset.last || '').toLowerCase()} ${(b.dataset.first || '').toLowerCase()}`;
    return aKey.localeCompare(bKey);
  });
  cards.forEach(c => list.appendChild(c));
}

document.addEventListener('DOMContentLoaded', () => {
  const box = document.getElementById('theme-swatches');
  if (!box || !window.BGL_THEMES) return;
  const current = localStorage.getItem('bgl_theme') || 'Classic Navy';
  Object.keys(window.BGL_THEMES).forEach(name => {
    const color = window.BGL_THEMES[name][0];
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'theme-swatch' + (name === current ? ' active' : '');
    b.dataset.theme = name;
    b.innerHTML = `<span class="theme-dot" style="background:${color}"></span>${name}`;
    b.onclick = () => { applyTheme(name); closeModal('modal-theme'); };
    box.appendChild(b);
  });
});
