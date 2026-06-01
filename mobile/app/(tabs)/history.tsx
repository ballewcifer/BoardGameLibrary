import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, Alert } from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as db from '../../lib/db';
import type { Loan } from '../../lib/types';

const NAVY = '#1a237e';

export default function History() {
  const [loans, setLoans]           = useState<Loan[]>([]);
  const [filter, setFilter]         = useState<'all' | 'active' | 'returned'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => setLoans(db.loanHistory()), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const returnNow = (loan: Loan) => {
    Alert.alert('Mark as returned?', `Return "${loan.game_name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Return', onPress: () => {
          db.getDb().runSync('UPDATE loans SET returned_at = ? WHERE id = ?', [db.nowIso(), loan.id]);
          load();
        }
      },
    ]);
  };

  const today = new Date().toISOString().slice(0, 10);

  const filtered = loans.filter(l => {
    if (filter === 'active')   return !l.returned_at;
    if (filter === 'returned') return !!l.returned_at;
    return true;
  });

  return (
    <View style={s.container}>
      {/* Filter tabs */}
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
                {!l.returned_at && (
                  <TouchableOpacity style={s.returnBtn} onPress={() => returnNow(l)}>
                    <Text style={s.returnBtnTxt}>Return</Text>
                  </TouchableOpacity>
                )}
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
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  filterRow: { flexDirection: 'row', backgroundColor: '#fff', padding: 8, gap: 6, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  filterBtn: { flex: 1, padding: 8, borderRadius: 8, alignItems: 'center', backgroundColor: '#f4f6fa' },
  filterBtnActive: { backgroundColor: NAVY },
  filterTxt: { fontSize: 13, fontWeight: '600', color: '#6b7280' },
  filterTxtActive: { color: '#fff' },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 4, elevation: 2 },
  cardOverdue: { borderLeftWidth: 3, borderLeftColor: '#b71c1c' },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  gameName: { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 8 },
  overdueText: { color: '#b71c1c' },
  member: { fontSize: 13, color: '#6b7280', marginBottom: 6 },
  dates: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  dateItem: { fontSize: 12, color: '#9e9e9e' },
  notes: { marginTop: 6, fontSize: 12, color: '#9e9e9e', fontStyle: 'italic' },
  returnBtn: { backgroundColor: '#e8eaf6', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  returnBtnTxt: { color: NAVY, fontWeight: '600', fontSize: 12 },
  empty: { textAlign: 'center', color: '#9e9e9e', marginTop: 40, fontStyle: 'italic' },
});
