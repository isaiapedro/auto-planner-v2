import React, { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { createCalendarBlock } from "../api/client";

type Props = { navigation?: { goBack: () => void } };

const today = () => new Date().toISOString().slice(0, 10);

export default function AddCalendarBlock({ navigation }: Props) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(today());
  const [start, setStart] = useState("09:00");
  const [duration, setDuration] = useState("60");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const minutes = Number.parseInt(duration, 10);
    if (!title.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(start) || minutes < 5) {
      Alert.alert("Check the block", "Enter a title, YYYY-MM-DD date, HH:MM time, and a duration of at least 5 minutes.");
      return;
    }
    setSaving(true);
    try {
      await createCalendarBlock({ title: title.trim(), scheduled_at: `${date}T${start}:00-03:00`, duration_minutes: minutes });
      Alert.alert("Block added", "It is now in your Planner and Google Calendar.");
      navigation?.goBack();
    } catch (error: any) {
      Alert.alert("Couldn’t add block", error.message);
    } finally {
      setSaving(false);
    }
  };

  return <View style={styles.container}>
    <Text style={styles.hint}>Add a one-time commitment to your schedule and Google Calendar.</Text>
    <Field label="Title" value={title} setValue={setTitle} placeholder="Gym, appointment, focused work…" />
    <Field label="Date (YYYY-MM-DD)" value={date} setValue={setDate} keyboardType="numbers-and-punctuation" />
    <Field label="Start time (HH:MM)" value={start} setValue={setStart} keyboardType="numbers-and-punctuation" />
    <Field label="Duration (minutes)" value={duration} setValue={setDuration} keyboardType="number-pad" />
    <Pressable style={[styles.save, saving && styles.disabled]} onPress={save} disabled={saving}><Text style={styles.saveText}>{saving ? "Adding…" : "Add block"}</Text></Pressable>
  </View>;
}

function Field({ label, value, setValue, placeholder, keyboardType }: { label: string; value: string; setValue: (value: string) => void; placeholder?: string; keyboardType?: "default" | "number-pad" | "numbers-and-punctuation" }) {
  return <View style={styles.field}><Text style={styles.label}>{label}</Text><TextInput style={styles.input} value={value} onChangeText={setValue} placeholder={placeholder} keyboardType={keyboardType} /></View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20, gap: 16 }, hint: { color: "#4b5563", lineHeight: 20 }, field: { gap: 5 }, label: { color: "#374151", fontWeight: "600", fontSize: 13 }, input: { backgroundColor: "#fff", borderColor: "#d1d5db", borderWidth: 1, borderRadius: 10, padding: 13, fontSize: 16 }, save: { backgroundColor: "#6366f1", paddingVertical: 15, borderRadius: 12, alignItems: "center", marginTop: 8 }, disabled: { opacity: 0.5 }, saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
