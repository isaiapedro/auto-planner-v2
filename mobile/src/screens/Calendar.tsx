import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { getLiveCalendarEvents } from "../api/client";
import { colors } from "../theme";
import type { LiveCalendarEvent } from "../types";

const FIRST_HOUR = 6;
const LAST_HOUR = 22;
const HOUR_HEIGHT = 64;
const DAY_WIDTH = 132;
const t = colors;

const asMinutes = (time: string) => {
  const [hour, minute] = time.slice(0, 5).split(":").map(Number);
  return hour * 60 + minute;
};

type CalendarEvent = {
  id: string;
  date: string;
  start: string;
  end: string;
  title: string;
  allDay: boolean;
};

function liveEventToCalendarEvent(event: LiveCalendarEvent): CalendarEvent {
  if (event.all_day) {
    return { id: event.id, date: event.start.slice(0, 10), start: "00:00", end: "00:00", title: event.title, allDay: true };
  }
  const scheduled = new Date(event.start);
  const end = new Date(event.end);
  const formatDate = (value: Date) => {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const formatTime = (value: Date) => `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
  return { id: event.id, date: formatDate(scheduled), start: formatTime(scheduled), end: formatTime(end), title: event.title, allDay: false };
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

export default function Calendar() {
  const [liveEvents, setLiveEvents] = useState<LiveCalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const windowStart = useMemo(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }, []);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => localDateKey(addDays(windowStart, index))), [windowStart]);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true);
    try {
      setLiveEvents(await getLiveCalendarEvents(days[0], nextCalendarDate(days[days.length - 1])));
      setError(null);
    } catch (cause) {
      setLiveEvents([]);
      setError(cause instanceof Error ? cause.message : "Could not load your live calendar.");
    } finally { setLoading(false); setRefreshing(false); }
  }, [days]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const calendarEvents = useMemo(() => {
    return liveEvents.map(liveEventToCalendarEvent).filter((event) => days.includes(event.date));
  }, [liveEvents, days]);
  const events = useMemo(() => {
    const grouped: Record<string, CalendarEvent[]> = {};
    for (const event of calendarEvents) (grouped[event.date] ??= []).push(event);
    for (const values of Object.values(grouped)) values.sort((a, b) => a.start.localeCompare(b.start));
    return grouped;
  }, [calendarEvents]);

  if (loading) return <ActivityIndicator style={styles.center} size="large" />;
  const gridHeight = (LAST_HOUR - FIRST_HOUR) * HOUR_HEIGHT;
  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content} nestedScrollEnabled refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />}>
      <View style={styles.toolbar}>
        <View><Text style={styles.heading}>Calendar</Text><Text style={styles.range}>Live Google Calendar · through {days[days.length - 1]}</Text></View>
      </View>
      <Text style={styles.hint}>{error ? "Live events could not be loaded. Pull down to retry." : "Today plus the next six days. Read-only view."}</Text>
      <ScrollView horizontal nestedScrollEnabled showsHorizontalScrollIndicator={false} contentContainerStyle={styles.calendarScroll}>
        <View>
          <View style={styles.headerRow}>
            <View style={styles.gutter} />
            {days.map((date) => {
              const value = new Date(`${date}T12:00:00`);
              return <View key={date} style={styles.dayHeader}><Text style={styles.weekday}>{value.toLocaleDateString([], { weekday: "short" })}</Text><Text style={styles.date}>{value.getDate()}</Text>{(events[date] ?? []).filter((event) => event.allDay).slice(0, 2).map((event) => <Text key={event.id} numberOfLines={1} style={styles.allDayEvent}>{event.title}</Text>)}</View>;
            })}
          </View>
          <View style={[styles.grid, { height: gridHeight }]}>
            <View style={styles.timeColumn}>{Array.from({ length: LAST_HOUR - FIRST_HOUR + 1 }, (_, index) => <Text key={index} style={[styles.hour, { top: index * HOUR_HEIGHT - 8 }]}>{String(FIRST_HOUR + index).padStart(2, "0")}:00</Text>)}</View>
            {days.map((date) => <View key={date} style={styles.dayColumn}>
              {Array.from({ length: LAST_HOUR - FIRST_HOUR }, (_, index) => <View key={index} style={[styles.hourLine, { top: index * HOUR_HEIGHT }]} />)}
              {(events[date] ?? []).map((event, index) => {
                if (event.allDay) return null;
                const start = Math.max(asMinutes(event.start), FIRST_HOUR * 60);
                const end = Math.min(asMinutes(event.end), LAST_HOUR * 60);
                if (end <= FIRST_HOUR * 60 || start >= LAST_HOUR * 60) return null;
                return <View key={`${event.id}-${index}`} style={[styles.event, { top: ((start - FIRST_HOUR * 60) / 60) * HOUR_HEIGHT + 2, height: Math.max(((end - start) / 60) * HOUR_HEIGHT - 4, 24) }]}><Text numberOfLines={1} style={styles.eventTitle}>{event.title}</Text><Text numberOfLines={1} style={styles.eventTime}>{event.start}–{event.end}</Text></View>;
              })}
            </View>)}
          </View>
        </View>
      </ScrollView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: t.canvas }, content: { paddingBottom: 24 }, center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 16, padding: 24 },
  toolbar: { paddingHorizontal: 16, paddingTop: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, heading: { fontSize: 24, fontWeight: "700", color: t.ink }, range: { marginTop: 2, color: t.muted, fontSize: 13 }, hint: { margin: 16, marginTop: 10, color: t.muted, fontSize: 13 }, allDayEvent: { color: t.primary, fontSize: 9, fontWeight: "700", maxWidth: DAY_WIDTH - 8 },
  empty: { color: t.muted, textAlign: "center", fontSize: 15 },
  calendarScroll: { paddingBottom: 24 }, headerRow: { flexDirection: "row", borderBottomWidth: 1, borderColor: t.border }, gutter: { width: 52 }, dayHeader: { width: DAY_WIDTH, alignItems: "center", paddingVertical: 8, borderLeftWidth: 1, borderColor: t.border }, weekday: { color: t.muted, fontSize: 12, textTransform: "uppercase" }, date: { color: t.ink, fontSize: 17, fontWeight: "700", marginTop: 2 },
  grid: { flexDirection: "row" }, timeColumn: { width: 52, position: "relative" }, hour: { position: "absolute", right: 8, color: t.muted, fontSize: 11 }, dayColumn: { width: DAY_WIDTH, position: "relative", borderLeftWidth: 1, borderColor: t.border }, hourLine: { position: "absolute", width: "100%", borderTopWidth: 1, borderColor: t.border },
  event: { position: "absolute", left: 3, right: 3, backgroundColor: t.primarySoft, borderLeftWidth: 3, borderLeftColor: t.primary, borderRadius: 5, paddingHorizontal: 5, paddingVertical: 3, overflow: "hidden" }, eventTitle: { color: t.primaryText, fontWeight: "700", fontSize: 11 }, eventTime: { color: t.primary, fontSize: 10, marginTop: 1 },
});
