/**
 * Pillar 2: Dashboard — deterministic charts from pre-computed metrics (task #17).
 * All data from GET /dashboard — zero LLM, zero client-side computation.
 */
import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { getDashboard } from "../api/client";
import { Gauge, SentimentDonut, TopicBars, TrendLine } from "../components/charts";
import type { DashboardMetric } from "../types";

/** Non-scalar metrics store their real payload as JSON in metadata.data. */
function jsonData(m: DashboardMetric | undefined): Record<string, number> {
  if (!m) return {};
  const raw = (m.metadata as any)?.data;
  if (typeof raw !== "string") return {};
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Record<string, DashboardMetric>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await getDashboard();
      setMetrics(Object.fromEntries(d.metrics.map((m) => [m.metric_id, m])));
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading) return <ActivityIndicator style={styles.center} />;

  const hasData = Object.keys(metrics).length > 0;
  if (!hasData) {
    return (
      <View style={styles.center}>
        <Text style={styles.empty}>Record your first memo to see metrics.</Text>
      </View>
    );
  }

  const mood = metrics["mood_7d_avg"];
  const energy = metrics["energy_7d_avg"];
  const completion = metrics["event_completion_rate"];
  const streak = metrics["memo_streak_days"];

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {mood && (
        <View style={styles.card}>
          <Text style={styles.label}>Mood (7-day trend)</Text>
          <TrendLine data={[mood.value]} color="#6366f1" />
        </View>
      )}

      {energy && (
        <View style={styles.card}>
          <Text style={styles.label}>Energy (7-day trend)</Text>
          <TrendLine data={[energy.value]} color="#22c55e" />
        </View>
      )}

      <View style={styles.row}>
        {completion && (
          <View style={[styles.card, styles.half]}>
            <Text style={styles.label}>Event completion</Text>
            <Gauge value={completion.value} label="last 7 days" />
          </View>
        )}
        {streak && (
          <View style={[styles.card, styles.half]}>
            <Text style={styles.label}>Memo streak</Text>
            <Text style={styles.bigNumber}>{Math.round(streak.value)}</Text>
            <Text style={styles.sub}>days</Text>
          </View>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>Top topics (7 days)</Text>
        <TopicBars data={jsonData(metrics["topic_frequency"])} />
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>Sentiment (7 days)</Text>
        <SentimentDonut data={jsonData(metrics["sentiment_distribution"])} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  content:   { padding: 16, gap: 12 },
  center:    { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  card:      { backgroundColor: "#fff", padding: 16, borderRadius: 12 },
  row:       { flexDirection: "row", gap: 12 },
  half:      { flex: 1 },
  label:     { fontSize: 13, color: "#888", marginBottom: 12 },
  bigNumber: { fontSize: 40, fontWeight: "800", color: "#6366f1" },
  sub:       { fontSize: 13, color: "#888" },
  empty:     { textAlign: "center", color: "#aaa" },
});
