/**
 * PlayerPicker — select existing members and/or type custom names.
 * Returns a comma-separated string of player names.
 */
import { useState } from 'react';
import {
  View, Text, TouchableOpacity, Modal, Pressable, TextInput,
  FlatList, StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { User } from '../lib/types';

const NAVY = '#1a237e';

interface Props {
  users: User[];
  value: string;           // comma-separated current value
  onChange: (v: string) => void;
  label?: string;
}

export default function PlayerPicker({ users, value, onChange, label = 'Players' }: Props) {
  const [open, setOpen]         = useState(false);
  const [custom, setCustom]     = useState('');

  // Parse current selections into a Set
  const selected = new Set(
    value.split(',').map(s => s.trim()).filter(Boolean)
  );

  const toggle = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange([...next].join(', '));
  };

  const addCustom = () => {
    const name = custom.trim();
    if (!name) return;
    const next = new Set(selected);
    next.add(name);
    onChange([...next].join(', '));
    setCustom('');
  };

  const clear = () => onChange('');

  return (
    <>
      <TouchableOpacity style={s.trigger} onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel={`Select players, currently: ${value || 'none selected'}`}>
        <View style={{ flex: 1 }}>
          {value
            ? <Text style={s.triggerTxt}>{value}</Text>
            : <Text style={s.placeholder}>Tap to select players…</Text>}
        </View>
        <Ionicons name="people" size={18} color="#9e9e9e" />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetHeader}>
            <Text style={s.sheetTitle}>{label}</Text>
            {selected.size > 0 && (
              <TouchableOpacity onPress={clear} accessibilityRole="button" accessibilityLabel="Clear all selected players">
                <Text style={s.clearTxt}>Clear all</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Member list */}
          {users.length > 0 && (
            <FlatList
              data={users}
              keyExtractor={u => String(u.id)}
              style={{ maxHeight: 260 }}
              renderItem={({ item: u }) => {
                const name = `${u.first_name} ${u.last_name}`;
                const checked = selected.has(name);
                return (
                  <TouchableOpacity style={s.row} onPress={() => toggle(name)} accessibilityRole="checkbox" accessibilityState={{ checked }} accessibilityLabel={name}>
                    <View style={[s.checkbox, checked && s.checkboxChecked]}>
                      {checked && <Ionicons name="checkmark" size={14} color="#fff" />}
                    </View>
                    <Text style={s.rowTxt}>{name}</Text>
                  </TouchableOpacity>
                );
              }}
              ItemSeparatorComponent={() => <View style={s.sep} />}
            />
          )}

          {/* Custom name entry */}
          <View style={s.customRow}>
            <TextInput
              style={s.customInput}
              value={custom}
              onChangeText={setCustom}
              placeholder="Add custom name…"
              returnKeyType="done"
              onSubmitEditing={addCustom}
            />
            <TouchableOpacity style={s.addBtn} onPress={addCustom} accessibilityRole="button" accessibilityLabel="Add custom player name">
              <Ionicons name="add" size={20} color="#fff" />
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={s.doneBtn} onPress={() => setOpen(false)} accessibilityRole="button" accessibilityLabel={`Done, ${selected.size} player${selected.size !== 1 ? 's' : ''} selected`}>
            <Text style={s.doneBtnTxt}>Done  ({selected.size} selected)</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  trigger: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, marginBottom: 12, flexDirection: 'row', alignItems: 'center' },
  triggerTxt: { fontSize: 15, color: '#333', flex: 1 },
  placeholder: { fontSize: 15, color: '#aaa' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, paddingBottom: 36 },
  sheetHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  sheetTitle: { fontSize: 17, fontWeight: '700', color: NAVY },
  clearTxt: { fontSize: 13, color: '#b71c1c' },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12 },
  checkbox: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: '#d1d5db', marginRight: 12, alignItems: 'center', justifyContent: 'center' },
  checkboxChecked: { backgroundColor: NAVY, borderColor: NAVY },
  rowTxt: { fontSize: 15 },
  sep: { height: 1, backgroundColor: '#f3f4f6' },
  customRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  customInput: { flex: 1, borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15 },
  addBtn: { backgroundColor: NAVY, borderRadius: 8, paddingHorizontal: 14, justifyContent: 'center' },
  doneBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 12 },
  doneBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
