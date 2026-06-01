import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

const KEY = 'bgl_settings';
const PWD_KEY = 'bgl_bgg_password';

export interface Settings {
  bgg_username: string;
  bgg_token: string;
  bgg_password: string; // runtime only — stored in SecureStore, not AsyncStorage
}

const DEFAULTS: Settings = {
  bgg_username: '',
  bgg_token: 'YOUR_BGG_API_TOKEN_HERE',
  bgg_password: '',
};

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    const base = raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
    // Load password from secure storage
    const pwd = await SecureStore.getItemAsync(PWD_KEY);
    return { ...base, bgg_password: pwd ?? '' };
  } catch {
    return { ...DEFAULTS };
  }
}

export async function saveSettings(s: Settings): Promise<void> {
  const { bgg_password, ...rest } = s;
  await AsyncStorage.setItem(KEY, JSON.stringify(rest));
  // Store password separately in secure storage
  if (bgg_password) {
    await SecureStore.setItemAsync(PWD_KEY, bgg_password);
  } else {
    await SecureStore.deleteItemAsync(PWD_KEY).catch(() => {});
  }
}
