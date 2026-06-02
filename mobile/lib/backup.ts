/**
 * Export / import all user data as a JSON file.
 *
 * What is exported:
 *   - Members
 *   - Plays (full detail)
 *   - Loan history (full detail)
 *   - Game customisations: tags, favorites, insert flag, my_comment, my_rating, manual_fields
 *
 * What is NOT exported (can be re-synced from BGG):
 *   - Full game catalogue (name, description, mechanics, etc.)
 */

import * as FileSystem from 'expo-file-system';
import * as Sharing     from 'expo-sharing';
import * as DocumentPicker from 'expo-document-picker';
import { getDb, nowIso } from './db';

const BACKUP_VERSION = 1;

// ── Export ────────────────────────────────────────────────────────────────────

export async function exportBackup(): Promise<void> {
  const db = getDb();

  const members = db.getAllSync('SELECT * FROM users ORDER BY id');

  const plays = db.getAllSync(
    'SELECT plays.*, games.name AS game_name FROM plays ' +
    'LEFT JOIN games ON games.bgg_id = plays.game_id ' +
    'ORDER BY plays.played_at DESC'
  );

  const loans = db.getAllSync(
    'SELECT loans.*, games.name AS game_name, ' +
    '       users.first_name, users.last_name ' +
    'FROM loans ' +
    'LEFT JOIN games ON games.bgg_id = loans.game_id ' +
    'LEFT JOIN users ON users.id     = loans.user_id ' +
    'ORDER BY loans.checked_out_at DESC'
  );

  const customisations = db.getAllSync(
    'SELECT bgg_id, name, tags, is_favorite, has_insert, ' +
    '       my_comment, my_rating, manual_fields ' +
    'FROM games ' +
    'WHERE tags IS NOT NULL OR is_favorite = 1 OR has_insert = 1 ' +
    '   OR my_comment IS NOT NULL OR my_rating IS NOT NULL'
  );

  const payload = {
    version:     BACKUP_VERSION,
    exported_at: nowIso(),
    members,
    plays,
    loans,
    customisations,
  };

  const json     = JSON.stringify(payload, null, 2);
  const filename = `bgl-backup-${nowIso().slice(0, 10)}.json`;
  const path     = FileSystem.cacheDirectory + filename;

  await FileSystem.writeAsStringAsync(path, json, { encoding: FileSystem.EncodingType.UTF8 });

  const canShare = await Sharing.isAvailableAsync();
  if (!canShare) throw new Error('Sharing is not available on this device.');
  await Sharing.shareAsync(path, { mimeType: 'application/json', dialogTitle: 'Save BGL Backup' });
}

// ── Import ────────────────────────────────────────────────────────────────────

export interface ImportResult {
  members:       number;
  plays:         number;
  loans:         number;
  customisations:number;
  skipped:       number;
}

export async function importBackup(): Promise<ImportResult> {
  const result = await DocumentPicker.getDocumentAsync({
    type: 'application/json',
    copyToCacheDirectory: true,
  });

  if (result.canceled) throw new Error('Cancelled');

  const uri  = result.assets[0].uri;
  const json = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.UTF8 });
  const data = JSON.parse(json);

  if (!data.version || !data.members) {
    throw new Error('Invalid backup file — does not look like a BGL backup.');
  }

  const db = getDb();
  const counts: ImportResult = { members: 0, plays: 0, loans: 0, customisations: 0, skipped: 0 };

  // ── Members ──────────────────────────────────────────────────────────────
  // Map old IDs → new IDs so loans/plays can reference correct users
  const userIdMap: Record<number, number> = {};

  for (const m of (data.members ?? [])) {
    // Skip if exact name already exists
    const existing = db.getFirstSync<{id:number}>(
      'SELECT id FROM users WHERE first_name = ? AND last_name = ?',
      [m.first_name, m.last_name]
    );
    if (existing) {
      userIdMap[m.id] = existing.id;
      counts.skipped++;
    } else {
      const r = db.runSync(
        'INSERT INTO users (first_name, last_name, created_at) VALUES (?, ?, ?)',
        [m.first_name, m.last_name, m.created_at ?? nowIso()]
      );
      userIdMap[m.id] = r.lastInsertRowId;
      counts.members++;
    }
  }

  // ── Plays ────────────────────────────────────────────────────────────────
  for (const p of (data.plays ?? [])) {
    const exists = db.getFirstSync(
      'SELECT id FROM plays WHERE game_id = ? AND played_at = ?',
      [p.game_id, p.played_at]
    );
    if (exists) { counts.skipped++; continue; }
    // Only import if the game exists in local DB
    const gameExists = db.getFirstSync('SELECT bgg_id FROM games WHERE bgg_id = ?', [p.game_id]);
    if (!gameExists) { counts.skipped++; continue; }
    db.runSync(
      'INSERT INTO plays (game_id, played_at, player_names, winner, notes, duration_minutes, scores) ' +
      'VALUES (?, ?, ?, ?, ?, ?, ?)',
      [p.game_id, p.played_at, p.player_names ?? null, p.winner ?? null,
       p.notes ?? null, p.duration_minutes ?? null, p.scores ?? null]
    );
    counts.plays++;
  }

  // ── Loans ────────────────────────────────────────────────────────────────
  for (const l of (data.loans ?? [])) {
    const mappedUserId = userIdMap[l.user_id] ?? l.user_id;
    const exists = db.getFirstSync(
      'SELECT id FROM loans WHERE game_id = ? AND checked_out_at = ?',
      [l.game_id, l.checked_out_at]
    );
    if (exists) { counts.skipped++; continue; }
    const gameExists = db.getFirstSync('SELECT bgg_id FROM games WHERE bgg_id = ?', [l.game_id]);
    if (!gameExists) { counts.skipped++; continue; }
    db.runSync(
      'INSERT INTO loans (game_id, user_id, checked_out_at, returned_at, due_date, notes) ' +
      'VALUES (?, ?, ?, ?, ?, ?)',
      [l.game_id, mappedUserId, l.checked_out_at, l.returned_at ?? null,
       l.due_date ?? null, l.notes ?? null]
    );
    counts.loans++;
  }

  // ── Game customisations ───────────────────────────────────────────────────
  for (const c of (data.customisations ?? [])) {
    const gameExists = db.getFirstSync('SELECT bgg_id FROM games WHERE bgg_id = ?', [c.bgg_id]);
    if (!gameExists) { counts.skipped++; continue; }
    db.runSync(
      'UPDATE games SET tags = ?, is_favorite = ?, has_insert = ?, ' +
      '  my_comment = ?, my_rating = ?, manual_fields = ? ' +
      'WHERE bgg_id = ?',
      [c.tags ?? null, c.is_favorite ?? 0, c.has_insert ?? 0,
       c.my_comment ?? null, c.my_rating ?? null, c.manual_fields ?? null,
       c.bgg_id]
    );
    counts.customisations++;
  }

  return counts;
}
