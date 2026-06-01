import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'bgl_settings';

export interface Settings {
  bgg_username: string;
}

const DEFAULTS: Settings = { bgg_username: '' };

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch {
    return { ...DEFAULTS };
  }
}

export async function saveSettings(s: Settings): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(s));
}
