import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl } from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as db from '../../lib/db';
import type { Loan } from '../../lib/types';

const NAVY = '#1a237e';

export default function History() {
  const [loans, setLoans] = useState<Loan[]>([]);
  const [filter, setFilter] = useState<'all' | 'active' | 'returned'>('all');
  const [refreshing, setRefreshing] = useState(false);
  const today = new Date().toISOString().slice(0, 10);

  const load = useCallback(() => setLoans(db.loanHistory()), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = () => { setRefreshing(true); load(); setRefreshing(false); };

  const filtered = loans.filter(l => {
    if (filter === 'active') return !l.returned_at;
    if (filter === 'returned') return !!l.returned_at;
    return true;
  });

  const returnNow = (loan: Loan) => {
    db.getDb().runSync('UPDATE loans SET returned_at = ? WHERE id = ?', [db.nowIso(), loan.id]);
    load();
  };

  return (
    <View style={s.container}>
      <View style={s.filterRow}>
        {(['all', 'active', 'returned'] as const).map(f => (
          <TouchableOpacity key={f} style={[s.filterBtn, filter === f && s.filterBtnActive]} onPress={() => setFilter(f)}>
            <Text style={[s.filterTxt, filter === f && s.filterTxtActive]}>
              {f === 'all' ? 'All' : f === 'active' ? 'Still Out' : 'Returned'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={s.count}>{filtered.length} record{filtered.length !== 1 ? 's' : ''}</Text>
      <FlatList
        data={filtered}
        keyExtractor={l => String(l.id)}
        renderItem={({ item: l }) => {
          const overdue = !l.returned_at && !!(l.due_date && l.due_date < today);
          return (
            <View style={[s.card, overdue && s.cardOverdue]}>
              <View style={s.cardTop}>
                <Text style={[s.gameName, overdue && s.textRed]} numberOfLines={1}>{l.game_name}</Text>
                {!l.returned_at && (
                  <TouchableOpacity style={s.returnBtn} onPress={() => returnNow(l)}>
                    <Text style={s.returnTxt}>Return Now</Text>
                  </TouchableOpacity>
                )}
              </View>
              <Text style={s.member}>{l.first_name} {l.last_name}</Text>
              <View style={s.dates}>
                <Text style={s.dateLabel}>Out: <Text style={s.dateVal}>{l.checked_out_at.slice(0, 10)}</Text></Text>
                {l.due_date && <Text style={[s.dateLabel, overdue && s.textRed]}>Due: <Text style={s.dateVal}>{l.due_date}</Text></Text>}
                {l.returned_at
                  ? <Text style={s.dateLabel}>Returned: <Text style={s.dateVal}>{l.returned_at.slice(0, 10)}</Text></Text>
                  : <Text style={[s.dateLabel, overdue ? s.textRed : s.textOrange]}>
                      {overdue ? '⚠ OVERDUE' : 'Still out'}
                    </Text>}
              </View>
              {l.notes ? <Text style={s.notes}>{l.notes}</Text> : null}
            </View>
          );
        }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ padding: 10, gap: 8 }}
        ListEmptyComponent={<Text style={s.empty}>No checkout records.</Text>}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  filterRow: { flexDirection: 'row', gap: 8, padding: 10 },
  filterBtn: { flex: 1, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: '#e5e7eb', alignItems: 'center', backgroundColor: '#fff' },
  filterBtnActive: { backgroundColor: NAVY, borderColor: NAVY },
  filterTxt: { fontSize: 13, color: '#555', fontWeight: '600' },
  filterTxtActive: { color: '#fff' },
  count: { paddingHorizontal: 12, paddingBottom: 4, color: '#9e9e9e', fontSize: 12 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  cardOverdue: { borderLeftWidth: 3, borderLeftColor: '#b71c1c' },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  gameName: { fontSize: 15, fontWeight: '700', flex: 1 },
  member: { fontSize: 13, color: '#6b7280', marginBottom: 6 },
  dates: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  dateLabel: { fontSize: 12, color: '#9e9e9e' },
  dateVal: { color: '#333', fontWeight: '600' },
  notes: { fontSize: 12, color: '#9e9e9e', marginTop: 4, fontStyle: 'italic' },
  returnBtn: { backgroundColor: '#e8eaf6', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 5 },
  returnTxt: { fontSize: 12, color: NAVY, fontWeight: '700' },
  textRed: { color: '#b71c1c' },
  textOrange: { color: '#f57c00' },
  empty: { textAlign: 'center', color: '#9e9e9e', padding: 40, fontSize: 14 },
});
