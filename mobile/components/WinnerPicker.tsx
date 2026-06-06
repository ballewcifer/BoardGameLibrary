/**
 * WinnerPicker — choose the winner from the players already listed for a play.
 * Reads the same comma-separated string PlayerPicker produces, and offers each
 * listed player plus "All" (co-op win) and "None" (clear). Single-select.
 */
import { useState } from 'react';
import { View, Text, TouchableOpacity, Modal, Pressable, FlatList, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const DS = {
  blue600: '#1366C9',
  ink900:  '#16202B',
  ink500:  '#6B7785',
  line200: '#D9E0E7',
  line100: '#EAEEF2',
  surface: '#FFFFFF',
};
const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

interface Props {
  players: string;              // comma-separated names (from PlayerPicker)
  value: string;                // current winner
  onChange: (v: string) => void;
}

export default function WinnerPicker({ players, value, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const names = players.split(',').map(s => s.trim()).filter(Boolean);
  // Player names + "All"; surface a pre-existing custom value if it isn't a listed player
  const options = [...names, 'All'];
  if (value && value !== 'All' && !names.includes(value)) options.unshift(value);

  const pick = (name: string) => { onChange(name); setOpen(false); };

  const label = (o: string) => (o === 'All' ? 'All (everyone won)' : o);

  return (
    <>
      <TouchableOpacity
        style={s.trigger}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={`Winner, currently ${value || 'none selected'}`}
      >
        {value
          ? <Text style={s.triggerTxt}>{label(value)}</Text>
          : <Text style={s.placeholder}>Tap to choose winner…</Text>}
        <Ionicons name="chevron-down" size={16} color={DS.ink500} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setOpen(false)} />
        <View style={s.sheet}>
          <View style={s.grab} />
          <Text style={s.sheetTitle}>Winner</Text>
          {names.length === 0 && (
            <Text style={s.hint}>Tip: add players above first to pick from them.</Text>
          )}
          <FlatList
            data={options}
            keyExtractor={(o, i) => `${o}-${i}`}
            style={{ maxHeight: 320 }}
            renderItem={({ item: o }) => {
              const selected = value === o;
              return (
                <TouchableOpacity style={s.row} onPress={() => pick(o)} accessibilityRole="button" accessibilityState={{ selected }} accessibilityLabel={label(o)}>
                  <Text style={s.rowTxt}>{label(o)}</Text>
                  {selected && <Ionicons name="checkmark" size={18} color={DS.blue600} />}
                </TouchableOpacity>
              );
            }}
            ItemSeparatorComponent={() => <View style={s.sep} />}
          />
          {/* Clear / no winner */}
          <TouchableOpacity style={s.clearRow} onPress={() => pick('')} accessibilityRole="button" accessibilityLabel="No winner (clear)">
            <Text style={s.clearTxt}>None / no winner</Text>
            {!value && <Ionicons name="checkmark" size={18} color={DS.blue600} />}
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  trigger:     { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, marginBottom: SP.md, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: DS.surface },
  triggerTxt:  { fontSize: 15, color: DS.ink900, flex: 1 },
  placeholder: { fontSize: 15, color: DS.ink500, flex: 1 },
  overlay:     { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },
  sheet:       { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, paddingHorizontal: SP.lg, paddingTop: SP.sm, paddingBottom: SP.xxxl },
  grab:        { width: 40, height: 5, backgroundColor: DS.line200, borderRadius: R.pill, alignSelf: 'center', marginBottom: SP.md },
  sheetTitle:  { fontSize: 17, fontWeight: '700', color: DS.ink900, marginBottom: SP.md },
  hint:        { fontSize: 12, color: DS.ink500, fontStyle: 'italic', marginBottom: SP.sm },
  row:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: SP.md },
  rowTxt:      { fontSize: 15, color: DS.ink900 },
  sep:         { height: 1, backgroundColor: DS.line100 },
  clearRow:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: SP.md, marginTop: SP.xs, borderTopWidth: 1, borderTopColor: DS.line100 },
  clearTxt:    { fontSize: 15, color: DS.ink500 },
});
