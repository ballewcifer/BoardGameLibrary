import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, Alert, Modal, TextInput, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Loan } from '../../lib/types';
import ScreenHeader from '../../components/ScreenHeader';

const NAVY = '#1a237e';

export default function History({ isActive = true }: { isActive?: boolean }) {
  const [loans, setLoans]           = useState<Loan[]>([]);
  const [filter, setFilter]         = useState<'all' | 'active' | 'returned'>('all');
  const [refreshing, setRefreshing] = useState(false);
  const [editingLoan, setEditingLoan] = useState<Loan | null>(null);

  // Edit form fields
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
          <TouchableOpacity key={f} style={[s.filterBtn, filter === f && s.filterBtnActive]} onPress={() => setFilter(f)}>
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
        contentContainerStyle={{ padding: 12 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        ListEmptyComponent={<Text style={s.empty}>No records found.</Text>}
        renderItem={({ item: l }) => {
          const overdue = !!(l.due_date && !l.returned_at && l.due_date < today);
          return (
            <View style={[s.card, overdue && s.cardOverdue]}>
              <View style={s.cardTop}>
                <Text style={[s.gameName, overdue && s.overdueText]} numberOfLines={1}>{l.game_name}</Text>
                <View style={s.cardActions}>
                  {!l.returned_at && (
                    <TouchableOpacity style={s.returnBtn} onPress={() => returnNow(l)}>
                      <Text style={s.returnBtnTxt}>Return</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity onPress={() => openEdit(l)} style={s.editBtn}>
                    <Ionicons name="pencil-outline" size={16} color={NAVY} />
                  </TouchableOpacity>
                </View>
              </View>
              <Text style={s.member}>{l.first_name} {l.last_name}</Text>
              <View style={s.dates}>
                <Text style={s.dateItem}>Out: {l.checked_out_at?.slice(0, 10)}</Text>
                {l.due_date && <Text style={[s.dateItem, overdue && s.overdueText]}>Due: {l.due_date}</Text>}
                {l.returned_at
                  ? <Text style={[s.dateItem, { color: '#1b5e20' }]}>✓ {l.returned_at.slice(0, 10)}</Text>
                  : <Text style={[s.dateItem, { color: overdue ? '#b71c1c' : '#795548' }]}>{overdue ? '⚠ OVERDUE' : 'Still out'}</Text>}
              </View>
              {l.notes ? <Text style={s.notes}>{l.notes}</Text> : null}
            </View>
          );
        }}
      />

      {/* Edit Loan modal */}
      <Modal visible={!!editingLoan} transparent animationType="slide" onRequestClose={() => setEditingLoan(null)}>
        <Pressable style={s.overlay} onPress={() => setEditingLoan(null)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Edit Checkout</Text>
          {editingLoan && (
            <Text style={s.sheetSub}>{editingLoan.game_name} — {editingLoan.first_name} {editingLoan.last_name}</Text>
          )}

          <Text style={s.label}>Checked Out (YYYY-MM-DD HH:MM)</Text>
          <View style={s.inputRow}>
            <TextInput style={[s.input, { flex: 1 }]} value={editOut} onChangeText={setEditOut} placeholder="2026-01-15 14:30" />
            <TouchableOpacity style={s.nowBtn} onPress={() => setNow(setEditOut)}>
              <Text style={s.nowBtnTxt}>Now</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.label}>Returned (blank = still out)</Text>
          <View style={s.inputRow}>
            <TextInput style={[s.input, { flex: 1 }]} value={editRet} onChangeText={setEditRet} placeholder="Leave blank if still out" />
            <TouchableOpacity style={s.nowBtn} onPress={() => setNow(setEditRet)}>
              <Text style={s.nowBtnTxt}>Now</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.clearBtn} onPress={() => setEditRet('')}>
              <Text style={s.clearBtnTxt}>Clear</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.label}>Due Date (YYYY-MM-DD)</Text>
          <TextInput style={s.input} value={editDue} onChangeText={setEditDue} placeholder="Optional" />

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
  container:      { flex: 1, backgroundColor: '#f4f6fa' },
  filterRow:      { flexDirection: 'row', backgroundColor: '#fff', padding: 8, gap: 6, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  filterBtn:      { flex: 1, padding: 8, borderRadius: 8, alignItems: 'center', backgroundColor: '#f4f6fa' },
  filterBtnActive:{ backgroundColor: NAVY },
  filterTxt:      { fontSize: 13, fontWeight: '600', color: '#6b7280' },
  filterTxtActive:{ color: '#fff' },
  card:           { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 4, elevation: 2 },
  cardOverdue:    { borderLeftWidth: 3, borderLeftColor: '#b71c1c' },
  cardTop:        { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  gameName:       { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 8 },
  overdueText:    { color: '#b71c1c' },
  cardActions:    { flexDirection: 'row', alignItems: 'center', gap: 6 },
  member:         { fontSize: 13, color: '#6b7280', marginBottom: 6 },
  dates:          { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  dateItem:       { fontSize: 12, color: '#9e9e9e' },
  notes:          { marginTop: 6, fontSize: 12, color: '#9e9e9e', fontStyle: 'italic' },
  returnBtn:      { backgroundColor: '#e8eaf6', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  returnBtnTxt:   { color: NAVY, fontWeight: '600', fontSize: 12 },
  editBtn:        { padding: 4 },
  empty:          { textAlign: 'center', color: '#9e9e9e', marginTop: 40, fontStyle: 'italic' },
  // Modal
  overlay:        { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet:          { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 44 },
  sheetTitle:     { fontSize: 18, fontWeight: '700', color: NAVY, marginBottom: 4 },
  sheetSub:       { fontSize: 13, color: '#6b7280', marginBottom: 16 },
  label:          { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input:          { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  inputRow:       { flexDirection: 'row', gap: 6, marginBottom: 12, alignItems: 'center' },
  nowBtn:         { backgroundColor: '#e8eaf6', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 10 },
  nowBtnTxt:      { color: NAVY, fontSize: 12, fontWeight: '600' },
  clearBtn:       { backgroundColor: '#fee2e2', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 10 },
  clearBtnTxt:    { color: '#b91c1c', fontSize: 12, fontWeight: '600' },
  btnRow:         { flexDirection: 'row', gap: 10, marginTop: 4 },
  cancelBtn:      { flex: 1, backgroundColor: '#f3f4f6', borderRadius: 8, padding: 14, alignItems: 'center' },
  cancelBtnTxt:   { color: '#6b7280', fontWeight: '600' },
  saveBtn:        { flex: 1, backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center' },
  saveBtnTxt:     { color: '#fff', fontWeight: '700' },
});
