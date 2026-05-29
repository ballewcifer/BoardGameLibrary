/**
 * BGG XML API v2 client — mirrors bgg.py
 * All HTTP requests use a browser-like User-Agent (BGG blocks others).
 */

const BASE = 'https://boardgamegeek.com/xmlapi2';
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15';

async function fetchXml(url: string, attempts = 8): Promise<Document> {
  for (let i = 0; i < attempts; i++) {
    const res = await fetch(url, { headers: { 'User-Agent': UA } });
    if (res.status === 200) {
      const text = await res.text();
      return new DOMParser().parseFromString(text, 'text/xml');
    }
    if (res.status === 202) {
      await new Promise(r => setTimeout(r, 2000));
      continue;
    }
    throw new Error(`BGG HTTP ${res.status}`);
  }
  throw new Error('BGG kept returning 202');
}

function txt(el: Element | null, attr?: string): string {
  if (!el) return '';
  return attr ? (el.getAttribute(attr) ?? '') : (el.textContent ?? '');
}

function num(el: Element | null, attr = 'value'): number | undefined {
  const s = el?.getAttribute(attr);
  const n = s ? parseFloat(s) : NaN;
  return isNaN(n) ? undefined : n;
}

// ── Search ────────────────────────────────────────────────────────────────────

export interface SearchResult {
  bgg_id: number;
  name: string;
  year?: number;
}

export async function searchGames(query: string): Promise<SearchResult[]> {
  const params = new URLSearchParams({ query, type: 'boardgame,boardgameexpansion' });
  const doc = await fetchXml(`${BASE}/search?${params}`);
  const results: SearchResult[] = [];
  doc.querySelectorAll('item').forEach(item => {
    const bgg_id = parseInt(item.getAttribute('id') ?? '0', 10);
    if (!bgg_id) return;
    let name = '';
    item.querySelectorAll('name').forEach(n => {
      if (n.getAttribute('type') === 'primary') name = n.getAttribute('value') ?? '';
    });
    if (!name) return;
    const yearEl = item.querySelector('yearpublished');
    const year = yearEl ? parseInt(yearEl.getAttribute('value') ?? '', 10) : undefined;
    results.push({ bgg_id, name, year: isNaN(year as number) ? undefined : year });
  });
  return results.sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
}

// ── Game details ──────────────────────────────────────────────────────────────

export interface GameDetails {
  bgg_id: number;
  name: string;
  year?: number;
  image_url?: string;
  thumbnail_url?: string;
  min_players?: number;
  max_players?: number;
  min_playtime?: number;
  max_playtime?: number;
  playing_time?: number;
  min_age?: number;
  weight?: number;
  avg_rating?: number;
  description?: string;
  categories: string[];
  mechanics: string[];
  designers: string[];
  publishers: string[];
  is_expansion: boolean;
}

export async function fetchGameDetails(bggId: number): Promise<GameDetails | null> {
  const doc = await fetchXml(`${BASE}/thing?id=${bggId}&stats=1`);
  const item = doc.querySelector('item');
  if (!item) return null;

  const type = item.getAttribute('type') ?? '';
  const is_expansion = type === 'boardgameexpansion';

  let name = '';
  item.querySelectorAll('name').forEach(n => {
    if (n.getAttribute('type') === 'primary') name = n.getAttribute('value') ?? '';
  });

  const listValues = (linkType: string) =>
    Array.from(item.querySelectorAll(`link[type="${linkType}"]`))
      .map(l => l.getAttribute('value') ?? '').filter(Boolean);

  const stats = item.querySelector('statistics ratings');

  return {
    bgg_id:       bggId,
    name,
    year:         num(item.querySelector('yearpublished')),
    image_url:    item.querySelector('image')?.textContent?.trim(),
    thumbnail_url:item.querySelector('thumbnail')?.textContent?.trim(),
    min_players:  num(item.querySelector('minplayers')),
    max_players:  num(item.querySelector('maxplayers')),
    min_playtime: num(item.querySelector('minplaytime')),
    max_playtime: num(item.querySelector('maxplaytime')),
    playing_time: num(item.querySelector('playingtime')),
    min_age:      num(item.querySelector('minage')),
    weight:       num(stats?.querySelector('averageweight')),
    avg_rating:   num(stats?.querySelector('average')),
    description:  item.querySelector('description')?.textContent?.trim().replace(/&#10;/g, '\n'),
    categories:   listValues('boardgamecategory'),
    mechanics:    listValues('boardgamemechanic'),
    designers:    listValues('boardgamedesigner'),
    publishers:   listValues('boardgamepublisher'),
    is_expansion,
  };
}

// ── Collection sync ───────────────────────────────────────────────────────────

export async function fetchCollection(username: string): Promise<GameDetails[]> {
  const doc = await fetchXml(
    `${BASE}/collection?username=${encodeURIComponent(username)}&own=1&stats=1`,
    12
  );
  const items = doc.querySelectorAll('item');
  const ids: number[] = [];
  items.forEach(item => {
    const id = parseInt(item.getAttribute('objectid') ?? '0', 10);
    if (id) ids.push(id);
  });

  // Fetch details in batches of 20
  const results: GameDetails[] = [];
  for (let i = 0; i < ids.length; i += 20) {
    const batch = ids.slice(i, i + 20).join(',');
    const detailDoc = await fetchXml(`${BASE}/thing?id=${batch}&stats=1`);
    detailDoc.querySelectorAll('item').forEach(item => {
      const bggId = parseInt(item.getAttribute('id') ?? '0', 10);
      if (!bggId) return;
      let name = '';
      item.querySelectorAll('name').forEach(n => {
        if (n.getAttribute('type') === 'primary') name = n.getAttribute('value') ?? '';
      });
      if (!name) return;
      const type = item.getAttribute('type') ?? '';
      const stats = item.querySelector('statistics ratings');
      const listValues = (linkType: string) =>
        Array.from(item.querySelectorAll(`link[type="${linkType}"]`))
          .map(l => l.getAttribute('value') ?? '').filter(Boolean);
      results.push({
        bgg_id: bggId, name,
        year:         num(item.querySelector('yearpublished')),
        image_url:    item.querySelector('image')?.textContent?.trim(),
        thumbnail_url:item.querySelector('thumbnail')?.textContent?.trim(),
        min_players:  num(item.querySelector('minplayers')),
        max_players:  num(item.querySelector('maxplayers')),
        playing_time: num(item.querySelector('playingtime')),
        weight:       num(stats?.querySelector('averageweight')),
        avg_rating:   num(stats?.querySelector('average')),
        categories:   listValues('boardgamecategory'),
        mechanics:    listValues('boardgamemechanic'),
        designers:    listValues('boardgamedesigner'),
        publishers:   listValues('boardgamepublisher'),
        is_expansion: type === 'boardgameexpansion',
      });
    });
  }
  return results;
}
