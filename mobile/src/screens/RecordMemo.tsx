/**
 * Task #8 — Audio recording screen (Pillar 1 — Capture).
 * Uses expo-audio useAudioRecorder + HIGH_QUALITY preset → .m4a.
 * On stop: save locally to SQLite sync_queue, upload, poll status.
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

import { pollMemoStatus, uploadMemo } from "../api/client";
import { openDb, markMemoSynced, saveMemoLocal } from "../db/schema";

type Props = {
  route?: { params?: { eventTitle?: string } };
  navigation?: { goBack: () => void };
};

export default function RecordMemo({ route, navigation }: Props) {
  const eventTitle = route?.params?.eventTitle;
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [title, setTitle] = useState(eventTitle ?? "");
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading" | "processing">("idle");
  const [statusText, setStatusText] = useState("");

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
    setStatusText("Uploading…");
    try {
      const db = await openDb();
      const { job_id } = await uploadMemo(uri, title || undefined);
      await saveMemoLocal(db, job_id, uri);

      setPhase("processing");
      const result = await pollMemoStatus(job_id);
      if (result.status === "error") {
        Alert.alert("Processing failed", result.error ?? "Unknown error");
      } else {
        await markMemoSynced(db, job_id);
        Alert.alert("Memo saved", "Transcript and insights are ready.");
        navigation?.goBack();
      }
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setPhase("idle");
      setStatusText("");
    }
  };

  const secs = Math.floor((state.durationMillis ?? 0) / 1000);
  const mmss = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;

  const busy = phase === "uploading" || phase === "processing";

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
            {phase === "uploading" ? "Uploading memo…" : "Transcribing + extracting insights…"}
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
