/** Read-only rendering of evidence-backed Insights conclusions. */
import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { getCurrentInsights } from "../api/client";
import { ErrorState, Screen } from "../components/ui";
import { colors } from "../theme";
import type { CurrentInsights, ReviewFinding, ScientificSupport } from "../types";

const t = colors;

function Finding({ finding, tone = "default" }: { finding: ReviewFinding; tone?: "default" | "attention" | "positive" }) {
  const accent = tone === "attention" ? t.warning : tone === "positive" ? t.success : t.primary;
  return <View style={s.finding}><View style={[s.findingMark, { backgroundColor: accent }]} /><Text style={s.findingText}>{finding.statement}</Text></View>;
}

function sourceLabel(path: string) {
  return path.split("/").at(-1)?.replace(/\.md$/, "").replaceAll("-", " ") ?? "Local planning-science source";
}

function ScientificOption({ item }: { item: ScientificSupport }) {
  return <View style={s.option}><Text style={s.optionClaim}>{item.claim}</Text><Text style={s.optionApplicability}>{item.applicability}</Text><Text style={s.optionSource}>{sourceLabel(item.source_path)}</Text></View>;
}

function Story({ insight }: { insight: CurrentInsights }) {
  const { routine_review: routine, goal_review: goals, future_plan_review: future, life_pillar_review: pillars } = insight.inference_bundle;
  const findings = useMemo(() => [
    ...routine.worked.map((finding) => ({ finding, tone: "positive" as const })),
    ...routine.did_not_work.map((finding) => ({ finding, tone: "attention" as const })),
    ...future.progress_updates.map((finding) => ({ finding, tone: "positive" as const })),
    ...future.new_additions.map((finding) => ({ finding, tone: "default" as const })),
    ...(future.conflicts ?? []).map(({ statement, evidence_paths, confidence }) => ({ finding: { statement, evidence_paths, confidence }, tone: "attention" as const })),
    ...(future.facilitators ?? []).map(({ statement, evidence_paths, confidence }) => ({ finding: { statement, evidence_paths, confidence }, tone: "positive" as const })),
    ...goals.assessments.flatMap((assessment) => assessment.findings.map((finding) => ({ finding, tone: assessment.status === "at_risk" ? "attention" as const : "default" as const }))),
  ], [future.conflicts, future.facilitators, future.new_additions, future.progress_updates, goals.assessments, routine.did_not_work, routine.worked]);
  const scientificOptions = useMemo(() => [
    ...goals.assessments.flatMap((assessment) => assessment.recommendations),
    ...pillars.groups.flatMap((group) => group.topics.flatMap((topic) => topic.recommendations)),
  ], [goals.assessments, pillars.groups]);
  return <>
    <View style={s.hero}><Text style={s.title}>Insights</Text><Text style={s.goalSummary}>{goals.summary}</Text></View>
    <View style={s.section}><Text style={s.sectionTitle}>Routine</Text><Text style={s.summary}>{routine.summary}</Text></View>
    {findings.length > 0 && <View style={s.section}><Text style={s.sectionTitle}>Key findings</Text>{findings.map(({ finding, tone }, index) => <Finding key={`${finding.statement}-${index}`} finding={finding} tone={tone} />)}</View>}
    {future.summary && <View style={s.section}><Text style={s.summary}>{future.summary}</Text></View>}
    {scientificOptions.length > 0 && <View style={s.section}><Text style={s.sectionTitle}>Evidence-informed options</Text>{scientificOptions.map((item, index) => <ScientificOption key={`${item.source_path}-${index}`} item={item} />)}</View>}
  </>;
}

export default function Insights() {
  const [insight, setInsight] = useState<CurrentInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setInsight(await getCurrentInsights());
    } catch (cause) {
      setInsight(null);
      setError(String(cause));
    } finally {
      setLoading(false);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading) return <Screen style={s.state}><ActivityIndicator color={t.primary} /></Screen>;
  if (error) return <Screen style={s.state}><ErrorState title="Insights are unavailable" body={error} /></Screen>;
  if (insight?.example) return <Screen style={s.state}><Text style={s.empty}>No personal review has been published.</Text></Screen>;
  return insight ? <Screen><ScrollView contentContainerStyle={s.content} showsVerticalScrollIndicator={false}><Story insight={insight} /></ScrollView></Screen> : null;
}

const s = StyleSheet.create({
  content: { padding: 16, paddingBottom: 40, gap: 26 },
  state: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32 },
  hero: { backgroundColor: t.inverseSurface, borderRadius: 20, padding: 22, gap: 10 },
  title: { color: t.inverse, fontSize: 28, fontWeight: "800", letterSpacing: -0.6 },
  goalSummary: { color: t.inverseMuted, fontSize: 16, lineHeight: 23 },
  section: { gap: 10 },
  sectionTitle: { color: t.ink, fontSize: 18, fontWeight: "800", letterSpacing: -0.2 },
  summary: { color: t.ink, fontSize: 15, lineHeight: 22 },
  finding: { flexDirection: "row", gap: 10, backgroundColor: t.surface, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: t.border },
  findingMark: { width: 3, borderRadius: 3, alignSelf: "stretch" },
  findingText: { flex: 1, color: t.ink, fontSize: 14, lineHeight: 20 },
  option: { backgroundColor: t.surfaceRaised, borderRadius: 14, padding: 15, gap: 8 },
  optionClaim: { color: t.ink, fontSize: 15, fontWeight: "700", lineHeight: 21 },
  optionApplicability: { color: t.muted, fontSize: 13, lineHeight: 19 },
  optionSource: { color: t.primaryText, fontSize: 11, fontWeight: "700", textTransform: "capitalize" },
  empty: { color: t.muted, fontSize: 15, textAlign: "center" },
});
