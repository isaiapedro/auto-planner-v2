/** Privacy-safe review queue for account-triage proposals. */
import { useFocusEffect } from "@react-navigation/native";
import React, { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Alert, FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { acceptAccountProposal, dismissAccountProposal, getAccountProposals, getAccountProposalsByStatus, getAccountRuns } from "../api/client";
import { EmptyState, ErrorState, PrimaryButton, Screen, SecondaryButton, StatusPill } from "../components/ui";
import { colors } from "../theme";
import type { AccountProposal, AccountTriageRun } from "../types";

const t = colors;

function when(iso: string) {
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? "Recently" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(value);
}

function label(value: string) { return value.replaceAll("_", " "); }

function destinationLabel(target: string) {
  const labels: Record<string, string> = {
    personal_planner: "Planner", personal_career_strategy: "Career strategy", personal_finance: "Finance", knowledge_technology: "Knowledge · Technology",
  };
  return labels[target] ?? label(target);
}

function confidenceTone(value: AccountProposal["confidence"]): "info" | "success" | "warning" {
  return value === "high" ? "success" : value === "low" || value === "none" ? "warning" : "info";
}

function outcomeTone(status: AccountProposal["status"]): "info" | "success" | "warning" {
  return status === "accepted" ? "success" : status === "dismissed" || status === "failed" ? "warning" : "info";
}

function auditStatus(run: AccountTriageRun) {
  if (run.fallback_used || run.status === "needs_manual_review") return "Manual review";
  return run.used_llm ? "Local synthesis" : "Review ready";
}

export default function Inbox() {
  const [proposals, setProposals] = useState<AccountProposal[]>([]);
  const [outcomes, setOutcomes] = useState<AccountProposal[]>([]);
  const [runs, setRuns] = useState<AccountTriageRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    try {
      const [open, accepted, dismissed, accountRuns] = await Promise.all([
        getAccountProposals(), getAccountProposalsByStatus("accepted"), getAccountProposalsByStatus("dismissed"), getAccountRuns(),
      ]);
      setProposals(open.proposals);
      setOutcomes([...accepted, ...dismissed].sort((left, right) => new Date(right.resolved_at ?? right.created_at).getTime() - new Date(left.resolved_at ?? left.created_at).getTime()));
      setRuns([...accountRuns].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the account inbox.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const open = useMemo(() => proposals.filter((proposal) => proposal.status === "proposed"), [proposals]);
  const recentOutcomes = useMemo(() => outcomes.slice(0, 8), [outcomes]);
  const update = useCallback(async (proposal: AccountProposal, action: "accept" | "dismiss") => {
    setActingId(proposal.id);
    try {
      const updated = action === "accept" ? await acceptAccountProposal(proposal.id) : await dismissAccountProposal(proposal.id);
      setProposals((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) {
      Alert.alert("Could not update proposal", cause instanceof Error ? cause.message : "Please try again.");
    } finally {
      setActingId(null);
    }
  }, []);
  const confirm = useCallback((proposal: AccountProposal, action: "accept" | "dismiss") => {
    const accepting = action === "accept";
    Alert.alert(
      accepting ? "Accept this proposal?" : "Dismiss this proposal?",
      accepting
        ? "This will create the approved follow-up in its declared destination."
        : "This removes it from your active review queue. The private audit record remains intact.",
      [{ text: "Cancel", style: "cancel" }, { text: accepting ? "Accept" : "Dismiss", style: accepting ? "default" : "destructive", onPress: () => update(proposal, action) }],
    );
  }, [update]);

  if (loading) return <Screen style={s.state}><ActivityIndicator color={t.primary} /><Text style={s.muted}>Loading your review queue…</Text></Screen>;

  return <Screen>
    <FlatList
      data={open}
      keyExtractor={(proposal) => proposal.id}
      contentContainerStyle={s.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={t.primary} />}
      ListHeaderComponent={<View style={s.header}><Text style={s.eyebrow}>ACCOUNT REVIEW</Text><Text style={s.title}>Inbox</Text><Text style={s.subtitle}>Review suggested follow-ups before anything is created. Evidence stays private and is never shown here.</Text>{error ? <ErrorState title="Inbox is unavailable" body="Pull down to reload account-review metadata." /> : null}</View>}
      ListEmptyComponent={<EmptyState title="Nothing to review" body="When you run account triage, proposed notes, research questions, and project follow-ups will appear here." />}
      renderItem={({ item }) => <View style={s.card}>
        <View style={s.cardTop}><View style={s.grow}><Text style={s.target}>{destinationLabel(item.target)}</Text><Text style={s.cardTitle}>{item.title}</Text></View><StatusPill label={label(item.confidence)} tone={confidenceTone(item.confidence)} /></View>
        <Text style={s.summary}>{item.summary}</Text>
        <View style={s.meta}><Text style={s.metaText}>{label(item.kind)}</Text><Text style={s.metaText}>{when(item.created_at)}</Text></View>
        <Text style={s.notice}>{item.requires_confirmation ? "Requires your confirmation" : "Ready for review"}</Text>
        <View style={s.actions}><SecondaryButton label="Dismiss" disabled={actingId === item.id} onPress={() => confirm(item, "dismiss")} style={s.dismiss} /><PrimaryButton label={actingId === item.id ? "Saving…" : "Accept"} loading={actingId === item.id} disabled={actingId === item.id} onPress={() => confirm(item, "accept")} style={s.accept} /></View>
      </View>}
      ListFooterComponent={<View style={s.audit}>
        <View style={s.auditHeader}><Text style={s.eyebrow}>PRIVATE ACTIVITY</Text><Text style={s.auditTitle}>Account timeline</Text><Text style={s.auditSubtitle}>Operational metadata only—no memo contents, evidence, paths, or raw errors.</Text></View>
        {runs.length === 0 ? <EmptyState title="No review activity yet" body="Run an account review from Memos to create a private, traceable timeline." /> : runs.slice(0, 12).map((run) => <View key={run.id} style={s.auditCard}>
          <View style={s.cardTop}><View style={s.grow}><Text style={s.auditLabel}>{auditStatus(run)}</Text><Text style={s.auditValue}>{run.proposal_ids.length} {run.proposal_ids.length === 1 ? "follow-up" : "follow-ups"} assessed</Text></View><StatusPill label={run.status === "completed" ? "complete" : "review"} tone={run.status === "completed" ? "success" : "warning"} /></View>
          <View style={s.meta}><Text style={s.metaText}>{when(run.completed_at ?? run.created_at)}</Text>{run.model_label ? <Text style={s.metaText}>{run.model_label}</Text> : null}{run.fallback_used || run.status === "needs_manual_review" ? <Text style={s.metaText}>Fallback used</Text> : null}</View>
        </View>)}
        {recentOutcomes.length ? <View style={s.outcomes}><Text style={s.auditTitle}>Recent outcomes</Text>{recentOutcomes.map((proposal) => <View key={proposal.id} style={s.outcome}><View style={s.grow}><Text style={s.target}>{destinationLabel(proposal.target)}</Text><Text style={s.outcomeTitle} numberOfLines={1}>{proposal.title}</Text><Text style={s.metaText}>{when(proposal.resolved_at ?? proposal.created_at)}</Text></View><StatusPill label={label(proposal.status)} tone={outcomeTone(proposal.status)} /></View>)}</View> : null}
      </View>}
    />
  </Screen>;
}

const s = StyleSheet.create({
  state: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 }, muted: { color: t.muted }, content: { padding: 16, paddingBottom: 34, gap: 12 },
  header: { paddingVertical: 8, gap: 7, marginBottom: 4 }, eyebrow: { color: t.primary, fontSize: 10, fontWeight: "800", letterSpacing: 1.1 }, title: { color: t.ink, fontSize: 30, fontWeight: "800", letterSpacing: -0.6 }, subtitle: { color: t.muted, fontSize: 14, lineHeight: 20 },
  card: { backgroundColor: t.surface, borderRadius: 18, padding: 16, borderWidth: 1, borderColor: t.border, gap: 11 }, cardTop: { flexDirection: "row", gap: 12, alignItems: "flex-start" }, grow: { flex: 1 }, target: { color: t.primary, fontSize: 11, lineHeight: 16, fontWeight: "800", textTransform: "uppercase", letterSpacing: 0.5 }, cardTitle: { color: t.ink, fontSize: 17, lineHeight: 22, fontWeight: "800", marginTop: 2 }, summary: { color: t.ink, fontSize: 14, lineHeight: 20 }, meta: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, metaText: { color: t.muted, fontSize: 11, textTransform: "capitalize" }, notice: { color: t.primaryText, fontSize: 12, fontWeight: "700", backgroundColor: t.primarySoft, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 }, actions: { flexDirection: "row", gap: 10 }, dismiss: { flex: 1 }, accept: { flex: 1 },
  audit: { gap: 12, marginTop: 28, paddingBottom: 16 }, auditHeader: { gap: 5 }, auditTitle: { color: t.ink, fontSize: 18, fontWeight: "800" }, auditSubtitle: { color: t.muted, fontSize: 13, lineHeight: 19 }, auditCard: { backgroundColor: t.primarySoft, borderRadius: 16, padding: 14, gap: 8, borderWidth: 1, borderColor: t.border }, auditLabel: { color: t.primaryText, fontSize: 11, fontWeight: "800", textTransform: "uppercase", letterSpacing: 0.5 }, auditValue: { color: t.ink, fontSize: 15, fontWeight: "800", marginTop: 2 }, outcomes: { gap: 8, marginTop: 8 }, outcome: { backgroundColor: t.surface, borderRadius: 14, padding: 13, borderWidth: 1, borderColor: t.border, flexDirection: "row", gap: 12, alignItems: "flex-start" }, outcomeTitle: { color: t.ink, fontSize: 14, fontWeight: "800", marginVertical: 2 },
});
