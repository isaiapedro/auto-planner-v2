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
      event_id      TEXT,
      event_title   TEXT,
      synced_at     TEXT
    );

    CREATE TABLE IF NOT EXISTS sync_queue (
      memo_id      TEXT PRIMARY KEY REFERENCES memos(id),
      retry_count  INTEGER NOT NULL DEFAULT 0,
      created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_events_scheduled ON events (scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_events_status    ON events (status);

    CREATE TABLE IF NOT EXISTS event_notifications (
      event_id        TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
      notification_id TEXT NOT NULL,
      scheduled_at    TEXT NOT NULL
    );
  `);

  // Existing devices created the original three-column table. These additive
  // migrations keep their unsent recordings and add enough context to finish
  // event linking when connectivity returns.
  const columns = await db.getAllAsync<{ name: string }>("PRAGMA table_info(memos)");
  if (!columns.some((column) => column.name === "event_id")) {
    await db.execAsync("ALTER TABLE memos ADD COLUMN event_id TEXT");
  }
  if (!columns.some((column) => column.name === "event_title")) {
    await db.execAsync("ALTER TABLE memos ADD COLUMN event_title TEXT");
  }
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

export async function getEventsForToday(db: SQLite.SQLiteDatabase) {
  return db.getAllAsync<{
    id: string;
    title: string;
    scheduled_at: string;
    status: "pending" | "confirmed" | "skipped";
    memo_id: string | null;
  }>(
    `SELECT id, title, scheduled_at, status, memo_id FROM events
     WHERE date(scheduled_at, 'localtime') = date('now', 'localtime')
     ORDER BY scheduled_at ASC`
  );
}

export async function saveMemoLocal(
  db: SQLite.SQLiteDatabase,
  id: string,
  audioPath: string,
  eventId?: string,
  eventTitle?: string
) {
  await db.withTransactionAsync(async () => {
    await db.runAsync(
      `INSERT OR IGNORE INTO memos (id, audio_path, event_id, event_title) VALUES (?, ?, ?, ?)`,
      [id, audioPath, eventId ?? null, eventTitle ?? null]
    );
    await db.runAsync(`INSERT OR IGNORE INTO sync_queue (memo_id) VALUES (?)`, [id]);
  });
}

export async function markMemoSynced(db: SQLite.SQLiteDatabase, id: string) {
  await db.runAsync(
    `UPDATE memos SET synced_at = datetime('now') WHERE id = ?`,
    [id]
  );
  await db.runAsync(`DELETE FROM sync_queue WHERE memo_id = ?`, [id]);
}

export async function getPendingSyncQueue(db: SQLite.SQLiteDatabase) {
  return db.getAllAsync<{ memo_id: string; audio_path: string; event_id: string | null; event_title: string | null; retry_count: number }>(
    `SELECT sync_queue.memo_id, memos.audio_path, memos.event_id, memos.event_title, sync_queue.retry_count FROM sync_queue
     JOIN memos ON memos.id = sync_queue.memo_id
     WHERE retry_count < 3
     ORDER BY created_at ASC`
  );
}

export async function recordMemoRetry(db: SQLite.SQLiteDatabase, id: string) {
  await db.runAsync(`UPDATE sync_queue SET retry_count = retry_count + 1 WHERE memo_id = ?`, [id]);
}
