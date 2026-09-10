import { useFocusEffect, useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { getEventsForRange, getRoutineWeek } from "../api/client";
import type { RootStackParams } from "../navigation/RootNavigator";
import type { AppEvent, RoutineCalendar, RoutineCalendarEvent } from "../types";

const FIRST_HOUR = 6;
const LAST_HOUR = 22;
const HOUR_HEIGHT = 64;
const DAY_WIDTH = 132;

const asMinutes = (time: string) => {
  const [hour, minute] = time.slice(0, 5).split(":").map(Number);
  return hour * 60 + minute;
};

type CalendarEvent = Pick<RoutineCalendarEvent, "date" | "start" | "end" | "title">;

function savedEventToCalendarEvent(event: AppEvent): CalendarEvent {
  const scheduled = new Date(event.scheduled_at);
  const end = new Date(scheduled.getTime() + (event.duration_minutes ?? 60) * 60_000);
  const formatDate = (value: Date) => {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const formatTime = (value: Date) => `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
  return { date: formatDate(scheduled), start: formatTime(scheduled), end: formatTime(end), title: event.title };
}

function nextCalendarDate(date: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const value = new Date(year, month - 1, day + 1);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function localDateKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function projectRoutineIntoWindow(routine: RoutineCalendar | null, days: string[]): CalendarEvent[] {
  if (!routine) return [];
  return days.flatMap((targetDate) => {
    const weekday = new Date(`${targetDate}T12:00:00`).getDay();
    return routine.events
      .filter((event) => new Date(`${event.date}T12:00:00`).getDay() === weekday)
      .map((event) => ({ date: targetDate, start: event.start, end: event.end, title: event.title }));
  });
}

export default function Calendar() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const [routine, setRoutine] = useState<RoutineCalendar | null>(null);
  const [savedEvents, setSavedEvents] = useState<AppEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const windowStart = useMemo(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }, []);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => localDateKey(addDays(windowStart, index))), [windowStart]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const weeklyRoutine = await getRoutineWeek();
      setRoutine(weeklyRoutine);
      // A routine remains useful even while a newly deployed API has not yet
      // exposed the saved-event range endpoint.
      try { setSavedEvents(await getEventsForRange(days[0], nextCalendarDate(days[days.length - 1]))); } catch { setSavedEvents([]); }
    } catch {
      setRoutine(null);
      setSavedEvents([]);
    } finally { setLoading(false); }
  }, [days]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const calendarEvents = useMemo(() => {
    const combined: CalendarEvent[] = [...projectRoutineIntoWindow(routine, days), ...savedEvents.map(savedEventToCalendarEvent)];
    // Routine occurrences are also saved events after an apply. Collapse that
    // shared representation while retaining explicitly added one-time blocks.
    return [...new Map(combined.map((event) => [`${event.date}|${event.start}|${event.title}`, event])).values()];
  }, [routine, savedEvents, days]);
  const events = useMemo(() => {
    const grouped: Record<string, CalendarEvent[]> = {};
    for (const event of calendarEvents) (grouped[event.date] ??= []).push(event);
    for (const values of Object.values(grouped)) values.sort((a, b) => a.start.localeCompare(b.start));
    return grouped;
  }, [calendarEvents]);

  if (loading) return <ActivityIndicator style={styles.center} size="large" />;
  if (!routine) return (
    <View style={styles.center}>
      <Text style={styles.empty}>Your calendar is not available yet.</Text>
      <Pressable style={styles.addButton} onPress={() => navigation.navigate("AddCalendarBlock")}><Text style={styles.addText}>Add block</Text></Pressable>
    </View>
  );

  const gridHeight = (LAST_HOUR - FIRST_HOUR) * HOUR_HEIGHT;
  return (
    <View style={styles.container}>
      <View style={styles.toolbar}>
        <View><Text style={styles.heading}>Calendar</Text><Text style={styles.range}>Today through {days[days.length - 1]}</Text></View>
        <Pressable style={styles.addButton} onPress={() => navigation.navigate("AddCalendarBlock")}><Text style={styles.addText}>+ Add block</Text></Pressable>
      </View>
      <Text style={styles.hint}>Today plus the next six days. Your Plan creates blocks.</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.calendarScroll}>
        <View>
          <View style={styles.headerRow}>
            <View style={styles.gutter} />
            {days.map((date) => {
              const value = new Date(`${date}T12:00:00`);
              return <View key={date} style={styles.dayHeader}><Text style={styles.weekday}>{value.toLocaleDateString([], { weekday: "short" })}</Text><Text style={styles.date}>{value.getDate()}</Text></View>;
            })}
          </View>
          <View style={[styles.grid, { height: gridHeight }]}>
            <View style={styles.timeColumn}>{Array.from({ length: LAST_HOUR - FIRST_HOUR + 1 }, (_, index) => <Text key={index} style={[styles.hour, { top: index * HOUR_HEIGHT - 8 }]}>{String(FIRST_HOUR + index).padStart(2, "0")}:00</Text>)}</View>
            {days.map((date) => <View key={date} style={styles.dayColumn}>
              {Array.from({ length: LAST_HOUR - FIRST_HOUR }, (_, index) => <View key={index} style={[styles.hourLine, { top: index * HOUR_HEIGHT }]} />)}
              {(events[date] ?? []).map((event, index) => {
                const start = Math.max(asMinutes(event.start), FIRST_HOUR * 60);
                const end = Math.min(asMinutes(event.end), LAST_HOUR * 60);
                if (end <= FIRST_HOUR * 60 || start >= LAST_HOUR * 60) return null;
                return <View key={`${event.title}-${index}`} style={[styles.event, { top: ((start - FIRST_HOUR * 60) / 60) * HOUR_HEIGHT + 2, height: Math.max(((end - start) / 60) * HOUR_HEIGHT - 4, 24) }]}><Text numberOfLines={1} style={styles.eventTitle}>{event.title}</Text><Text numberOfLines={1} style={styles.eventTime}>{event.start}–{event.end}</Text></View>;
              })}
            </View>)}
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff" }, center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 16, padding: 24 },
  toolbar: { paddingHorizontal: 16, paddingTop: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, heading: { fontSize: 24, fontWeight: "700", color: "#111827" }, range: { marginTop: 2, color: "#6b7280", fontSize: 13 }, hint: { margin: 16, marginTop: 10, color: "#6b7280", fontSize: 13 },
  addButton: { backgroundColor: "#6366f1", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 20 }, addText: { color: "#fff", fontWeight: "700", fontSize: 13 }, empty: { color: "#4b5563", textAlign: "center", fontSize: 15 },
  calendarScroll: { paddingBottom: 24 }, headerRow: { flexDirection: "row", borderBottomWidth: 1, borderColor: "#e5e7eb" }, gutter: { width: 52 }, dayHeader: { width: DAY_WIDTH, alignItems: "center", paddingVertical: 8, borderLeftWidth: 1, borderColor: "#f3f4f6" }, weekday: { color: "#6b7280", fontSize: 12, textTransform: "uppercase" }, date: { color: "#111827", fontSize: 17, fontWeight: "700", marginTop: 2 },
  grid: { flexDirection: "row" }, timeColumn: { width: 52, position: "relative" }, hour: { position: "absolute", right: 8, color: "#9ca3af", fontSize: 11 }, dayColumn: { width: DAY_WIDTH, position: "relative", borderLeftWidth: 1, borderColor: "#e5e7eb" }, hourLine: { position: "absolute", width: "100%", borderTopWidth: 1, borderColor: "#f3f4f6" },
  event: { position: "absolute", left: 3, right: 3, backgroundColor: "#e0e7ff", borderLeftWidth: 3, borderLeftColor: "#6366f1", borderRadius: 5, paddingHorizontal: 5, paddingVertical: 3, overflow: "hidden" }, eventTitle: { color: "#3730a3", fontWeight: "700", fontSize: 11 }, eventTime: { color: "#4f46e5", fontSize: 10, marginTop: 1 },
});
