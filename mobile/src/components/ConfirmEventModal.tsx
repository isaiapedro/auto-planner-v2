/**
 * Task #7 — Event confirmation state machine (Pillar 1 — Capture).
 *
 * Flow:
 *   "Did [event] happen?"  ── No ──►  mark skipped
 *          │ Yes
 *          ▼
 *   "Save an audio memo?"  ── No ──►  mark confirmed
 *          │ Yes
 *          ▼
 *   navigate to RecordMemo (memo linked to event)
 */
import React from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import type { AppEvent } from "../types";

type Step = "confirm" | "memo";

type Props = {
  event: AppEvent | null;
  onClose: () => void;
  onSkip: (event: AppEvent) => void;
  onConfirmNoMemo: (event: AppEvent) => void;
  onConfirmWithMemo: (event: AppEvent) => void;
};

export default function ConfirmEventModal({
  event,
  onClose,
  onSkip,
  onConfirmNoMemo,
  onConfirmWithMemo,
}: Props) {
  const [step, setStep] = React.useState<Step>("confirm");

  React.useEffect(() => {
    if (event) setStep("confirm");
  }, [event]);

  if (!event) return null;

  return (
    <Modal transparent animationType="fade" visible={!!event} onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          {step === "confirm" ? (
            <>
              <Text style={styles.q}>Did “{event.title}” happen?</Text>
              <View style={styles.row}>
                <Pressable style={[styles.btn, styles.yes]} onPress={() => setStep("memo")}>
                  <Text style={styles.btnText}>Yes</Text>
                </Pressable>
                <Pressable style={[styles.btn, styles.no]} onPress={() => onSkip(event)}>
                  <Text style={styles.btnText}>No / Skipped</Text>
                </Pressable>
              </View>
            </>
          ) : (
            <>
              <Text style={styles.q}>Save an audio memo?</Text>
              <View style={styles.row}>
                <Pressable style={[styles.btn, styles.yes]} onPress={() => onConfirmWithMemo(event)}>
                  <Text style={styles.btnText}>Record memo</Text>
                </Pressable>
                <Pressable style={[styles.btn, styles.plain]} onPress={() => onConfirmNoMemo(event)}>
                  <Text style={styles.plainText}>Just confirm</Text>
                </Pressable>
              </View>
            </>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop:  { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  sheet:     { backgroundColor: "#fff", padding: 24, borderTopLeftRadius: 24, borderTopRightRadius: 24, gap: 20 },
  q:         { fontSize: 18, fontWeight: "600", textAlign: "center" },
  row:       { flexDirection: "row", gap: 12 },
  btn:       { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: "center" },
  yes:       { backgroundColor: "#22c55e" },
  no:        { backgroundColor: "#ef4444" },
  plain:     { backgroundColor: "#f3f4f6", borderWidth: 1, borderColor: "#d1d5db" },
  btnText:   { color: "#fff", fontWeight: "700" },
  plainText: { color: "#374151", fontWeight: "700" },
});
