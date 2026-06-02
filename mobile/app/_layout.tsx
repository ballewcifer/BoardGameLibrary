import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { initDb } from '../lib/db';

export default function RootLayout() {
  useEffect(() => {
    initDb();
    // Fix any protocol-relative URLs stored before the https normalisation fix
    import('../lib/db').then(d => d.fixProtocolRelativeUrls());
  }, []);
  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false }} />
    </>
  );
}
