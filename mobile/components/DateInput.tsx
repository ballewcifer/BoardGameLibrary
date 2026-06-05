/**
 * DateInput — taps open a native calendar picker.
 * Returns YYYY-MM-DD strings to match the rest of the app.
 */
import { useState } from 'react';
import { TouchableOpacity, Text, View, StyleSheet, Platform, Modal } from 'react-native';
import DateTimePicker, { DateTimePickerEvent } from '@react-native-community/datetimepicker';
import { Ionicons } from '@expo/vector-icons';

// Design tokens
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
  okText:     '#1E6E32', okBg:    '#E6F4EA', okSolid:    '#2E7D32',
  warnText:   '#8A5300', warnBg:  '#FFF3E0', warnSolid:  '#B26A00',
  dangerText: '#B3261E', dangerBg:'#FCEBEA', dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg:  '#E7F0FB',
  starText:   '#B07A00', starFill:'#F2A900',
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

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
        <Ionicons name="calendar-outline" size={16} color={DS.ink500} style={{ marginRight: SP.sm - 2 }} />
        <Text style={value ? s.value : s.placeholder}>
          {value || placeholder}
        </Text>
      </TouchableOpacity>

      {nullable && value ? (
        <TouchableOpacity style={s.clearBtn} onPress={() => onChange('')}>
          <Ionicons name="close-circle" size={18} color={DS.ink500} />
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
  wrap:        { flexDirection: 'row', alignItems: 'center', marginBottom: SP.md },
  btn:         { flex: 1, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md - 2, backgroundColor: DS.surface },
  value:       { fontSize: 14, color: DS.ink900 },
  placeholder: { fontSize: 14, color: DS.ink500 },
  clearBtn:    { paddingLeft: SP.sm },
  iosOverlay:  { flex: 1, backgroundColor: 'rgba(14,42,71,0.35)' },
  iosSheet:    { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18 },
  iosHeader:   { padding: SP.lg - 2, alignItems: 'flex-end', borderBottomWidth: 1, borderBottomColor: DS.line200 },
  iosDone:     { color: DS.blue600, fontWeight: '700', fontSize: 15 },
});
