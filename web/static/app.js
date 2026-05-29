/* Board Game Library — web client JS */

// ── Modal helpers ──────────────────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.hidden = false; el.focus && el.focus(); }
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

// Close modal when clicking backdrop
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.hidden = true;
  }
});

// Close modal on Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop:not([hidden])').forEach(m => { m.hidden = true; });
  }
});

// ── BGG game search ────────────────────────────────────────────────────────
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

    results.innerHTML = data.map(g => `
      <div class="search-result-item" onclick="bggSelectGame(${g.id}, ${JSON.stringify(g.name).replace(/'/g,"&#39;")})">
        ${g.name}
        ${g.year ? `<span class="search-result-year">(${g.year})</span>` : ''}
      </div>
    `).join('');
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
