import type { TextStyle, ViewStyle } from "react-native";

/**
 * Planner's small, semantic visual contract.  Screens should compose these
 * roles instead of introducing literal palette values or control geometry.
 */
export const colors = {
  canvas: "#f4f6fb",
  surface: "#ffffff",
  surfaceRaised: "#ffffff",
  ink: "#172033",
  muted: "#68738a",
  border: "#e6e9f2",
  primary: "#5b5bd6",
  primarySoft: "#eeedff",
  success: "#237b66",
  successSoft: "#e5f5ef",
  warning: "#a96100",
  warningSoft: "#fff2d9",
  danger: "#b42318",
  dangerSoft: "#feeceb",
  info: "#456a9e",
  infoSoft: "#eaf1fa",
  inverse: "#ffffff",
  inverseSurface: "#172033",
  inverseMuted: "#a6b4d0",
  inverseBorder: "#40506a",
  primaryText: "#3d3a8e",
  successText: "#4b6f65",
  warningText: "#805417",
  track: "#edf0f6",
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
  raised: { shadowColor: "#172033", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 2 } satisfies ViewStyle,
} as const;
