/**
 * Task #11 — Expo local push notifications (Pillar 1 — Capture).
 * Schedules a local notification at each event's scheduled_at.
 * Payload carries event_id for deep-link into the confirmation flow.
 * v1: local scheduling only — no remote push server.
 */
import * as Notifications from "expo-notifications";

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
 * Schedule confirmation prompts for all pending future events.
 * Cancels existing scheduled notifications first to avoid duplicates.
 */
export async function scheduleEventNotifications(events: AppEvent[]): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();

  const now = Date.now();
  for (const event of events) {
    const fireAt = new Date(event.scheduled_at).getTime();
    if (event.status !== "pending" || fireAt <= now) continue;

    await Notifications.scheduleNotificationAsync({
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

const WEEKLY_REVIEW_ID = "review-reminder-weekly";
const MONTHLY_REVIEW_ID = "review-reminder-monthly";

/**
 * Recurring local reminders to generate the weekly/monthly review
 * (generation itself stays a manual paste-into-Claude-Code step).
 * Fixed identifiers make re-scheduling idempotent — safe to call on every app start.
 */
export async function scheduleReviewReminders(): Promise<void> {
  await Notifications.scheduleNotificationAsync({
    identifier: WEEKLY_REVIEW_ID,
    content: {
      title: "Weekly review time",
      body: "Generate this week's review (GET /insights/weekly/context → paste into Claude Code).",
      data: { review_period: "weekly" },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.WEEKLY,
      weekday: 6, // Friday (1 = Sunday ... 7 = Saturday)
      hour: 12,
      minute: 0,
    },
  });

  await Notifications.scheduleNotificationAsync({
    identifier: MONTHLY_REVIEW_ID,
    content: {
      title: "Monthly review time",
      body: "Generate this month's review (GET /insights/monthly/context → paste into Claude Code).",
      data: { review_period: "monthly" },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.CALENDAR,
      day: 1,
      hour: 12,
      minute: 0,
      repeats: true,
    },
  });
}
