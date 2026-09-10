import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { applyRoutineWeek, getRoutineWeek } from "../api/client";
import type { RoutineCalendar, RoutineCalendarEvent } from "../types";

type Props = {
  onDone?: () => void;
  navigation?: { goBack: () => void };
};

function groupByDate(events: RoutineCalendarEvent[]) {
  const grouped: Record<string, RoutineCalendarEvent[]> = {};
  for (const event of events) {
    grouped[event.date] = grouped[event.date] ?? [];
    grouped[event.date].push(event);
  }
  return grouped;
}

export default function RoutineWeekScreen({ onDone, navigation }: Props) {
  const [routine, setRoutine] = useState<RoutineCalendar | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getRoutineWeek();
      setRoutine(data);
    } catch (error: any) {
      Alert.alert("Error", error.message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleApply = async () => {
    if (!routine) return;
    Alert.alert(
      "Apply weekly routine?",
      `${routine.event_count} blocks (${routine.week_start} → ${routine.week_end}) will be written to Google Calendar. No LLM involved.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Apply",
          style: "default",
          onPress: async () => {
            setApplying(true);
            try {
              const result = await applyRoutineWeek();
              if (result.events_failed > 0 && result.events_created === 0) {
                Alert.alert(
                  "Apply failed",
                  `No events were saved. ${result.events_failed} failed.` +
                    (result.errors[0]?.error ? `\n\n${result.errors[0].error}` : "")
                );
                return;
              }
              Alert.alert(
                "Routine applied",
                `Saved ${result.events_created} events` +
                  (result.events_existing ? ` (${result.events_existing} already existed)` : "") +
                  (result.events_failed > 0 ? ` (${result.events_failed} failed).` : ".") +
                  "\n\nOpen Today tab to see your schedule."
              );
              onDone?.();
              navigation?.goBack();
            } catch (error: any) {
              Alert.alert("Error", error.message);
            } finally {
              setApplying(false);
            }
          },
        },
      ]
    );
  };

  if (loading) {
    return <ActivityIndicator style={styles.center} size="large" />;
  }

  if (!routine) {
    return (
      <View style={styles.center}>
        <Text style={styles.error}>Routine calendar not found on server.</Text>
        <Pressable style={styles.retryBtn} onPress={load}>
          <Text style={styles.retryText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  const grouped = groupByDate(routine.events);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Weekly routine</Text>
      <Text style={styles.subheading}>
        {routine.week_start} → {routine.week_end}
      </Text>
      <View style={styles.metaCard}>
        <Text style={styles.metaRow}>{routine.event_count} calendar blocks</Text>
        <Text style={styles.metaRow}>Source: {routine.source_markdown}</Text>
        <Text style={styles.metaHint}>
          Pre-authored in knowledge base. Applies directly to Google Calendar — no model pipeline.
        </Text>
      </View>

      {Object.entries(grouped).map(([date, events]) => (
        <View key={date} style={styles.card}>
          <Text style={styles.dayLabel}>
            {date}
            {events[0]?.day_theme ? ` · ${events[0].day_theme}` : ""}
          </Text>
          {events.map((event, index) => (
            <View key={`${date}-${index}`} style={styles.eventRow}>
              <Text style={styles.eventTime}>
                {event.start}–{event.end}
              </Text>
              <View style={styles.eventBody}>
                <Text style={styles.eventTitle}>{event.title}</Text>
                {event.notes ? <Text style={styles.eventNotes}>{event.notes}</Text> : null}
              </View>
            </View>
          ))}
        </View>
      ))}

      <Pressable style={styles.applyBtn} onPress={handleApply} disabled={applying}>
        <Text style={styles.applyText}>{applying ? "Creating events…" : "Apply to Google Calendar"}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  content: { padding: 16, gap: 12, paddingBottom: 32 },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  heading: { fontSize: 22, fontWeight: "700" },
  subheading: { fontSize: 14, color: "#666" },
  metaCard: {
    backgroundColor: "#ecfdf5",
    borderColor: "#6ee7b7",
    borderWidth: 1,
    padding: 12,
    borderRadius: 10,
    gap: 4,
  },
  metaRow: { fontSize: 13, color: "#065f46" },
  metaHint: { fontSize: 12, color: "#047857", lineHeight: 17, marginTop: 4 },
  card: { backgroundColor: "#fff", padding: 16, borderRadius: 12, gap: 8 },
  dayLabel: { fontSize: 14, fontWeight: "700", color: "#111827", marginBottom: 4 },
  eventRow: { flexDirection: "row", gap: 10, paddingVertical: 4 },
  eventTime: { width: 92, fontSize: 12, color: "#6366f1", fontWeight: "600" },
  eventBody: { flex: 1, gap: 2 },
  eventTitle: { fontSize: 14, color: "#374151" },
  eventNotes: { fontSize: 12, color: "#6b7280", fontStyle: "italic" },
  applyBtn: {
    backgroundColor: "#059669",
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: "center",
    marginTop: 8,
  },
  applyText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  error: { fontSize: 15, color: "#374151", textAlign: "center", marginBottom: 12 },
  retryBtn: { backgroundColor: "#6366f1", paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  retryText: { color: "#fff", fontWeight: "700" },
});
