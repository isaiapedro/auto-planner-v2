/**
 * Schedule view — first-launch wizard launch + weekly block display (task #9 wired).
 */
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { getSchedule } from "../api/client";
import type { RootStackParams } from "../navigation/RootNavigator";

export default function Schedule() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [noSchedule, setNoSchedule] = useState(false);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      getSchedule()
        .then((c) => {
          setConfig(c);
          setNoSchedule(false);
        })
        .catch(() => setNoSchedule(true))
        .finally(() => setLoading(false));
    }, [])
  );

  if (loading) return <ActivityIndicator style={styles.center} />;

  if (noSchedule) {
    return (
      <View style={styles.center}>
        <Text style={styles.wizardTitle}>Set up your schedule</Text>
        <Text style={styles.wizardSub}>
          Define your wake/sleep times, fixed commitments, and goal domains.
        </Text>
        <Pressable style={styles.btn} onPress={() => navigation.navigate("ScheduleWizard")}>
          <Text style={styles.btnText}>Start Wizard</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>Your Schedule</Text>
      <View style={styles.card}>
        <Text style={styles.label}>Sleep</Text>
        <Text style={styles.value}>
          {config?.wake_time} – {config?.sleep_time}
        </Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.label}>Domain Weights</Text>
        {config?.domain_weights &&
          Object.entries(config.domain_weights).map(([domain, weight]) => (
            <Text key={domain} style={styles.row}>
              {domain}: {((weight as number) * 100).toFixed(0)}%
            </Text>
          ))}
      </View>
      <View style={styles.card}>
        <Text style={styles.label}>Fixed Blocks</Text>
        {config?.fixed_blocks?.map((b: any, i: number) => (
          <Text key={i} style={styles.row}>
            {b.title} — {b.days?.join(", ")} @ {b.start} ({b.duration_minutes}min)
          </Text>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: "#f5f5f5" },
  content:     { padding: 16, gap: 12 },
  center:      { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  heading:     { fontSize: 22, fontWeight: "700" },
  card:        { backgroundColor: "#fff", padding: 16, borderRadius: 12 },
  label:       { fontSize: 12, fontWeight: "700", color: "#6366f1",
                 textTransform: "uppercase", marginBottom: 8 },
  value:       { fontSize: 18, fontWeight: "600" },
  row:         { fontSize: 14, color: "#374151", paddingVertical: 2 },
  wizardTitle: { fontSize: 22, fontWeight: "700", textAlign: "center", marginBottom: 8 },
  wizardSub:   { fontSize: 15, color: "#555", textAlign: "center", marginBottom: 24, lineHeight: 22 },
  btn:         { backgroundColor: "#6366f1", paddingHorizontal: 32, paddingVertical: 14,
                 borderRadius: 12 },
  btnText:     { color: "#fff", fontWeight: "700", fontSize: 16 },
});
