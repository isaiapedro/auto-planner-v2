import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type PressableProps, type StyleProp, type TextStyle, type ViewStyle } from "react-native";

import { colors, control, elevation, radius, spacing, type } from "../../theme";

export function Screen({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Card({ children, style, raised = false }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; raised?: boolean }) {
  return <View style={[styles.card, raised && elevation.raised, style]}>{children}</View>;
}

export function SectionHeader({ eyebrow, title }: { eyebrow?: string; title: string }) {
  return <View style={styles.sectionHeader}>{eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}<Text style={styles.sectionTitle}>{title}</Text></View>;
}

type ButtonProps = PressableProps & { label: string; loading?: boolean; style?: StyleProp<ViewStyle>; textStyle?: StyleProp<TextStyle> };
function Button({ kind, label, loading, style, textStyle, disabled, ...props }: ButtonProps & { kind: "primary" | "secondary" | "text" }) {
  const isDisabled = disabled || loading;
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: isDisabled, busy: loading }} disabled={isDisabled} style={({ pressed }) => [styles.button, styles[kind], isDisabled && styles.disabled, pressed && !isDisabled && styles.pressed, style]} {...props}>
    {loading ? <ActivityIndicator color={kind === "primary" ? colors.inverse : colors.primary} /> : <Text style={[styles.buttonText, kind === "primary" ? styles.primaryText : styles.secondaryText, textStyle]}>{label}</Text>}
  </Pressable>;
}
export function PrimaryButton(props: Omit<ButtonProps, "children">) { return <Button kind="primary" {...props} />; }
export function SecondaryButton(props: Omit<ButtonProps, "children">) { return <Button kind="secondary" {...props} />; }
export function TextButton(props: Omit<ButtonProps, "children">) { return <Button kind="text" {...props} />; }

export function StatusPill({ label, tone = "info" }: { label: string; tone?: "success" | "warning" | "info" }) {
  const palette = tone === "success" ? styles.successPill : tone === "warning" ? styles.warningPill : styles.infoPill;
  const labelStyle = tone === "success" ? styles.successLabel : tone === "warning" ? styles.warningLabel : styles.infoLabel;
  return <View accessibilityLabel={`Status: ${label}`} style={[styles.pill, palette]}><Text style={[styles.pillLabel, labelStyle]}>{label}</Text></View>;
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return <Card style={styles.state}><Text style={styles.stateTitle}>{title}</Text><Text style={styles.stateBody}>{body}</Text>{action}</Card>;
}
export function ErrorState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return <View accessibilityRole="alert" style={styles.error}><Text style={styles.errorTitle}>{title}</Text><Text style={styles.errorBody}>{body}</Text>{action}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.canvas },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  sectionHeader: { gap: spacing.xs }, eyebrow: { ...type.eyebrow, color: colors.muted }, sectionTitle: { ...type.title, color: colors.ink },
  button: { minHeight: control.minHeight, borderRadius: radius.md, paddingHorizontal: spacing.md, alignItems: "center", justifyContent: "center", flexDirection: "row" }, primary: { backgroundColor: colors.primary }, secondary: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, text: { backgroundColor: "transparent", alignSelf: "flex-start", minHeight: 40, paddingHorizontal: 0 }, pressed: { opacity: 0.8 }, disabled: { opacity: 0.55 }, buttonText: { fontSize: 15, fontWeight: "800" }, primaryText: { color: colors.inverse }, secondaryText: { color: colors.primary },
  pill: { borderRadius: radius.pill, paddingHorizontal: spacing.xs, paddingVertical: spacing.xxs }, pillLabel: { fontSize: 10, fontWeight: "800", textTransform: "capitalize" }, successPill: { backgroundColor: colors.successSoft }, warningPill: { backgroundColor: colors.warningSoft }, infoPill: { backgroundColor: colors.primarySoft }, successLabel: { color: colors.success }, warningLabel: { color: colors.warning }, infoLabel: { color: colors.primary },
  state: { gap: spacing.xs, alignItems: "flex-start" }, stateTitle: { color: colors.ink, fontSize: 17, fontWeight: "800" }, stateBody: { ...type.caption, color: colors.muted },
  error: { backgroundColor: colors.warningSoft, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.xs }, errorTitle: { color: colors.warning, fontSize: 16, fontWeight: "800" }, errorBody: { ...type.caption, color: colors.warningText },
});
