/**
 * Task #8 — Audio recording screen (Pillar 1 — Capture).
 * Uses expo-audio useAudioRecorder + HIGH_QUALITY preset → .m4a.
 * On stop: save locally to SQLite sync_queue, then upload for background transcription.
 */
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { confirmEvent, uploadMemo } from "../api/client";
import { openDb, markMemoSynced, saveMemoLocal } from "../db/schema";

type Props = {
  route?: { params?: { eventTitle?: string; eventId?: string } };
  navigation?: { goBack: () => void };
};

function newMemoId(): string {
  // Expo/Hermes exposes Web Crypto on current SDKs. The fallback keeps the
  // UUID-shaped client key usable on older Android runtimes.
  const values = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(values);
  } else {
    for (let i = 0; i < values.length; i += 1) values[i] = Math.floor(Math.random() * 256);
  }
  values[6] = (values[6] & 0x0f) | 0x40;
  values[8] = (values[8] & 0x3f) | 0x80;
  const hex = Array.from(values, (v) => v.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export default function RecordMemo({ route, navigation }: Props) {
  const eventTitle = route?.params?.eventTitle;
  const eventId = route?.params?.eventId;
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [title, setTitle] = useState(eventTitle ?? "");
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading">("idle");

  useEffect(() => {
    (async () => {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        Alert.alert("Permission required", "Microphone access is needed to record memos.");
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    })();
  }, []);

  const startRecording = async () => {
    await recorder.prepareToRecordAsync();
    recorder.record();
    setPhase("recording");
  };

  const stopAndUpload = async () => {
    await recorder.stop();
    const uri = recorder.uri;
    if (!uri) {
      Alert.alert("Recording failed", "No audio captured.");
      setPhase("idle");
      return;
    }

    setPhase("uploading");
    try {
      const db = await openDb();
      // Queue the local recording *before* the network request. A failed or
      // slow long upload therefore leaves a recoverable local reference rather
      // than making the recording disappear with the error dialog.
      const memoId = newMemoId();
      await saveMemoLocal(db, memoId, uri, eventId, eventTitle);
      const { job_id } = await uploadMemo(uri, title || undefined, memoId);
      // Today may already have marked the event complete before opening this
      // recorder. This idempotent confirmation only attaches the durable memo;
      // it does not create a second event or duplicate a completion action.
      if (eventId) await confirmEvent(eventId, true, job_id);
      await markMemoSynced(db, job_id);
      Alert.alert("Memo saved", "Your recording is safely stored. The transcript will finish in the background.");
      navigation?.goBack();
    } catch (e: any) {
      Alert.alert("Upload paused", `Your recording remains queued on this device. ${e.message}`);
    } finally {
      setPhase("idle");
    }
  };

  const secs = Math.floor((state.durationMillis ?? 0) / 1000);
  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;

  const busy = phase === "uploading";

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="Memo title (optional)"
        value={title}
        onChangeText={setTitle}
        editable={phase === "idle"}
      />

      <View style={styles.timerWrap}>
        <Text style={styles.timer}>{mmss}</Text>
        {phase === "recording" && <View style={styles.recDot} />}
      </View>

      {busy ? (
        <View style={styles.busy}>
          <ActivityIndicator size="large" color="#6366f1" />
          <Text style={styles.busyText}>
            Uploading memo…
          </Text>
        </View>
      ) : (
        <Pressable
          style={[styles.recordBtn, phase === "recording" && styles.recordBtnActive]}
          onPress={phase === "recording" ? stopAndUpload : startRecording}
        >
          <Text style={styles.recordBtnText}>
            {phase === "recording" ? "Stop & Save" : "Record"}
          </Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: "#f5f5f5", padding: 24, justifyContent: "center", gap: 32 },
  input:          { backgroundColor: "#fff", borderRadius: 12, padding: 16, fontSize: 16 },
  timerWrap:      { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 12 },
  timer:          { fontSize: 56, fontWeight: "200", fontVariant: ["tabular-nums"] },
  recDot:         { width: 16, height: 16, borderRadius: 8, backgroundColor: "#ef4444" },
  recordBtn:      { backgroundColor: "#6366f1", paddingVertical: 20, borderRadius: 16, alignItems: "center" },
  recordBtnActive:{ backgroundColor: "#ef4444" },
  recordBtnText:  { color: "#fff", fontSize: 18, fontWeight: "700" },
  busy:           { alignItems: "center", gap: 16 },
  busyText:       { color: "#555", fontSize: 15 },
});
