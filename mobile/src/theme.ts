import type { TextStyle, ViewStyle } from "react-native";

/**
 * Planner's small, semantic visual contract.  Screens should compose these
 * roles instead of introducing literal palette values or control geometry.
 */
export const colors = {
  canvas: "#10131a",
  surface: "#191e28",
  surfaceRaised: "#222936",
  ink: "#f3f6fb",
  muted: "#a9b4c7",
  border: "#303949",
  primary: "#aaa8ff",
  primarySoft: "#292846",
  success: "#67d3ad",
  successSoft: "#183a31",
  warning: "#ffc46b",
  warningSoft: "#40331d",
  danger: "#ff8f8a",
  dangerSoft: "#422324",
  info: "#8dbdff",
  infoSoft: "#1d314c",
  inverse: "#ffffff",
  inverseSurface: "#0b0e14",
  inverseMuted: "#b7c2d7",
  inverseBorder: "#3a4557",
  primaryText: "#d7d6ff",
  successText: "#b1ead6",
  warningText: "#ffe1ac",
  track: "#2a3240",
} as const;

export const spacing = { xxs: 4, xs: 8, sm: 12, md: 16, lg: 20, xl: 24, xxl: 32 } as const;
export const radius = { sm: 12, md: 16, lg: 18, xl: 20, hero: 24, pill: 999 } as const;
export const control = { minHeight: 48, icon: 40 } as const;

export const type = {
  eyebrow: { fontSize: 10, fontWeight: "800", letterSpacing: 1.1 } satisfies TextStyle,
  body: { fontSize: 14, lineHeight: 20 } satisfies TextStyle,
  caption: { fontSize: 12, lineHeight: 18 } satisfies TextStyle,
  title: { fontSize: 21, lineHeight: 27, fontWeight: "800", letterSpacing: -0.35 } satisfies TextStyle,
  hero: { fontSize: 28, lineHeight: 34, fontWeight: "800", letterSpacing: -0.7 } satisfies TextStyle,
  numeric: { fontVariant: ["tabular-nums"], fontWeight: "800" } satisfies TextStyle,
} as const;

export const elevation = {
  raised: { shadowColor: "#000000", shadowOpacity: 0.28, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 2 } satisfies ViewStyle,
} as const;
