/**
 * Task #11 — Expo local push notifications (Pillar 1 — Capture).
 * Schedules a local notification at each event's scheduled_at.
 * Payload carries event_id for deep-link into the confirmation flow.
 * v1: local scheduling only — no remote push server.
 */
import * as Notifications from "expo-notifications";

import { openDb } from "../db/schema";
import type { AppEvent } from "../types";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function requestPermissions(): Promise<boolean> {
  const { status } = await Notifications.requestPermissionsAsync();
  return status === "granted";
}

/**
 * Reconcile confirmation prompts with the current event list. Notification ids are
 * persisted locally, so unrelated notifications (including those from other apps)
 * are never cancelled and unchanged event reminders are not needlessly recreated.
 */
export async function scheduleEventNotifications(events: AppEvent[]): Promise<void> {
  const now = Date.now();
  const desired = new Map(
    events
      .filter((event) => event.status === "pending" && new Date(event.scheduled_at).getTime() > now)
      .map((event) => [event.id, event])
  );
  const db = await openDb();
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS event_notifications (
      event_id TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
      notification_id TEXT NOT NULL,
      scheduled_at TEXT NOT NULL
    );
  `);
  const existing = await db.getAllAsync<{ event_id: string; notification_id: string; scheduled_at: string }>(
    "SELECT event_id, notification_id, scheduled_at FROM event_notifications"
  );

  for (const notification of existing) {
    const event = desired.get(notification.event_id);
    if (event && event.scheduled_at === notification.scheduled_at) {
      desired.delete(notification.event_id);
      continue;
    }
    await Notifications.cancelScheduledNotificationAsync(notification.notification_id).catch(() => undefined);
    await db.runAsync("DELETE FROM event_notifications WHERE event_id = ?", [notification.event_id]);
  }

  for (const event of desired.values()) {
    const fireAt = new Date(event.scheduled_at).getTime();
    const notificationId = await Notifications.scheduleNotificationAsync({
      content: {
        title: "Event check-in",
        body: `Did “${event.title}” happen?`,
        data: { event_id: event.id },
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: new Date(fireAt),
      },
    });
    await db.runAsync(
      `INSERT INTO event_notifications (event_id, notification_id, scheduled_at)
       VALUES (?, ?, ?)
       ON CONFLICT(event_id) DO UPDATE SET
         notification_id = excluded.notification_id,
         scheduled_at = excluded.scheduled_at`,
      [event.id, notificationId, event.scheduled_at]
    );
  }
}

/**
 * Register a handler for notification taps. Returns the event_id so the
 * caller can open ConfirmEventModal for that event.
 */
export function onNotificationResponse(handler: (eventId: string) => void) {
  return Notifications.addNotificationResponseReceivedListener((response) => {
    const eventId = response.notification.request.content.data?.event_id;
    if (typeof eventId === "string") handler(eventId);
  });
}
