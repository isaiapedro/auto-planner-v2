import * as SQLite from "expo-sqlite";

const DB_NAME = "pios.db";

export async function openDb() {
  return SQLite.openDatabaseAsync(DB_NAME);
}

export async function runMigrations(db: SQLite.SQLiteDatabase) {
  await db.execAsync(`
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS events (
      id           TEXT PRIMARY KEY,
      title        TEXT NOT NULL,
      scheduled_at TEXT NOT NULL,
      status       TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','confirmed','skipped')),
      memo_id      TEXT,
      synced_at    TEXT
    );

    CREATE TABLE IF NOT EXISTS memos (
      id            TEXT PRIMARY KEY,
      audio_path    TEXT NOT NULL,
      transcript    TEXT,
      features_json TEXT,
      synced_at     TEXT
    );

    CREATE TABLE IF NOT EXISTS sync_queue (
      memo_id      TEXT PRIMARY KEY REFERENCES memos(id),
      retry_count  INTEGER NOT NULL DEFAULT 0,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_events_scheduled ON events (scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_events_status    ON events (status);
  `);
}

// ── typed repository helpers ──────────────────────────────────────────────────

export async function upsertEvents(
  db: SQLite.SQLiteDatabase,
  events: Array<{
    id: string;
    title: string;
    scheduled_at: string;
    status: string;
    memo_id: string | null;
  }>
) {
  await db.withTransactionAsync(async () => {
    for (const e of events) {
      await db.runAsync(
        `INSERT INTO events (id, title, scheduled_at, status, memo_id, synced_at)
         VALUES (?, ?, ?, ?, ?, datetime('now'))
         ON CONFLICT(id) DO UPDATE SET
           status = excluded.status,
           memo_id = excluded.memo_id,
           synced_at = excluded.synced_at`,
        [e.id, e.title, e.scheduled_at, e.status, e.memo_id ?? null]
      );
    }
  });
}

export async function getPendingEvents(db: SQLite.SQLiteDatabase) {
  return db.getAllAsync<{ id: string; title: string; scheduled_at: string }>(
    `SELECT id, title, scheduled_at FROM events
     WHERE status = 'pending' AND scheduled_at >= datetime('now')
     ORDER BY scheduled_at ASC`
  );
}

export async function saveMemoLocal(
  db: SQLite.SQLiteDatabase,
  id: string,
  audioPath: string
) {
  await db.runAsync(
    `INSERT OR IGNORE INTO memos (id, audio_path) VALUES (?, ?)`,
    [id, audioPath]
  );
  await db.runAsync(
    `INSERT OR IGNORE INTO sync_queue (memo_id) VALUES (?)`,
    [id]
  );
}

export async function markMemoSynced(db: SQLite.SQLiteDatabase, id: string) {
  await db.runAsync(
    `UPDATE memos SET synced_at = datetime('now') WHERE id = ?`,
    [id]
  );
  await db.runAsync(`DELETE FROM sync_queue WHERE memo_id = ?`, [id]);
}

export async function getPendingSyncQueue(db: SQLite.SQLiteDatabase) {
  return db.getAllAsync<{ memo_id: string; retry_count: number }>(
    `SELECT memo_id, retry_count FROM sync_queue
     WHERE retry_count < 3
     ORDER BY created_at ASC`
  );
}
