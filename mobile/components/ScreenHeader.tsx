import { View, Text, StyleSheet } from 'react-native';
import type { ReactNode } from 'react';

const NAVY = '#1a237e';

export default function ScreenHeader({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <View style={s.header}>
      <Text style={s.title}>{title}</Text>
      {right ? <View style={s.right}>{right}</View> : null}
    </View>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14 },
  title:  { color: '#fff', fontSize: 20, fontWeight: '700' },
  right:  { flexDirection: 'row', alignItems: 'center', gap: 4 },
});
