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

const DS = {
  navy900: '#0E2A47',
  navy800: '#13395F',
  navy700: '#1B4B79',
  blue600: '#1366C9',
  blue700: '#0F52A3',
  blue800: '#0B3F80',
  blue050: '#E7F0FB',
  ink900:  '#16202B',
  ink600:  '#51606E',
  ink500:  '#6B7785',
  line200: '#D9E0E7',
  line100: '#EAEEF2',
  surface: '#FFFFFF',
  bg:      '#F4F6F8',
  dangerText: '#B3261E',
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

interface Props {
  users: User[];
  value: string;
  onChange: (v: string) => void;
  label?: string;
}

export default function PlayerPicker({ users, value, onChange, label = 'Players' }: Props) {
  const [open, setOpen]     = useState(false);
  const [custom, setCustom] = useState('');

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
      <TouchableOpacity
        style={s.trigger}
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={`Select players, currently: ${value || 'none selected'}`}
      >
        <View style={{ flex: 1 }}>
          {value
            ? <Text style={s.triggerTxt}>{value}</Text>
            : <Text style={s.placeholder}>Tap to select players…</Text>}
        </View>
        <Ionicons name="people" size={18} color={DS.ink500} />
      </TouchableOpacity>

      <Modal
        visible={open}
        transparent
        animationType="slide"
        onRequestClose={() => setOpen(false)}
        accessibilityViewIsModal={true}
      >
        <Pressable style={s.overlay} onPress={() => setOpen(false)} />
        <View style={s.sheet}>
          <View style={s.grab} />
          <View style={s.sheetHeader}>
            <Text style={s.sheetTitle}>{label}</Text>
            {selected.size > 0 && (
              <TouchableOpacity
                onPress={clear}
                accessibilityRole="button"
                accessibilityLabel="Clear all selected players"
              >
                <Text style={s.clearTxt}>Clear all</Text>
              </TouchableOpacity>
            )}
          </View>

          {users.length > 0 && (
            <FlatList
              data={users}
              keyExtractor={u => String(u.id)}
              style={{ maxHeight: 260 }}
              renderItem={({ item: u }) => {
                const name = `${u.first_name} ${u.last_name}`;
                const checked = selected.has(name);
                return (
                  <TouchableOpacity
                    style={s.row}
                    onPress={() => toggle(name)}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked }}
                    accessibilityLabel={name}
                  >
                    <View style={[s.checkbox, checked && s.checkboxChecked]}>
                      {checked && <Ionicons name="checkmark" size={14} color={DS.surface} />}
                    </View>
                    <Text style={s.rowTxt}>{name}</Text>
                  </TouchableOpacity>
                );
              }}
              ItemSeparatorComponent={() => <View style={s.sep} />}
            />
          )}

          <View style={s.customRow}>
            <TextInput
              style={s.customInput}
              value={custom}
              onChangeText={setCustom}
              placeholder="Add custom name…"
              placeholderTextColor={DS.ink500}
              returnKeyType="done"
              onSubmitEditing={addCustom}
            />
            <TouchableOpacity
              style={s.addBtn}
              onPress={addCustom}
              accessibilityRole="button"
              accessibilityLabel="Add custom player name"
            >
              <Ionicons name="add" size={20} color={DS.surface} />
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={s.doneBtn}
            onPress={() => setOpen(false)}
            accessibilityRole="button"
            accessibilityLabel={`Done, ${selected.size} player${selected.size !== 1 ? 's' : ''} selected`}
          >
            <Text style={s.doneBtnTxt}>Done  ({selected.size} selected)</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  trigger: {
    borderWidth: 1,
    borderColor: DS.line200,
    borderRadius: R.md,
    paddingVertical: SP.md,
    paddingHorizontal: SP.lg,
    marginBottom: SP.md,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: DS.surface,
  },
  triggerTxt: {
    fontSize: 15,
    color: DS.ink900,
    flex: 1,
  },
  placeholder: {
    fontSize: 15,
    color: DS.ink500,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(11,26,42,0.35)',
  },
  sheet: {
    backgroundColor: DS.surface,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: DS.line200,
    paddingHorizontal: SP.lg,
    paddingBottom: SP.xxxl,
    paddingTop: SP.sm,
  },
  grab: {
    width: 40,
    height: 5,
    backgroundColor: DS.line200,
    borderRadius: R.pill,
    alignSelf: 'center',
    marginBottom: SP.md,
  },
  sheetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SP.md,
  },
  sheetTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: DS.ink900,
  },
  clearTxt: {
    fontSize: 13,
    color: DS.dangerText,
    fontWeight: '600',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SP.md,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: R.sm,
    borderWidth: 2,
    borderColor: DS.line200,
    marginRight: SP.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: DS.surface,
  },
  checkboxChecked: {
    backgroundColor: DS.blue600,
    borderColor: DS.blue600,
  },
  rowTxt: {
    fontSize: 15,
    color: DS.ink900,
  },
  sep: {
    height: 1,
    backgroundColor: DS.line100,
  },
  customRow: {
    flexDirection: 'row',
    gap: SP.sm,
    marginTop: SP.md,
  },
  customInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: DS.line200,
    borderRadius: R.md,
    paddingVertical: SP.md,
    paddingHorizontal: SP.lg,
    fontSize: 15,
    color: DS.ink900,
    backgroundColor: DS.bg,
  },
  addBtn: {
    backgroundColor: DS.blue600,
    borderRadius: R.md,
    paddingHorizontal: SP.lg,
    justifyContent: 'center',
  },
  doneBtn: {
    backgroundColor: DS.blue600,
    borderRadius: R.md,
    padding: SP.lg,
    alignItems: 'center',
    marginTop: SP.md,
  },
  doneBtnTxt: {
    color: DS.surface,
    fontWeight: '700',
    fontSize: 15,
  },
});
