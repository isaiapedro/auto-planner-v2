import React, { useEffect } from "react";
import { AppState } from "react-native";

import { confirmEvent, uploadMemo } from "./src/api/client";
import { getPendingSyncQueue, markMemoSynced, openDb, recordMemoRetry, runMigrations } from "./src/db/schema";
import RootNavigator from "./src/navigation/RootNavigator";
import { requestPermissions } from "./src/notifications";

export default function App() {
  useEffect(() => {
    let draining = false;
    const drainMemoQueue = async () => {
      if (draining) return;
      draining = true;
      try {
        const db = await openDb();
        await runMigrations(db);
        const pending = await getPendingSyncQueue(db);
        for (const memo of pending) {
          try {
            const result = await uploadMemo(memo.audio_path, memo.event_title ?? undefined, memo.memo_id);
            if (memo.event_id) await confirmEvent(memo.event_id, true, result.job_id);
            await markMemoSynced(db, result.job_id);
          } catch {
            await recordMemoRetry(db, memo.memo_id);
          }
        }
      } finally {
        draining = false;
      }
    };

    // Retry both on launch and when the user returns after restoring Wi-Fi.
    drainMemoQueue().catch(console.error);
    const appStateSubscription = AppState.addEventListener("change", (state) => {
      if (state === "active") drainMemoQueue().catch(console.error);
    });
    requestPermissions().catch(console.error);
    return () => appStateSubscription.remove();
  }, []);

  return <RootNavigator />;
}
