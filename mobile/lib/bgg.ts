/**
 * BGG XML API v2 client — React Native compatible.
 * Uses fast-xml-parser instead of DOMParser (which doesn't exist in RN).
 */
import { XMLParser } from 'fast-xml-parser';

const BASE = 'https://boardgamegeek.com/xmlapi2';
const UA   = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36';

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '_',
  parseAttributeValue: true,
  parseTagValue: true,
  // Always treat these as arrays even if only one element
  isArray: (name) => ['item', 'link', 'name', 'rank'].includes(name),
});

// ── HTTP ──────────────────────────────────────────────────────────────────────

async function fetchXml(url: string, attempts = 10, token?: string): Promise<any> {
  for (let i = 0; i < attempts; i++) {
    const headers: Record<string, string> = { 'User-Agent': UA };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(url, { headers, credentials: 'include' });
    if (res.status === 200) {
      const text = await res.text();
      return parser.parse(text);
    }
    if (res.status === 202) {
      await new Promise(r => setTimeout(r, 2500));
      continue;
    }
    throw new Error(`BGG HTTP ${res.status}`);
  }
  throw new Error('BGG kept returning 202 — try again in a moment.');
}

// ── BGG login ─────────────────────────────────────────────────────────────────

export async function loginBgg(username: string, password: string): Promise<void> {
  const res = await fetch('https://boardgamegeek.com/login/api/v1', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': UA },
    body: `credentials[username]=${encodeURIComponent(username)}&credentials[password]=${encodeURIComponent(password)}`,
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`BGG login failed (HTTP ${res.status}). Check username/password.`);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function strVal(obj: any): string | undefined {
  if (obj == null) return undefined;
  if (typeof obj === 'string') return obj;
  if (typeof obj === 'number') return String(obj);
  return obj._value != null ? String(obj._value) : undefined;
}

function numVal(obj: any): number | undefined {
  if (obj == null) return undefined;
  const v = typeof obj === 'number' ? obj : obj._value;
  const n = parseFloat(String(v));
  return isNaN(n) ? undefined : n;
}

function linkValues(items: any[], type: string): string[] {
  return (items || [])
    .filter((l: any) => l._type === type)
    .map((l: any) => String(l._value ?? ''))
    .filter(Boolean);
}

function primaryName(names: any[]): string {
  if (!names?.length) return '';
  const primary = names.find((n: any) => n._type === 'primary');
  const n = primary ?? names[0];
  return String(n._value ?? n['#text'] ?? '');
}

function ensureHttps(url?: string): string | undefined {
  if (!url) return undefined;
  return url.startsWith('//') ? `https:${url}` : url;
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
  const items: any[] = doc?.items?.item ?? [];
  const results: SearchResult[] = items.map((item: any) => ({
    bgg_id: item._id,
    name:   primaryName(item.name),
    year:   numVal(item.yearpublished),
  })).filter(r => r.bgg_id && r.name);
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

export async function fetchGameDetails(bggId: number, token?: string): Promise<GameDetails | null> {
  const doc = await fetchXml(`${BASE}/thing?id=${bggId}&stats=1`, 10, token);
  const items: any[] = doc?.items?.item ?? [];
  const item = items[0];
  if (!item) return null;

  const links: any[] = item.link ?? [];
  const ratings = item.statistics?.ratings ?? item.stats?.rating ?? {};

  return {
    bgg_id:        item._id,
    name:          primaryName(item.name),
    year:          numVal(item.yearpublished),
    image_url:     ensureHttps(typeof item.image === 'string' ? item.image : item.image?.['#text']),
    thumbnail_url: ensureHttps(typeof item.thumbnail === 'string' ? item.thumbnail : item.thumbnail?.['#text']),
    min_players:   numVal(item.minplayers),
    max_players:   numVal(item.maxplayers),
    min_playtime:  numVal(item.minplaytime),
    max_playtime:  numVal(item.maxplaytime),
    playing_time:  numVal(item.playingtime),
    min_age:       numVal(item.minage),
    weight:        numVal(ratings.averageweight),
    avg_rating:    numVal(ratings.average),
    description:   typeof item.description === 'string' ? item.description.slice(0, 2000) : undefined,
    categories:    linkValues(links, 'boardgamecategory'),
    mechanics:     linkValues(links, 'boardgamemechanic'),
    designers:     linkValues(links, 'boardgamedesigner'),
    publishers:    linkValues(links, 'boardgamepublisher'),
    is_expansion:  item._type === 'boardgameexpansion',
  };
}

// ── Collection sync ───────────────────────────────────────────────────────────

export async function fetchCollection(username: string, token?: string): Promise<GameDetails[]> {
  const doc = await fetchXml(
    `${BASE}/collection?username=${encodeURIComponent(username)}&own=1&stats=1`,
    14,
    token,
  );

  const items: any[] = doc?.items?.item ?? [];
  if (!items.length) return [];

  // Fetch full details in batches of 20
  const ids: number[] = items
    .map((item: any) => Number(item._objectid))
    .filter(Boolean);

  const results: GameDetails[] = [];
  for (let i = 0; i < ids.length; i += 20) {
    const batch = ids.slice(i, i + 20).join(',');
    const batchDoc = await fetchXml(`${BASE}/thing?id=${batch}&stats=1`, 10, token);
    const batchItems: any[] = batchDoc?.items?.item ?? [];
    for (const item of batchItems) {
      const links: any[] = item.link ?? [];
      const ratings = item.statistics?.ratings ?? item.stats?.rating ?? {};
      results.push({
        bgg_id:        item._id,
        name:          primaryName(item.name),
        year:          numVal(item.yearpublished),
        image_url:     ensureHttps(typeof item.image === 'string' ? item.image : item.image?.['#text']),
        thumbnail_url: ensureHttps(typeof item.thumbnail === 'string' ? item.thumbnail : item.thumbnail?.['#text']),
        min_players:   numVal(item.minplayers),
        max_players:   numVal(item.maxplayers),
        min_playtime:  numVal(item.minplaytime),
        max_playtime:  numVal(item.maxplaytime),
        playing_time:  numVal(item.playingtime),
        min_age:       numVal(item.minage),
        weight:        numVal(ratings.averageweight),
        avg_rating:    numVal(ratings.average),
        description:   typeof item.description === 'string' ? item.description.slice(0, 2000) : undefined,
        categories:    linkValues(links, 'boardgamecategory'),
        mechanics:     linkValues(links, 'boardgamemechanic'),
        designers:     linkValues(links, 'boardgamedesigner'),
        publishers:    linkValues(links, 'boardgamepublisher'),
        is_expansion:  item._type === 'boardgameexpansion',
      });
    }
  }
  return results;
}
