import { useFocusEffect, useNavigation, type NavigationProp } from "@react-navigation/native";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, Alert, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from "react-native";

import { getMemos, runAccountTriage } from "../api/client";
import { EmptyState, PrimaryButton, Screen, SecondaryButton, StatusPill } from "../components/ui";
import { colors } from "../theme";
import type { MemoListItem } from "../types";

const t = colors;

function relativeDate(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "Unknown date"
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

function statusTone(status: MemoListItem["status"]): "info" | "success" | "warning" | undefined {
  if (status === "done") return "success";
  if (status === "error") return "warning";
  if (status === "transcribing") return "info";
  return undefined;
}

export default function Memos() {
  const navigation = useNavigation<NavigationProp<{ Inbox: undefined }>>();
  const [memos, setMemos] = useState<MemoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [reviewMode, setReviewMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [instruction, setInstruction] = useState("");
  const [runningReview, setRunningReview] = useState(false);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true); else setLoading(true);
    try {
      const result = await getMemos();
      setMemos(result);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load memos.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const toggleSelection = useCallback((id: string) => {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }, []);
  const stopReviewMode = useCallback(() => { setReviewMode(false); setSelected([]); setInstruction(""); }, []);
  const runReview = useCallback(async () => {
    if (!selected.length) return;
    setRunningReview(true);
    try {
      const run = await runAccountTriage(selected, instruction);
      stopReviewMode();
      const count = run.proposal_ids.length;
      Alert.alert(
        run.status === "needs_manual_review" ? "Review needs your attention" : "Account review ready",
        count ? `${count} ${count === 1 ? "proposal is" : "proposals are"} ready in Inbox.` : "No new proposals were created. You can review the result in Inbox.",
        [{ text: "Later", style: "cancel" }, { text: "View Inbox", onPress: () => navigation.navigate("Inbox") }],
      );
    } catch (cause) {
      Alert.alert("Could not run account review", cause instanceof Error ? cause.message : "Please try again.");
    } finally {
      setRunningReview(false);
    }
  }, [instruction, navigation, selected, stopReviewMode]);

  if (loading) return <Screen style={s.state}><ActivityIndicator color={t.primary} /><Text style={s.muted}>Loading memos…</Text></Screen>;

  return (
    <Screen>
      <FlatList
        data={memos}
        keyExtractor={(memo) => memo.id}
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={t.primary} />}
        ListHeaderComponent={<View style={s.header}><Text style={s.eyebrow}>CAPTURED CONTEXT</Text><Text style={s.title}>Memos</Text><Text style={s.subtitle}>Your recordings and transcripts, without extra interpretation.</Text>{error && <Text style={s.error}>Could not refresh. Pull down to try again.</Text>}<View style={s.reviewCard}><View style={s.reviewCopy}><Text style={s.reviewTitle}>Account review</Text><Text style={s.reviewBody}>{reviewMode ? "Choose completed memos. The review creates suggestions only after your confirmation." : "Turn selected completed memos into a private, reviewable set of follow-ups."}</Text></View>{!reviewMode ? <SecondaryButton label="Select memos" onPress={() => setReviewMode(true)} /> : <><TextInput value={instruction} onChangeText={setInstruction} maxLength={500} placeholder="Optional focus for this review" placeholderTextColor={t.muted} style={s.instruction} accessibilityLabel="Optional account review focus" /><Text style={s.selectionCount}>{selected.length} completed {selected.length === 1 ? "memo" : "memos"} selected</Text><View style={s.reviewActions}><SecondaryButton label="Cancel" onPress={stopReviewMode} style={s.reviewAction} /><PrimaryButton label={runningReview ? "Reviewing…" : "Run review"} loading={runningReview} disabled={!selected.length || runningReview} onPress={runReview} style={s.reviewAction} /></View></>}</View></View>}
        ListEmptyComponent={<EmptyState title="No memos yet" body="Record a memo from Today to keep its transcript here." />}
        renderItem={({ item }) => {
          const open = expanded === item.id;
          const canOpen = item.status === "done" && Boolean(item.transcript);
          const selectable = reviewMode && item.status === "done";
          const isSelected = selected.includes(item.id);
          return <Pressable
            accessibilityRole={selectable || canOpen ? "button" : "text"}
            accessibilityLabel={`${item.event_title || "Memo"}, ${item.status}${selectable ? isSelected ? ", selected for review" : ", select for review" : ""}`}
            accessibilityState={selectable ? { selected: isSelected } : undefined}
            disabled={!selectable && !canOpen}
            onPress={() => selectable ? toggleSelection(item.id) : setExpanded(open ? null : item.id)}
            style={[s.card, isSelected && s.selectedCard]}
          >
            <View style={s.cardTop}><View style={s.cardTitleWrap}><Text style={s.cardTitle} numberOfLines={2}>{item.event_title || "Untitled memo"}</Text><Text style={s.date}>{relativeDate(item.created_at)}</Text></View>{selectable ? <View style={[s.check, isSelected && s.checked]}><Text style={s.checkText}>{isSelected ? "✓" : ""}</Text></View> : <StatusPill label={item.status} tone={statusTone(item.status)} />}</View>
            {item.status === "done" && !open && <Text style={s.hint}>{item.transcript ? "Tap to read transcript" : "Transcript unavailable"}</Text>}
            {item.status === "transcribing" && <Text style={s.hint}>Transcript is being prepared.</Text>}
            {item.status === "queued" && <Text style={s.hint}>Waiting for transcription.</Text>}
            {item.status === "error" && <Text style={s.error}>Transcript could not be created. {item.error || "Try again later."}</Text>}
            {open && <Text selectable style={s.transcript}>{item.transcript}</Text>}
          </Pressable>;
        }}
      />
    </Screen>
  );
}

const s = StyleSheet.create({
  state: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  content: { padding: 16, paddingBottom: 34, gap: 10 },
  header: { paddingVertical: 8, marginBottom: 4, gap: 7 },
  eyebrow: { color: t.primary, fontSize: 10, fontWeight: "800", letterSpacing: 1.1 },
  title: { color: t.ink, fontSize: 30, fontWeight: "800", letterSpacing: -0.6 },
  subtitle: { color: t.muted, fontSize: 14, lineHeight: 20 },
  card: { backgroundColor: t.surface, borderRadius: 16, padding: 15, borderWidth: 1, borderColor: t.border, gap: 8 },
  selectedCard: { borderColor: t.primary, backgroundColor: t.primarySoft },
  cardTop: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  cardTitleWrap: { flex: 1, gap: 3 },
  cardTitle: { color: t.ink, fontSize: 16, fontWeight: "800" },
  date: { color: t.muted, fontSize: 12 },
  hint: { color: t.muted, fontSize: 12 },
  transcript: { color: t.ink, fontSize: 15, lineHeight: 23, paddingTop: 4 },
  muted: { color: t.muted },
  error: { color: t.warning, fontSize: 12, lineHeight: 18 },
  reviewCard: { marginTop: 10, padding: 14, borderRadius: 16, backgroundColor: t.primarySoft, borderWidth: 1, borderColor: t.border, gap: 10 }, reviewCopy: { gap: 3 }, reviewTitle: { color: t.primaryText, fontWeight: "800", fontSize: 15 }, reviewBody: { color: t.primaryText, fontSize: 12, lineHeight: 18 }, instruction: { minHeight: 46, backgroundColor: t.surface, borderRadius: 12, borderWidth: 1, borderColor: t.border, paddingHorizontal: 12, color: t.ink, fontSize: 13 }, selectionCount: { color: t.primaryText, fontWeight: "700", fontSize: 12 }, reviewActions: { flexDirection: "row", gap: 10 }, reviewAction: { flex: 1 }, check: { width: 24, height: 24, borderRadius: 12, borderWidth: 1, borderColor: t.border, backgroundColor: t.surface, alignItems: "center", justifyContent: "center" }, checked: { backgroundColor: t.primary, borderColor: t.primary }, checkText: { color: t.inverse, fontWeight: "900", fontSize: 14 },
});
