import * as SQLite from 'expo-sqlite';
import type { Game, User, Loan, Play, Stats } from './types';

let _db: SQLite.SQLiteDatabase | null = null;

export function getDb(): SQLite.SQLiteDatabase {
  if (!_db) _db = SQLite.openDatabaseSync('library.db');
  return _db;
}

export function nowIso(): string {
  return new Date().toISOString().slice(0, 19).replace('T', 'T');
}

// ── Schema ────────────────────────────────────────────────────────────────────

export function fixProtocolRelativeUrls(): void {
  const db = getDb();
  db.runSync("UPDATE games SET thumbnail_url = 'https:' || thumbnail_url WHERE thumbnail_url LIKE '//%'");
  db.runSync("UPDATE games SET image_url     = 'https:' || image_url     WHERE image_url     LIKE '//%'");
}

export function initDb(): void {
  const db = getDb();
  db.execSync(`
    CREATE TABLE IF NOT EXISTS games (
      bgg_id        INTEGER PRIMARY KEY,
      name          TEXT NOT NULL,
      year          INTEGER,
      image_url     TEXT,
      thumbnail_url TEXT,
      image_path    TEXT,
      min_players   INTEGER,
      max_players   INTEGER,
      min_playtime  INTEGER,
      max_playtime  INTEGER,
      playing_time  INTEGER,
      min_age       INTEGER,
      weight        REAL,
      avg_rating    REAL,
      my_rating     REAL,
      description   TEXT,
      categories    TEXT,
      mechanics     TEXT,
      designers     TEXT,
      publishers    TEXT,
      best_players  TEXT,
      my_comment    TEXT,
      own           INTEGER DEFAULT 1,
      last_synced   TEXT,
      is_favorite   INTEGER DEFAULT 0,
      has_insert    INTEGER DEFAULT 0,
      is_expansion  INTEGER DEFAULT 0,
      tags          TEXT,
      manual_fields TEXT
    );
    CREATE TABLE IF NOT EXISTS users (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      first_name TEXT NOT NULL,
      last_name  TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS loans (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      game_id        INTEGER NOT NULL REFERENCES games(bgg_id) ON DELETE CASCADE,
      user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      checked_out_at TEXT NOT NULL,
      returned_at    TEXT,
      due_date       TEXT,
      notes          TEXT
    );
    CREATE TABLE IF NOT EXISTS plays (
      id               INTEGER PRIMARY KEY AUTOINCREMENT,
      game_id          INTEGER NOT NULL REFERENCES games(bgg_id) ON DELETE CASCADE,
      played_at        TEXT NOT NULL,
      player_names     TEXT,
      winner           TEXT,
      notes            TEXT,
      duration_minutes INTEGER,
      scores           TEXT
    );
    PRAGMA foreign_keys = ON;
  `);
}

// ── Games ─────────────────────────────────────────────────────────────────────

export function upsertGame(g: Partial<Game>): void {
  const db = getDb();
  db.runSync(
    `INSERT INTO games (bgg_id,name,year,image_url,thumbnail_url,min_players,max_players,
      min_playtime,max_playtime,playing_time,min_age,weight,avg_rating,my_rating,
      description,categories,mechanics,designers,publishers,best_players,my_comment,
      own,last_synced,is_expansion)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(bgg_id) DO UPDATE SET
       name=excluded.name, year=excluded.year, image_url=excluded.image_url,
       thumbnail_url=excluded.thumbnail_url, min_players=excluded.min_players,
       max_players=excluded.max_players, min_playtime=excluded.min_playtime,
       max_playtime=excluded.max_playtime, playing_time=excluded.playing_time,
       min_age=excluded.min_age, weight=excluded.weight, avg_rating=excluded.avg_rating,
       my_rating=excluded.my_rating, description=excluded.description,
       categories=excluded.categories, mechanics=excluded.mechanics,
       designers=excluded.designers, publishers=excluded.publishers,
       best_players=excluded.best_players, my_comment=excluded.my_comment,
       own=excluded.own, last_synced=excluded.last_synced, is_expansion=excluded.is_expansion`,
    [g.bgg_id,g.name,g.year??null,g.image_url??null,g.thumbnail_url??null,
     g.min_players??null,g.max_players??null,g.min_playtime??null,g.max_playtime??null,
     g.playing_time??null,g.min_age??null,g.weight??null,g.avg_rating??null,
     g.my_rating??null,g.description??null,g.categories??null,g.mechanics??null,
     g.designers??null,g.publishers??null,g.best_players??null,g.my_comment??null,
     g.own??1,nowIso(),g.is_expansion??0]
  );
}

export function listGames(search = ''): Game[] {
  const db = getDb();
  if (search) {
    return db.getAllSync<Game>(
      'SELECT * FROM games WHERE name LIKE ? ORDER BY name COLLATE NOCASE',
      [`%${search}%`]
    );
  }
  return db.getAllSync<Game>('SELECT * FROM games ORDER BY name COLLATE NOCASE');
}

export function getGame(bggId: number): Game | null {
  return getDb().getFirstSync<Game>('SELECT * FROM games WHERE bgg_id = ?', [bggId]);
}

export function deleteGame(bggId: number): void {
  getDb().runSync('DELETE FROM games WHERE bgg_id = ?', [bggId]);
}

export function setFavorite(bggId: number, value: boolean): void {
  getDb().runSync('UPDATE games SET is_favorite = ? WHERE bgg_id = ?', [value ? 1 : 0, bggId]);
}

export function setTags(bggId: number, tags: string): void {
  getDb().runSync('UPDATE games SET tags = ? WHERE bgg_id = ?', [tags || null, bggId]);
}

export function setMyComment(bggId: number, comment: string): void {
  getDb().runSync('UPDATE games SET my_comment = ? WHERE bgg_id = ?', [comment || null, bggId]);
}

// ── Users ─────────────────────────────────────────────────────────────────────

export function listUsers(): User[] {
  return getDb().getAllSync<User>(
    'SELECT * FROM users ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE'
  );
}

export function addUser(firstName: string, lastName: string): number {
  const result = getDb().runSync(
    'INSERT INTO users (first_name, last_name, created_at) VALUES (?,?,?)',
    [firstName.trim(), lastName.trim(), nowIso()]
  );
  return result.lastInsertRowId;
}

export function deleteUser(userId: number): void {
  getDb().runSync('DELETE FROM users WHERE id = ?', [userId]);
}

// ── Loans ─────────────────────────────────────────────────────────────────────

export function openLoanForGame(bggId: number): Loan | null {
  return getDb().getFirstSync<Loan>(
    `SELECT loans.*, users.first_name, users.last_name
     FROM loans JOIN users ON users.id = loans.user_id
     WHERE loans.game_id = ? AND loans.returned_at IS NULL`,
    [bggId]
  );
}

export function checkOut(bggId: number, userId: number, notes = '', dueDate?: string): void {
  if (openLoanForGame(bggId)) throw new Error('Game is already checked out.');
  getDb().runSync(
    'INSERT INTO loans (game_id, user_id, checked_out_at, due_date, notes) VALUES (?,?,?,?,?)',
    [bggId, userId, nowIso(), dueDate ?? null, notes]
  );
}

export function checkIn(bggId: number): void {
  const loan = openLoanForGame(bggId);
  if (!loan) throw new Error('Game is not currently checked out.');
  getDb().runSync('UPDATE loans SET returned_at = ? WHERE id = ?', [nowIso(), loan.id]);
}

export function loanHistory(gameId?: number, userId?: number): Loan[] {
  const where: string[] = [];
  const params: (number | null)[] = [];
  if (gameId != null) { where.push('loans.game_id = ?'); params.push(gameId); }
  if (userId != null) { where.push('loans.user_id = ?'); params.push(userId); }
  const whereSql = where.length ? 'WHERE ' + where.join(' AND ') : '';
  return getDb().getAllSync<Loan>(
    `SELECT loans.*, games.name AS game_name, users.first_name, users.last_name
     FROM loans
     JOIN games ON games.bgg_id = loans.game_id
     JOIN users ON users.id = loans.user_id
     ${whereSql}
     ORDER BY loans.checked_out_at DESC`,
    params
  );
}

export function currentlyCheckedOut(): Loan[] {
  return getDb().getAllSync<Loan>(
    `SELECT loans.id, loans.checked_out_at, loans.due_date,
            games.name AS game_name, games.bgg_id,
            users.first_name, users.last_name, users.id AS user_id
     FROM loans
     JOIN games ON games.bgg_id = loans.game_id
     JOIN users ON users.id     = loans.user_id
     WHERE loans.returned_at IS NULL
     ORDER BY loans.checked_out_at ASC`
  );
}

// ── Plays ─────────────────────────────────────────────────────────────────────

export function logPlay(
  gameId: number, playedAt: string, playerNames = '',
  winner = '', notes = '', durationMinutes?: number, scores?: string
): number {
  const result = getDb().runSync(
    `INSERT INTO plays (game_id, played_at, player_names, winner, notes, duration_minutes, scores)
     VALUES (?,?,?,?,?,?,?)`,
    [gameId, playedAt, playerNames.trim(), winner.trim(), notes.trim(),
     durationMinutes ?? null, scores ?? null]
  );
  return result.lastInsertRowId;
}

export function updatePlay(
  playId: number, gameId: number, playedAt: string,
  playerNames = '', winner = '', notes = '',
  durationMinutes?: number, scores?: string
): void {
  getDb().runSync(
    `UPDATE plays SET game_id=?, played_at=?, player_names=?, winner=?,
     notes=?, duration_minutes=?, scores=? WHERE id=?`,
    [gameId, playedAt, playerNames.trim(), winner.trim(), notes.trim(),
     durationMinutes ?? null, scores ?? null, playId]
  );
}

export function deletePlay(playId: number): void {
  getDb().runSync('DELETE FROM plays WHERE id = ?', [playId]);
}

export function listPlays(gameId?: number): Play[] {
  const where = gameId != null ? 'WHERE plays.game_id = ?' : '';
  const params = gameId != null ? [gameId] : [];
  return getDb().getAllSync<Play>(
    `SELECT plays.*, games.name AS game_name
     FROM plays JOIN games ON games.bgg_id = plays.game_id
     ${where} ORDER BY plays.played_at DESC`,
    params
  );
}

export function recentPlays(limit = 8): Play[] {
  return getDb().getAllSync<Play>(
    `SELECT plays.*, games.name AS game_name
     FROM plays JOIN games ON games.bgg_id = plays.game_id
     ORDER BY plays.played_at DESC LIMIT ?`,
    [limit]
  );
}

export function topGamesByPlays(limit = 5): { bgg_id: number; name: string; play_count: number }[] {
  return getDb().getAllSync(
    `SELECT games.bgg_id, games.name, COUNT(plays.id) AS play_count
     FROM plays JOIN games ON games.bgg_id = plays.game_id
     GROUP BY plays.game_id ORDER BY play_count DESC LIMIT ?`,
    [limit]
  );
}

export function topWinners(limit = 5): { winner: string; win_count: number }[] {
  const sql = limit > 0
    ? `SELECT winner, COUNT(*) AS win_count FROM plays
       WHERE winner IS NOT NULL AND winner != ''
       GROUP BY winner ORDER BY win_count DESC LIMIT ${limit}`
    : `SELECT winner, COUNT(*) AS win_count FROM plays
       WHERE winner IS NOT NULL AND winner != ''
       GROUP BY winner ORDER BY win_count DESC`;
  return getDb().getAllSync(sql);
}

// ── Stats ─────────────────────────────────────────────────────────────────────

export function statsSummary(): Stats {
  const db = getDb();
  return {
    total_games:   (db.getFirstSync<{n:number}>('SELECT COUNT(*) AS n FROM games')?.n ?? 0),
    total_plays:   (db.getFirstSync<{n:number}>('SELECT COUNT(*) AS n FROM plays')?.n ?? 0),
    total_members: (db.getFirstSync<{n:number}>('SELECT COUNT(*) AS n FROM users')?.n ?? 0),
    checked_out:   (db.getFirstSync<{n:number}>('SELECT COUNT(*) AS n FROM loans WHERE returned_at IS NULL')?.n ?? 0),
  };
}

export function playCounts(): Record<number, number> {
  const rows = getDb().getAllSync<{game_id:number;n:number}>(
    'SELECT game_id, COUNT(*) AS n FROM plays GROUP BY game_id'
  );
  return Object.fromEntries(rows.map(r => [r.game_id, r.n]));
}
