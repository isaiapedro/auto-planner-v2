/**
 * Task #10 — Schedule diff view (Pillar 3 → Capture handoff).
 * Renders LLM schedule_recommendation as per-block [Current → Proposed].
 * Accept → POST /insights/schedule/accept. Reject → discard, no state change.
 */
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { BlockChange, ScheduleRecommendation } from "../types";

const ACTION_COLOR: Record<string, string> = {
  add: "#22c55e",
  move: "#f59e0b",
  remove: "#ef4444",
};

function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string" && v.includes("T")) {
    const d = new Date(v);
    if (!isNaN(d.getTime())) return d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
  }
  return String(v);
}

function BlockRow({ block }: { block: BlockChange }) {
  const color = ACTION_COLOR[block.action] ?? "#6366f1";
  const label =
    block.title ?? block.field ?? (block.block_id ? `block ${block.block_id.slice(0, 6)}` : "block");

  return (
    <View style={styles.block}>
      <View style={styles.blockHeader}>
        <View style={[styles.tag, { backgroundColor: color }]}>
          <Text style={styles.tagText}>{block.action}</Text>
        </View>
        <Text style={styles.blockLabel}>{label}</Text>
      </View>

      {block.action === "move" && (
        <View style={styles.diffRow}>
          <View style={styles.col}>
            <Text style={styles.colLabel}>Current</Text>
            <Text style={styles.old}>{fmt(block.old)}</Text>
          </View>
          <Text style={styles.arrow}>→</Text>
          <View style={styles.col}>
            <Text style={styles.colLabel}>Proposed</Text>
            <Text style={styles.new}>{fmt(block.new)}</Text>
          </View>
        </View>
      )}

      {block.action === "add" && (
        <Text style={styles.addDetail}>
          {block.domain ? `${block.domain} · ` : ""}
          {fmt(block.scheduled_at)}
          {block.duration_minutes ? ` · ${block.duration_minutes}min` : ""}
        </Text>
      )}

      {block.action === "remove" && (
        <Text style={styles.old}>{fmt(block.old ?? block.scheduled_at)}</Text>
      )}
    </View>
  );
}

type Props = {
  recommendation: ScheduleRecommendation;
  accepted: boolean;
  onAccept: () => Promise<void>;
  onReject: () => void;
};

export default function ScheduleDiff({ recommendation, accepted, onAccept, onReject }: Props) {
  const [busy, setBusy] = useState(false);

  const handleAccept = async () => {
    setBusy(true);
    try {
      await onAccept();
    } finally {
      setBusy(false);
    }
  };

  if (accepted) {
    return (
      <View style={[styles.card, styles.acceptedBanner]}>
        <Text style={styles.acceptedText}>Schedule recommendation applied ✓</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.cardLabel}>Schedule Recommendation</Text>
      <Text style={styles.reasoning}>{recommendation.reasoning}</Text>

      {recommendation.blocks.length === 0 ? (
        <Text style={styles.noChanges}>No schedule changes proposed.</Text>
      ) : (
        recommendation.blocks.map((b, i) => <BlockRow key={i} block={b} />)
      )}

      {recommendation.blocks.length > 0 && (
        <View style={styles.actions}>
          <Pressable style={[styles.btn, styles.accept]} onPress={handleAccept} disabled={busy}>
            <Text style={styles.btnText}>{busy ? "Applying…" : "Accept"}</Text>
          </Pressable>
          <Pressable style={[styles.btn, styles.reject]} onPress={onReject} disabled={busy}>
            <Text style={styles.rejectText}>Reject</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card:          { backgroundColor: "#fff", padding: 16, borderRadius: 12, gap: 12 },
  cardLabel:     { fontSize: 12, fontWeight: "700", color: "#6366f1",
                   textTransform: "uppercase" },
  reasoning:     { fontSize: 14, color: "#555", lineHeight: 20 },
  noChanges:     { fontSize: 14, color: "#888", fontStyle: "italic" },
  block:         { backgroundColor: "#f9fafb", borderRadius: 8, padding: 12, gap: 8 },
  blockHeader:   { flexDirection: "row", alignItems: "center", gap: 8 },
  tag:           { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  tagText:       { color: "#fff", fontSize: 11, fontWeight: "700", textTransform: "uppercase" },
  blockLabel:    { fontSize: 14, fontWeight: "600", flex: 1 },
  diffRow:       { flexDirection: "row", alignItems: "center", gap: 8 },
  col:           { flex: 1 },
  colLabel:      { fontSize: 11, color: "#9ca3af" },
  old:           { fontSize: 14, color: "#ef4444", textDecorationLine: "line-through" },
  new:           { fontSize: 14, color: "#22c55e", fontWeight: "600" },
  arrow:         { fontSize: 16, color: "#9ca3af" },
  addDetail:     { fontSize: 14, color: "#374151" },
  actions:       { flexDirection: "row", gap: 8, marginTop: 4 },
  btn:           { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  accept:        { backgroundColor: "#22c55e" },
  reject:        { backgroundColor: "#f3f4f6", borderWidth: 1, borderColor: "#d1d5db" },
  btnText:       { color: "#fff", fontWeight: "700" },
  rejectText:    { color: "#374151", fontWeight: "700" },
  acceptedBanner:{ backgroundColor: "#f0fdf4", borderColor: "#86efac", borderWidth: 1 },
  acceptedText:  { color: "#15803d", fontWeight: "600" },
});
