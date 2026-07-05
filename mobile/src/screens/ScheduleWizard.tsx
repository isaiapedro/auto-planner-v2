/**
 * Task #9 — First-launch schedule wizard (Pillar 1 — Capture).
 * 3 steps: (1) wake/sleep, (2) goals (long-term w/ deadline + routine w/ cadence —
 * allocation is goal-driven, not domain-weight-driven), (3) fixed blocks.
 * On finish → POST /schedule + POST /goals (one per goal).
 */
import React, { useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { createGoal, createSchedule } from "../api/client";

type FixedBlock = { title: string; days: string[]; start: string; duration_minutes: number };

const WEEKDAYS: { key: string; label: string }[] = [
  { key: "mon", label: "M" },
  { key: "tue", label: "T" },
  { key: "wed", label: "W" },
  { key: "thu", label: "T" },
  { key: "fri", label: "F" },
  { key: "sat", label: "S" },
  { key: "sun", label: "S" },
];
type GoalKind = "long_term" | "routine";
type GoalDraft = { title: string; kind: GoalKind; domain: string; target_date: string; cadence: string };

type Props = { navigation?: { goBack: () => void }; onDone?: () => void };

export default function ScheduleWizard({ navigation, onDone }: Props) {
  const [step, setStep] = useState(0);
  const [wake, setWake] = useState("06:30");
  const [sleep, setSleep] = useState("23:00");
  const [bufferMinutes, setBufferMinutes] = useState("60");
  const [goals, setGoals] = useState<GoalDraft[]>([]);
  const [blocks, setBlocks] = useState<FixedBlock[]>([]);
  const [saving, setSaving] = useState(false);

  const addGoal = (kind: GoalKind) =>
    setGoals((g) => [...g, { title: "", kind, domain: "", target_date: "", cadence: "" }]);

  const addBlock = () =>
    setBlocks((b) => [...b, { title: "", days: [], start: "09:00", duration_minutes: 60 }]);

  const toggleBlockDay = (index: number, day: string) =>
    setBlocks((bl) =>
      bl.map((x, j) =>
        j === index
          ? { ...x, days: x.days.includes(day) ? x.days.filter((d) => d !== day) : [...x.days, day] }
          : x
      )
    );

  const finish = async () => {
    const validGoals = goals.filter((g) => g.title.trim());
    const validBlocks = blocks.filter((b) => b.title.trim());
    if (validBlocks.some((b) => b.days.length === 0)) {
      Alert.alert("Pick at least one day", "Every fixed commitment needs at least one day selected.");
      return;
    }
    setSaving(true);
    try {
      // Goals must exist before schedule creation — POST /schedule reads active
      // goals server-side to allocate exploration/practice blocks around them.
      for (const g of validGoals) {
        await createGoal({
          title: g.title,
          kind: g.kind,
          domain: g.domain || null,
          target_date: g.kind === "long_term" ? g.target_date || null : null,
          cadence: g.kind === "routine" ? g.cadence || null : null,
        });
      }
      await createSchedule({
        wake_time: wake,
        sleep_time: sleep,
        buffer_minutes: parseInt(bufferMinutes || "60", 10),
        fixed_blocks: validBlocks,
      });
      Alert.alert("Schedule created");
      onDone?.();
      navigation?.goBack();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.progress}>
        {[0, 1, 2].map((i) => (
          <View key={i} style={[styles.dot, step >= i && styles.dotActive]} />
        ))}
      </View>

      {step === 0 && (
        <View style={styles.card}>
          <Text style={styles.h}>Sleep window</Text>
          <Field label="Wake time" value={wake} onChange={setWake} />
          <Field label="Sleep time" value={sleep} onChange={setSleep} />
          <Field
            label="Evening buffer before sleep (min) — kept free, no blocks scheduled here"
            value={bufferMinutes}
            onChange={setBufferMinutes}
          />
        </View>
      )}

      {step === 1 && (
        <View style={styles.card}>
          <Text style={styles.h}>Goals</Text>
          <Text style={styles.hint}>
            Long-term goals get a deadline — allocation urgency scales with how close it is.
            Routine goals get a cadence and are slotted into open time now.
          </Text>

          {goals.map((g, i) => (
            <View key={i} style={styles.blockCard}>
              <Text style={styles.goalKindLabel}>
                {g.kind === "long_term" ? "Long-term" : "Routine"}
              </Text>
              <Field
                label="Title"
                value={g.title}
                onChange={(v) => setGoals((gl) => gl.map((x, j) => (j === i ? { ...x, title: v } : x)))}
              />
              <Field
                label="Theme (e.g. tech, health, music)"
                value={g.domain}
                onChange={(v) => setGoals((gl) => gl.map((x, j) => (j === i ? { ...x, domain: v } : x)))}
              />
              {g.kind === "long_term" ? (
                <Field
                  label="Target date (YYYY-MM-DD)"
                  value={g.target_date}
                  onChange={(v) =>
                    setGoals((gl) => gl.map((x, j) => (j === i ? { ...x, target_date: v } : x)))
                  }
                />
              ) : (
                <Field
                  label="Cadence (e.g. daily, 3x/week)"
                  value={g.cadence}
                  onChange={(v) => setGoals((gl) => gl.map((x, j) => (j === i ? { ...x, cadence: v } : x)))}
                />
              )}
            </View>
          ))}

          <View style={styles.goalAddRow}>
            <Pressable style={styles.addBtn} onPress={() => addGoal("long_term")}>
              <Text style={styles.addBtnText}>+ Long-term goal</Text>
            </Pressable>
            <Pressable style={styles.addBtn} onPress={() => addGoal("routine")}>
              <Text style={styles.addBtnText}>+ Routine goal</Text>
            </Pressable>
          </View>
        </View>
      )}

      {step === 2 && (
        <View style={styles.card}>
          <Text style={styles.h}>Fixed commitments</Text>
          {blocks.map((b, i) => (
            <View key={i} style={styles.blockCard}>
              <Field
                label="Title"
                value={b.title}
                onChange={(v) => setBlocks((bl) => bl.map((x, j) => (j === i ? { ...x, title: v } : x)))}
              />
              <Field
                label="Start (HH:MM)"
                value={b.start}
                onChange={(v) => setBlocks((bl) => bl.map((x, j) => (j === i ? { ...x, start: v } : x)))}
              />
              <Field
                label="Duration (min)"
                value={String(b.duration_minutes)}
                onChange={(v) =>
                  setBlocks((bl) =>
                    bl.map((x, j) => (j === i ? { ...x, duration_minutes: parseInt(v || "0", 10) } : x))
                  )
                }
              />
              <Text style={styles.fieldLabel}>Days</Text>
              <View style={styles.dayRow}>
                {WEEKDAYS.map((d) => (
                  <Pressable
                    key={d.key}
                    style={[styles.dayPill, b.days.includes(d.key) && styles.dayPillActive]}
                    onPress={() => toggleBlockDay(i, d.key)}
                  >
                    <Text style={[styles.dayPillText, b.days.includes(d.key) && styles.dayPillTextActive]}>
                      {d.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ))}
          <Pressable style={styles.addBtn} onPress={addBlock}>
            <Text style={styles.addBtnText}>+ Add block</Text>
          </Pressable>
        </View>
      )}

      <View style={styles.nav}>
        {step > 0 && (
          <Pressable style={[styles.navBtn, styles.back]} onPress={() => setStep((s) => s - 1)}>
            <Text style={styles.backText}>Back</Text>
          </Pressable>
        )}
        {step < 2 ? (
          <Pressable style={[styles.navBtn, styles.next]} onPress={() => setStep((s) => s + 1)}>
            <Text style={styles.nextText}>Next</Text>
          </Pressable>
        ) : (
          <Pressable style={[styles.navBtn, styles.next]} onPress={finish} disabled={saving}>
            <Text style={styles.nextText}>{saving ? "Saving…" : "Finish"}</Text>
          </Pressable>
        )}
      </View>
    </ScrollView>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput style={styles.fieldInput} value={value} onChangeText={onChange} />
    </View>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: "#f5f5f5" },
  content:     { padding: 16, gap: 16 },
  progress:    { flexDirection: "row", justifyContent: "center", gap: 8, marginVertical: 8 },
  dot:         { width: 40, height: 6, borderRadius: 3, backgroundColor: "#e5e7eb" },
  dotActive:   { backgroundColor: "#6366f1" },
  card:        { backgroundColor: "#fff", padding: 20, borderRadius: 12, gap: 12 },
  h:           { fontSize: 20, fontWeight: "700", marginBottom: 4 },
  field:       { gap: 4 },
  fieldLabel:  { fontSize: 13, color: "#888" },
  fieldInput:  { backgroundColor: "#f9fafb", borderWidth: 1, borderColor: "#e5e7eb",
                 borderRadius: 8, padding: 12, fontSize: 16 },
  hint:        { fontSize: 13, color: "#888", lineHeight: 18 },
  goalKindLabel: { fontSize: 12, fontWeight: "700", color: "#6366f1", textTransform: "uppercase" },
  goalAddRow:  { flexDirection: "row", gap: 8 },
  blockCard:   { backgroundColor: "#f9fafb", borderRadius: 8, padding: 12, gap: 8, marginBottom: 8 },
  dayRow:      { flexDirection: "row", gap: 6 },
  dayPill:     { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center",
                 backgroundColor: "#e5e7eb" },
  dayPillActive: { backgroundColor: "#6366f1" },
  dayPillText: { fontSize: 13, fontWeight: "600", color: "#374151" },
  dayPillTextActive: { color: "#fff" },
  addBtn:      { padding: 12, alignItems: "center", borderWidth: 1, borderColor: "#6366f1",
                 borderRadius: 8, borderStyle: "dashed" },
  addBtnText:  { color: "#6366f1", fontWeight: "600" },
  nav:         { flexDirection: "row", gap: 12 },
  navBtn:      { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: "center" },
  back:        { backgroundColor: "#f3f4f6", borderWidth: 1, borderColor: "#d1d5db" },
  backText:    { color: "#374151", fontWeight: "700" },
  next:        { backgroundColor: "#6366f1" },
  nextText:    { color: "#fff", fontWeight: "700" },
});
