/**
 * Task #18 — typed chart component wrappers over react-native-gifted-charts.
 * Deterministic renders from structured metric data (Pillar 2 — zero LLM).
 */
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { BarChart, LineChart, PieChart } from "react-native-gifted-charts";

const PALETTE = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#a855f7"];

// ── Line: mood / energy trend ────────────────────────────────────────────────

export function TrendLine({ data, color = "#6366f1" }: { data: number[]; color?: string }) {
  const points = data.map((v) => ({ value: v * 100 }));
  return (
    <LineChart
      data={points}
      color={color}
      thickness={3}
      curved
      hideDataPoints={false}
      dataPointsColor={color}
      yAxisOffset={0}
      maxValue={100}
      noOfSections={4}
      hideRules={false}
      height={120}
      areaChart
      startFillColor={color}
      startOpacity={0.2}
      endOpacity={0.0}
      yAxisTextStyle={styles.axis}
      xAxisLabelTextStyle={styles.axis}
    />
  );
}

// ── Bar: topic frequency ─────────────────────────────────────────────────────

export function TopicBars({ data }: { data: Record<string, number> }) {
  const bars = Object.entries(data).map(([label, value], i) => ({
    value,
    label,
    frontColor: PALETTE[i % PALETTE.length],
  }));
  if (!bars.length) return <Empty label="No topics yet" />;
  return (
    <BarChart
      data={bars}
      barWidth={28}
      spacing={18}
      roundedTop
      noOfSections={3}
      height={140}
      yAxisTextStyle={styles.axis}
      xAxisLabelTextStyle={styles.axis}
    />
  );
}

// ── Donut: sentiment distribution ────────────────────────────────────────────

export function SentimentDonut({ data }: { data: Record<string, number> }) {
  const colorMap: Record<string, string> = {
    positive: "#22c55e",
    neutral: "#94a3b8",
    negative: "#ef4444",
  };
  const slices = Object.entries(data).map(([label, value]) => ({
    value,
    color: colorMap[label] ?? "#6366f1",
    text: label,
  }));
  if (!slices.length) return <Empty label="No sentiment data" />;
  return (
    <View style={styles.donutRow}>
      <PieChart data={slices} donut radius={70} innerRadius={45} />
      <View style={styles.legend}>
        {slices.map((s) => (
          <View key={s.text} style={styles.legendRow}>
            <View style={[styles.dot, { backgroundColor: s.color }]} />
            <Text style={styles.legendText}>
              {s.text} ({s.value})
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ── Gauge: completion rate ───────────────────────────────────────────────────

export function Gauge({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <View style={styles.gauge}>
      <View style={styles.gaugeBg}>
        <View style={[styles.gaugeFill, { width: `${pct}%` as any }]} />
      </View>
      <Text style={styles.gaugeValue}>{pct}%</Text>
      <Text style={styles.gaugeLabel}>{label}</Text>
    </View>
  );
}

function Empty({ label }: { label: string }) {
  return <Text style={styles.empty}>{label}</Text>;
}

const styles = StyleSheet.create({
  axis:       { color: "#94a3b8", fontSize: 10 },
  donutRow:   { flexDirection: "row", alignItems: "center", gap: 16 },
  legend:     { flex: 1, gap: 6 },
  legendRow:  { flexDirection: "row", alignItems: "center", gap: 8 },
  dot:        { width: 12, height: 12, borderRadius: 6 },
  legendText: { fontSize: 13, color: "#374151", textTransform: "capitalize" },
  gauge:      { alignItems: "stretch" },
  gaugeBg:    { height: 12, backgroundColor: "#e5e7eb", borderRadius: 6, overflow: "hidden" },
  gaugeFill:  { height: 12, backgroundColor: "#6366f1", borderRadius: 6 },
  gaugeValue: { fontSize: 24, fontWeight: "700", marginTop: 8 },
  gaugeLabel: { fontSize: 13, color: "#888" },
  empty:      { color: "#aaa", fontStyle: "italic", paddingVertical: 12 },
});
