import Constants from "expo-constants";
import { Platform } from "react-native";

function platformFallback(): string {
  return (
    Platform.select({
      ios: "http://localhost:8000",
      android: "http://10.0.2.2:8000",
      default: "http://localhost:8000",
    }) ?? "http://localhost:8000"
  );
}

function devServerHost(): string | null {
  const debuggerHost =
    Constants.expoGoConfig?.debuggerHost ??
    Constants.expoConfig?.hostUri?.split(":")[0] ??
    null;
  if (!debuggerHost) return null;
  return debuggerHost.split(":")[0];
}

function isConfiguredApiUrl(value: string | undefined): value is string {
  if (!value?.trim()) return false;
  if (value.includes("YOUR_LAN_IP") || value.includes("<") || value.includes(">")) {
    return false;
  }
  return true;
}

function normalizedApiUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function configuredApiUrls(): string[] {
  const candidates = [
    ...(process.env.EXPO_PUBLIC_API_URLS?.split(",") ?? []),
    process.env.EXPO_PUBLIC_API_URL,
  ];
  return [...new Set(candidates.filter(isConfiguredApiUrl).map(normalizedApiUrl))];
}

function resolveApiBaseUrls(): string[] {
  const configured = configuredApiUrls();
  if (configured.length > 0) {
    return configured;
  }
  const host = devServerHost();
  if (host) {
    return [`http://${host}:8000`];
  }
  return [platformFallback()];
}

/** Ordered LAN endpoints. The client health-checks these before each uncached request. */
export const API_BASE_URLS = resolveApiBaseUrls();
export const API_TOKEN = process.env.EXPO_PUBLIC_PIOS_API_TOKEN?.trim() ?? "";
