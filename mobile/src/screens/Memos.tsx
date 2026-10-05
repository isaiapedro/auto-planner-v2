import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { getMemos } from "../api/client";
import { EmptyState, Screen, StatusPill } from "../components/ui";
import { colors } from "../theme";
import type { MemoListItem } from "../types";

const t = colors;

function relativeDate(iso: string, recordedAtKnown: boolean) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "Unknown date"
    : new Intl.DateTimeFormat(undefined, recordedAtKnown
      ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }
      : { month: "short", day: "numeric" }).format(date);
}

function statusTone(status: MemoListItem["status"]): "info" | "success" | "warning" | undefined {
  if (status === "done") return "success";
  if (status === "error") return "warning";
  if (status === "transcribing") return "info";
  return undefined;
}

export default function Memos() {
  const [memos, setMemos] = useState<MemoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

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

  if (loading) return <Screen style={s.state}><ActivityIndicator color={t.primary} /><Text style={s.muted}>Loading memos…</Text></Screen>;

  return (
    <Screen>
      <FlatList
        data={memos}
        keyExtractor={(memo) => memo.id}
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={t.primary} />}
        ListHeaderComponent={<View style={s.header}><Text style={s.eyebrow}>CAPTURED CONTEXT</Text><Text style={s.title}>Memos</Text><Text style={s.subtitle}>Your recordings and transcripts, without extra interpretation.</Text>{error && <Text style={s.error}>Could not refresh. Pull down to try again.</Text>}</View>}
        ListEmptyComponent={<EmptyState title="No memos yet" body="Record a memo from Today to keep its transcript here." />}
        renderItem={({ item }) => {
          const open = expanded === item.id;
          const canOpen = item.status === "done" && Boolean(item.transcript);
          return <Pressable
            accessibilityRole={canOpen ? "button" : "text"}
            accessibilityLabel={`${item.event_title || "Memo"}, ${item.status}`}
            disabled={!canOpen}
            onPress={() => setExpanded(open ? null : item.id)}
            style={s.card}
          >
            <View style={s.cardTop}><View style={s.cardTitleWrap}><Text style={s.cardTitle} numberOfLines={2}>{item.event_title || "Untitled memo"}</Text><Text style={s.date}>{relativeDate(item.created_at, item.recorded_at_known)}</Text></View><StatusPill label={item.status} tone={statusTone(item.status)} /></View>
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
  cardTop: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  cardTitleWrap: { flex: 1, gap: 3 },
  cardTitle: { color: t.ink, fontSize: 16, fontWeight: "800" },
  date: { color: t.muted, fontSize: 12 },
  hint: { color: t.muted, fontSize: 12 },
  transcript: { color: t.ink, fontSize: 15, lineHeight: 23, paddingTop: 4 },
  muted: { color: t.muted },
  error: { color: t.warning, fontSize: 12, lineHeight: 18 },
});
