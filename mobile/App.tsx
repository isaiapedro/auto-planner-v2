import React, { useEffect } from "react";

import { openDb, runMigrations } from "./src/db/schema";
import RootNavigator from "./src/navigation/RootNavigator";
import { requestPermissions, scheduleReviewReminders } from "./src/notifications";

export default function App() {
  useEffect(() => {
    // Initialize local SQLite DB + request notification permissions on first launch
    openDb().then(runMigrations).catch(console.error);
    requestPermissions()
      .then((granted) => {
        if (granted) return scheduleReviewReminders();
      })
      .catch(console.error);
  }, []);

  return <RootNavigator />;
}
