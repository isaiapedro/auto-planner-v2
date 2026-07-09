import { Platform } from 'react-native';

// Fallback IP depending on the OS platform running the app
const DEFAULT_API_URL = Platform.select({
  ios: 'http://localhost:8000',
  android: 'http://10.0.2.2:8000',
  default: 'http://localhost:8000',
});

export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_URL;
export const POLL_INTERVAL_MS = 2000;   
export const POLL_MAX_ATTEMPTS = 60;
