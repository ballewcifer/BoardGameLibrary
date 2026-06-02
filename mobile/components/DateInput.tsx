/**
 * DateInput — taps open a native calendar picker.
 * Returns YYYY-MM-DD strings to match the rest of the app.
 */
import { useState } from 'react';
import { TouchableOpacity, Text, View, StyleSheet, Platform, Modal } from 'react-native';
import DateTimePicker, { DateTimePickerEvent } from '@react-native-community/datetimepicker';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  value: string;           // YYYY-MM-DD or ''
  onChange: (date: string) => void;
  placeholder?: string;
  nullable?: boolean;      // show a "Clear" option
}

function parseDate(s: string): Date {
  if (!s) return new Date();
  // Parse as local date to avoid UTC off-by-one
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dy = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dy}`;
}

export default function DateInput({ value, onChange, placeholder = 'Select date…', nullable = false }: Props) {
  const [show, setShow] = useState(false);

  const handleChange = (_: DateTimePickerEvent, selected?: Date) => {
    // Android: picker auto-dismisses; iOS: keep open until user is done
    if (Platform.OS === 'android') setShow(false);
    if (selected) onChange(formatDate(selected));
  };

  return (
    <View style={s.wrap}>
      <TouchableOpacity style={s.btn} onPress={() => setShow(true)} activeOpacity={0.7}>
        <Ionicons name="calendar-outline" size={16} color="#9e9e9e" style={{ marginRight: 6 }} />
        <Text style={value ? s.value : s.placeholder}>
          {value || placeholder}
        </Text>
      </TouchableOpacity>

      {nullable && value ? (
        <TouchableOpacity style={s.clearBtn} onPress={() => onChange('')}>
          <Ionicons name="close-circle" size={18} color="#9e9e9e" />
        </TouchableOpacity>
      ) : null}

      {show && Platform.OS === 'android' && (
        <DateTimePicker
          value={parseDate(value)}
          mode="date"
          display="calendar"
          onChange={handleChange}
        />
      )}

      {/* iOS: wrap in Modal so it appears as a bottom sheet */}
      {show && Platform.OS === 'ios' && (
        <Modal transparent animationType="slide">
          <TouchableOpacity style={s.iosOverlay} activeOpacity={1} onPress={() => setShow(false)} />
          <View style={s.iosSheet}>
            <View style={s.iosHeader}>
              <TouchableOpacity onPress={() => setShow(false)}>
                <Text style={s.iosDone}>Done</Text>
              </TouchableOpacity>
            </View>
            <DateTimePicker
              value={parseDate(value)}
              mode="date"
              display="spinner"
              onChange={handleChange}
              style={{ height: 200 }}
            />
          </View>
        </Modal>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  wrap:       { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  btn:        { flex: 1, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, backgroundColor: '#fff' },
  value:      { fontSize: 15, color: '#333' },
  placeholder:{ fontSize: 15, color: '#aaa' },
  clearBtn:   { paddingLeft: 8 },
  iosOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.3)' },
  iosSheet:   { backgroundColor: '#fff', borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  iosHeader:  { padding: 14, alignItems: 'flex-end', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  iosDone:    { color: '#1a237e', fontWeight: '700', fontSize: 16 },
});
