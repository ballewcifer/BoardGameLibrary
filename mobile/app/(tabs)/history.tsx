import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, Alert, Modal, TextInput, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Loan } from '../../lib/types';
import ScreenHeader from '../../components/ScreenHeader';
import DateInput from '../../components/DateInput';

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
  okText:     '#1E6E32', okBg:   '#E6F4EA', okSolid:   '#2E7D32',
  warnText:   '#8A5300', warnBg: '#FFF3E0', warnSolid: '#B26A00',
  dangerText: '#B3261E', dangerBg:'#FCEBEA',dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg: '#E7F0FB',
  starText:   '#B07A00', starFill:'#F2A900',
};

const FONT = {
  display:   { fontSize: 22, fontWeight: '700' as const },
  title:     { fontSize: 17, fontWeight: '700' as const },
  cardTitle: { fontSize: 15, fontWeight: '700' as const },
  body:      { fontSize: 14, fontWeight: '400' as const },
  bodyBold:  { fontSize: 14, fontWeight: '700' as const },
  label:     { fontSize: 11, fontWeight: '700' as const, textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  caption:   { fontSize: 12, fontWeight: '400' as const },
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

export default function History({ isActive = true }: { isActive?: boolean }) {
  const [loans, setLoans]           = useState<Loan[]>([]);
  const [filter, setFilter]         = useState<'all' | 'active' | 'returned'>('all');
  const [refreshing, setRefreshing] = useState(false);
  const [editingLoan, setEditingLoan] = useState<Loan | null>(null);

  const [editOut,   setEditOut]   = useState('');
  const [editRet,   setEditRet]   = useState('');
  const [editDue,   setEditDue]   = useState('');
  const [editNotes, setEditNotes] = useState('');

  const load = useCallback(() => setLoans(db.loanHistory()), []);
  useEffect(() => { if (isActive) load(); }, [isActive]);

  const returnNow = (loan: Loan) => {
    Alert.alert('Mark as returned?', `Return "${loan.game_name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Return', onPress: () => {
        db.getDb().runSync('UPDATE loans SET returned_at = ? WHERE id = ?', [db.nowIso(), loan.id]);
        load();
      }},
    ]);
  };

  const openEdit = (loan: Loan) => {
    setEditingLoan(loan);
    setEditOut(loan.checked_out_at?.slice(0, 16).replace('T', ' ') ?? '');
    setEditRet(loan.returned_at?.slice(0, 16).replace('T', ' ')  ?? '');
    setEditDue(loan.due_date ?? '');
    setEditNotes(loan.notes ?? '');
  };

  const saveEdit = () => {
    if (!editingLoan || !editOut.trim()) {
      Alert.alert('Checked-out date is required.');
      return;
    }
    db.getDb().runSync(
      'UPDATE loans SET checked_out_at=?, returned_at=?, due_date=?, notes=? WHERE id=?',
      [
        editOut.trim(),
        editRet.trim() || null,
        editDue.trim() || null,
        editNotes.trim() || null,
        editingLoan.id,
      ]
    );
    setEditingLoan(null);
    load();
  };

  const setNow = (setter: (v: string) => void) => {
    setter(new Date().toISOString().slice(0, 16).replace('T', ' '));
  };

  const today = new Date().toISOString().slice(0, 10);

  const filtered = loans.filter(l => {
    if (filter === 'active')   return !l.returned_at;
    if (filter === 'returned') return !!l.returned_at;
    return true;
  });

  return (
    <View style={s.container}>
      <ScreenHeader title="History" />

      <View style={s.filterRow}>
        {(['all', 'active', 'returned'] as const).map(f => (
          <TouchableOpacity
            key={f}
            style={[s.filterBtn, filter === f && s.filterBtnActive]}
            onPress={() => setFilter(f)}
            accessibilityRole="button"
            accessibilityLabel={f === 'all' ? 'Show all checkouts' : f === 'active' ? 'Show still out' : 'Show returned'}
            accessibilityState={{ selected: filter === f }}
          >
            <Text style={[s.filterTxt, filter === f && s.filterTxtActive]}>
              {f === 'all' ? 'All' : f === 'active' ? 'Still Out' : 'Returned'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={filtered}
        keyExtractor={l => String(l.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
        contentContainerStyle={{ padding: SP.md }}
        ItemSeparatorComponent={() => <View style={{ height: SP.sm }} />}
        ListEmptyComponent={<Text style={s.empty}>No records found.</Text>}
        renderItem={({ item: l }) => {
          const overdue  = !!(l.due_date && !l.returned_at && l.due_date < today);
          const activeOut = !l.returned_at && !overdue;

          return (
            <View style={[s.card, overdue && s.cardOverdue, activeOut && s.cardActive]}>
              <View style={s.cardTop}>
                <Text style={[s.gameName, overdue && s.overdueText]} numberOfLines={1}>{l.game_name}</Text>
                <View style={s.cardActions}>
                  {!l.returned_at && (
                    <TouchableOpacity
                      style={s.returnBtn}
                      onPress={() => returnNow(l)}
                      accessibilityRole="button"
                      accessibilityLabel={`Return ${l.game_name}`}
                    >
                      <Text style={s.returnBtnTxt}>Return</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity
                    onPress={() => openEdit(l)}
                    style={s.editBtn}
                    accessibilityRole="button"
                    accessibilityLabel={`Edit checkout for ${l.game_name}`}
                  >
                    <Ionicons name="pencil-outline" size={16} color={DS.blue600} />
                  </TouchableOpacity>
                </View>
              </View>

              <Text style={s.member}>{l.first_name} {l.last_name}</Text>

              <View style={s.statusRow}>
                {l.returned_at ? (
                  <View style={s.badgeOk}>
                    <View style={s.dotOk} />
                    <Text style={s.badgeOkTxt}>Returned {l.returned_at.slice(0, 10)}</Text>
                  </View>
                ) : overdue ? (
                  <View style={s.badgeDanger}>
                    <View style={s.dotDanger} />
                    <Text style={s.badgeDangerTxt}>Overdue</Text>
                  </View>
                ) : (
                  <View style={s.badgeWarn}>
                    <View style={s.dotWarn} />
                    <Text style={s.badgeWarnTxt}>Still out</Text>
                  </View>
                )}
              </View>

              <View style={s.dates}>
                <Text style={s.dateItem}>Out: {l.checked_out_at?.slice(0, 10)}</Text>
                {l.due_date && (
                  <Text style={[s.dateItem, overdue && s.overdueText]}>Due: {l.due_date}</Text>
                )}
              </View>

              {l.notes ? <Text style={s.notes}>{l.notes}</Text> : null}
            </View>
          );
        }}
      />

      {/* Edit Loan modal */}
      <Modal visible={!!editingLoan} transparent animationType="slide" onRequestClose={() => setEditingLoan(null)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setEditingLoan(null)} />
        <View style={s.sheet}>
          <View style={s.grabBar} />
          <Text style={s.sheetTitle}>Edit Checkout</Text>
          {editingLoan && (
            <Text style={s.sheetSub}>{editingLoan.game_name} — {editingLoan.first_name} {editingLoan.last_name}</Text>
          )}

          <Text style={s.label}>Checked Out (YYYY-MM-DD HH:MM)</Text>
          <View style={s.inputRow}>
            <DateInput value={editOut.slice(0,10)} onChange={v => setEditOut(v)} />
            <TouchableOpacity style={s.nowBtn} onPress={() => setNow(setEditOut)}>
              <Text style={s.nowBtnTxt}>Now</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.label}>Returned (blank = still out)</Text>
          <View style={s.inputRow}>
            <DateInput value={editRet.slice(0,10)} onChange={v => setEditRet(v)} nullable />
            <TouchableOpacity style={s.nowBtn} onPress={() => setNow(setEditRet)}>
              <Text style={s.nowBtnTxt}>Now</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.label}>Due Date (YYYY-MM-DD)</Text>
          <DateInput value={editDue} onChange={setEditDue} placeholder="Optional (tap to set)" nullable />

          <Text style={s.label}>Notes</Text>
          <TextInput style={s.input} value={editNotes} onChangeText={setEditNotes} placeholder="Optional" />

          <View style={s.btnRow}>
            <TouchableOpacity style={s.cancelBtn} onPress={() => setEditingLoan(null)}>
              <Text style={s.cancelBtnTxt}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.saveBtn} onPress={saveEdit}>
              <Text style={s.saveBtnTxt}>Save</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:       { flex: 1, backgroundColor: DS.bg },

  // Filter row
  filterRow:       { flexDirection: 'row', backgroundColor: DS.surface, paddingHorizontal: SP.lg, paddingVertical: SP.sm, gap: SP.sm, borderBottomWidth: 1, borderBottomColor: DS.line200 },
  filterBtn:       { flex: 1, paddingVertical: SP.sm, paddingHorizontal: SP.sm, borderRadius: R.pill, alignItems: 'center', backgroundColor: 'transparent' },
  filterBtnActive: { backgroundColor: DS.blue050 },
  filterTxt:       { fontSize: 13, fontWeight: '600', color: DS.ink500 },
  filterTxtActive: { color: DS.blue600 },

  // Loan card
  card:            { backgroundColor: DS.surface, borderRadius: R.lg, padding: SP.lg, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 1, shadowRadius: 3, elevation: 2 },
  cardActive:      { borderLeftWidth: 3, borderLeftColor: DS.warnSolid },
  cardOverdue:     { borderLeftWidth: 3, borderLeftColor: DS.dangerSolid, backgroundColor: DS.dangerBg },
  cardTop:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SP.xs },
  gameName:        { ...FONT.cardTitle, color: DS.ink900, flex: 1, marginRight: SP.sm },
  overdueText:     { color: DS.dangerText },
  cardActions:     { flexDirection: 'row', alignItems: 'center', gap: SP.sm },

  // Status badges
  statusRow:       { marginBottom: SP.sm },
  badgeOk:         { flexDirection: 'row', alignItems: 'center', gap: SP.xs, alignSelf: 'flex-start', backgroundColor: DS.okBg, paddingHorizontal: SP.sm, paddingVertical: 3, borderRadius: R.pill },
  badgeOkTxt:      { fontSize: 11, fontWeight: '700', color: DS.okText },
  dotOk:           { width: 6, height: 6, borderRadius: 3, backgroundColor: DS.okSolid },
  badgeWarn:       { flexDirection: 'row', alignItems: 'center', gap: SP.xs, alignSelf: 'flex-start', backgroundColor: DS.warnBg, paddingHorizontal: SP.sm, paddingVertical: 3, borderRadius: R.pill },
  badgeWarnTxt:    { fontSize: 11, fontWeight: '700', color: DS.warnText },
  dotWarn:         { width: 6, height: 6, borderRadius: 3, backgroundColor: DS.warnSolid },
  badgeDanger:     { flexDirection: 'row', alignItems: 'center', gap: SP.xs, alignSelf: 'flex-start', backgroundColor: DS.dangerBg, paddingHorizontal: SP.sm, paddingVertical: 3, borderRadius: R.pill },
  badgeDangerTxt:  { fontSize: 11, fontWeight: '700', color: DS.dangerText },
  dotDanger:       { width: 6, height: 6, borderRadius: 3, backgroundColor: DS.dangerSolid },

  member:          { fontSize: 13, color: DS.ink600, marginBottom: SP.sm },
  dates:           { flexDirection: 'row', gap: SP.md, flexWrap: 'wrap' },
  dateItem:        { ...FONT.caption, color: DS.ink500 },
  notes:           { marginTop: SP.sm, fontSize: 12, color: DS.ink500, fontStyle: 'italic' },

  // Return + edit buttons
  returnBtn:       { backgroundColor: DS.blue600, paddingHorizontal: SP.md, paddingVertical: SP.xs, borderRadius: R.sm },
  returnBtnTxt:    { color: DS.surface, fontWeight: '700', fontSize: 12 },
  editBtn:         { padding: SP.xs },

  empty:           { textAlign: 'center', color: DS.ink500, marginTop: 40, fontStyle: 'italic' },

  // Modal / sheet
  overlay:         { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },
  sheet:           { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: SP.xxl, paddingBottom: 44 },
  grabBar:         { width: 40, height: 5, backgroundColor: DS.line200, borderRadius: 99, alignSelf: 'center', marginBottom: SP.lg },
  sheetTitle:      { fontSize: 17, fontWeight: '700', color: DS.ink900, marginBottom: SP.xs },
  sheetSub:        { fontSize: 13, color: DS.ink600, marginBottom: SP.lg },
  label:           { fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4, color: DS.ink600, marginBottom: SP.xs },
  input:           { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, fontSize: 15, marginBottom: SP.md, color: DS.ink900, backgroundColor: DS.surface },
  inputRow:        { flexDirection: 'row', gap: SP.sm, marginBottom: SP.md, alignItems: 'center' },
  nowBtn:          { backgroundColor: DS.blue050, borderRadius: R.sm, paddingHorizontal: SP.md, paddingVertical: SP.md },
  nowBtnTxt:       { color: DS.blue600, fontSize: 12, fontWeight: '600' },
  clearBtn:        { backgroundColor: DS.dangerBg, borderRadius: R.sm, paddingHorizontal: SP.sm, paddingVertical: SP.md },
  clearBtnTxt:     { color: DS.dangerText, fontSize: 12, fontWeight: '600' },
  btnRow:          { flexDirection: 'row', gap: SP.md, marginTop: SP.xs },
  cancelBtn:       { flex: 1, backgroundColor: DS.bg, borderRadius: R.md, borderWidth: 1, borderColor: DS.line200, padding: SP.lg, alignItems: 'center' },
  cancelBtnTxt:    { color: DS.ink600, fontWeight: '600', fontSize: 14 },
  saveBtn:         { flex: 1, backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.lg, alignItems: 'center' },
  saveBtnTxt:      { color: DS.surface, fontWeight: '700', fontSize: 14 },
});
