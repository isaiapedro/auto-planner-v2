/** Weekly routine overview: live structure, category balance, then explicit actions. */
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { getRoutineWeek, syncRoutineEventsLocal } from "../api/client";
import { ErrorState, PrimaryButton, Screen, SectionHeader, SecondaryButton } from "../components/ui";
import type { RootStackParams } from "../navigation/RootNavigator";
import type { RoutineCalendar } from "../types";
import { colors } from "../theme";

const t = colors;
const categoryColor: Record<string, string> = { work: t.primary, deep_work: t.primary, learning: t.success, creative: t.warning, movement: t.info, rest: t.muted, fixed: t.warning, anchor: t.info, research: t.primary };
const shortDate = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function Schedule() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const [routine, setRoutine] = useState<RoutineCalendar | null>(null); const [loading, setLoading] = useState(true); const [refreshing, setRefreshing] = useState(false); const [syncing, setSyncing] = useState(false);
  const load = useCallback(async () => { setLoading(true); try { setRoutine(await getRoutineWeek()); } catch { setRoutine(null); } finally { setLoading(false); } }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const categories = useMemo(() => { if (!routine) return []; const counts = routine.events.reduce<Record<string, number>>((all, event) => { const key = event.category ?? "other"; all[key] = (all[key] ?? 0) + 1; return all; }, {}); return Object.entries(counts).sort(([, a], [, b]) => b - a); }, [routine]);
  const refresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };
  const handleSync = () => Alert.alert("Show routine in Today?", "This adds the existing Google Calendar routine to Today without creating duplicate calendar events.", [{ text: "Cancel", style: "cancel" }, { text: "Show in Today", onPress: async () => { setSyncing(true); try { const result = await syncRoutineEventsLocal(); Alert.alert("Added to Today", `${result.events_created} routine events are now visible in Today.`); } catch (error: any) { Alert.alert("Error", error.message); } finally { setSyncing(false); } } }]);
  if (loading) return <Screen style={s.state}><ActivityIndicator color={t.primary} /><Text style={s.stateText}>Reading your weekly structure…</Text></Screen>;
  return <Screen><ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={t.primary} />} showsVerticalScrollIndicator={false}>
    <View style={s.hero}><Text style={s.eyebrow}>WEEKLY ROUTINE</Text><Text style={s.heroTitle}>{routine ? "Your week, at a glance" : "Your week is unavailable"}</Text><Text style={s.heroBody}>{routine ? `${shortDate(routine.week_start)} — ${shortDate(routine.week_end)} · ${routine.event_count} intentional blocks` : "Reconnect to load the routine saved in your Personal domain."}</Text>{routine && <View style={s.heroStats}><View><Text style={s.heroValue}>{routine.events.length}</Text><Text style={s.heroLabel}>moments</Text></View><View style={s.heroRule} /><View><Text style={s.heroValue}>{categories.length}</Text><Text style={s.heroLabel}>areas</Text></View></View>}</View>
    {!routine ? <ErrorState title="Routine not loaded" body="Check your connection, then try again." action={<SecondaryButton label="Try again" onPress={load} />} /> : <>
      <View style={s.section}><SectionHeader eyebrow="THE RHYTHM" title="Where your time is held" /><View style={s.balance}>{categories.map(([category, count]) => <View key={category} style={s.category} accessibilityLabel={`${category.replaceAll("_", " ")}: ${count} routine blocks`}><View style={s.categoryTop}><Text style={s.categoryName}>{category.replaceAll("_", " ")}</Text><Text style={s.categoryCount}>{count}</Text></View><View style={s.track}><View style={[s.fill, { width: `${Math.max(8, (count / routine.event_count) * 100)}%`, backgroundColor: categoryColor[category] ?? t.primary }]} /></View></View>)}</View></View>
      <View style={s.section}><SectionHeader eyebrow="NEXT STEP" title="Review before you apply" /><Text style={s.helper}>See every block, its timing, and its notes before anything is written to Google Calendar.</Text><PrimaryButton label="Review weekly routine" accessibilityHint="Opens the full weekly routine" onPress={() => navigation.navigate("RoutineWeek")} /></View>
      <View style={s.sync}><Text style={s.syncTitle}>Already on Google Calendar?</Text><Text style={s.syncText}>Bring existing routine events into Today. This never creates duplicates.</Text><SecondaryButton label="Show routine in Today" loading={syncing} accessibilityHint="Adds existing routine events to Today" onPress={handleSync} /></View>
    </>}
  </ScrollView></Screen>;
}

const s = StyleSheet.create({
  content: { padding: 16, paddingBottom: 36, gap: 24 }, state: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 }, stateText: { color: t.muted }, hero: { backgroundColor: t.primarySoft, borderRadius: 24, padding: 22, gap: 9, borderWidth: 1, borderColor: t.border }, eyebrow: { color: t.muted, fontSize: 10, fontWeight: "800", letterSpacing: 1.2 }, heroTitle: { color: t.ink, fontWeight: "800", fontSize: 28, letterSpacing: -.7 }, heroBody: { color: t.primaryText, fontSize: 14, lineHeight: 20 }, heroStats: { flexDirection: "row", gap: 18, marginTop: 8, alignItems: "center" }, heroValue: { color: t.primary, fontWeight: "800", fontSize: 23, fontVariant: ["tabular-nums"] }, heroLabel: { color: t.primaryText, fontSize: 10, textTransform: "uppercase", letterSpacing: .8 }, heroRule: { width: 1, height: 30, backgroundColor: t.border }, section: { gap: 10 }, balance: { backgroundColor: t.surface, borderRadius: 18, padding: 16, borderWidth: 1, borderColor: t.border, gap: 12 }, category: { gap: 6 }, categoryTop: { flexDirection: "row", justifyContent: "space-between" }, categoryName: { color: t.ink, fontSize: 13, fontWeight: "700", textTransform: "capitalize" }, categoryCount: { color: t.muted, fontSize: 12, fontWeight: "700", fontVariant: ["tabular-nums"] }, track: { height: 7, borderRadius: 4, backgroundColor: t.track, overflow: "hidden" }, fill: { height: 7, borderRadius: 4 }, helper: { color: t.muted, fontSize: 13, lineHeight: 19 }, sync: { backgroundColor: t.successSoft, padding: 17, borderRadius: 18, gap: 7 }, syncTitle: { color: t.success, fontWeight: "800", fontSize: 16 }, syncText: { color: t.successText, fontSize: 13, lineHeight: 19 },
});
