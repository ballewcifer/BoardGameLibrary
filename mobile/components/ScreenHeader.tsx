import { View, Text, StyleSheet } from 'react-native';
import type { ReactNode } from 'react';

const DS = {
  navy900: '#0E2A47',
}

const FONT = {
  title: { fontSize: 17, fontWeight: '700' as const },
}

const SP = { lg: 16 }

export default function ScreenHeader({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <View style={s.header}>
      <Text style={s.title}>{title}</Text>
      {right ? <View style={s.right}>{right}</View> : null}
    </View>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: DS.navy900, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SP.lg, paddingVertical: SP.lg },
  title:  { color: '#fff', ...FONT.title },
  right:  { flexDirection: 'row', alignItems: 'center', gap: 4 },
});
