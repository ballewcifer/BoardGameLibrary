import { useCallback, useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, Alert } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import { exportBackup, importBackup } from '../../lib/backup';
import type { Stats, Loan, Play } from '../../lib/types';
import ScreenHeader from '../../components/ScreenHeader';
import RibbonBadge from '../../components/RibbonBadge';

const NAVY = '#1a237e';

export default function Dashboard({ isActive = true }: { isActive?: boolean }) {
  const [stats, setStats]           = useState<Stats>({ total_games: 0, total_plays: 0, total_members: 0, checked_out: 0 });
  const [checkedOut, setCheckedOut] = useState<Loan[]>([]);
  const [recent, setRecent]         = useState<Play[]>([]);
  const [topGames, setTopGames]     = useState<any[]>([]);
  const [topWins, setTopWins]       = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    setStats(db.statsSummary());
    setCheckedOut(db.currentlyCheckedOut());
    setRecent(db.recentPlays(8));
    setTopGames(db.topGamesByPlays(5));
    setTopWins(db.topWinners(5));
  }, []);

  useEffect(() => { if (isActive) load(); }, [isActive]);

  const today = new Date().toISOString().slice(0, 10);

  const onExport = async () => {
    try { await exportBackup(); }
    catch (e: any) { Alert.alert('Export failed', e.message ?? String(e)); }
  };

  const onImport = async () => {
    try {
      const counts = await importBackup();
      load();
      Alert.alert(
        'Import complete',
        `Members: +${counts.members}\nPlays: +${counts.plays}\nLoans: +${counts.loans}\nCustomisations: ${counts.customisations}\nSkipped: ${counts.skipped}`
      );
    } catch (e: any) {
      if (e.message !== 'Cancelled') Alert.alert('Import failed', e.message ?? String(e));
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <ScreenHeader title="🎲 Board Game Library" />

      <ScrollView
        style={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
      >
        {/* Stat cards */}
        <View style={s.statGrid}>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#1a237e' }]} onPress={() => router.push('/games')} accessibilityRole="button" accessibilityLabel={`Games: ${stats.total_games}, navigate to games list`}>
            <Text style={s.statNum}>{stats.total_games}</Text>
            <Text style={s.statLbl}>Games</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#1b5e20' }]} onPress={() => router.push('/plays')} accessibilityRole="button" accessibilityLabel={`Total Plays: ${stats.total_plays}, navigate to plays`}>
            <Text style={s.statNum}>{stats.total_plays}</Text>
            <Text style={s.statLbl}>Total Plays</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#4a148c' }]} onPress={() => router.push('/members')} accessibilityRole="button" accessibilityLabel={`Members: ${stats.total_members}, navigate to members`}>
            <Text style={s.statNum}>{stats.total_members}</Text>
            <Text style={s.statLbl}>Members</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: stats.checked_out ? '#b71c1c' : '#37474f' }]} onPress={() => router.push('/history')} accessibilityRole="button" accessibilityLabel={`Checked Out: ${stats.checked_out}, navigate to history`}>
            <Text style={s.statNum}>{stats.checked_out}</Text>
            <Text style={s.statLbl}>Checked Out</Text>
          </TouchableOpacity>
        </View>

        {checkedOut.length > 0 && (
          <View style={s.card}>
            <Text style={s.sectionTitle}>Currently Checked Out</Text>
            {checkedOut.map(loan => {
              const overdue = !!(loan.due_date && loan.due_date < today);
              return (
                <View key={loan.id} style={[s.row, overdue && s.overdueRow]}>
                  <Text style={[s.rowTitle, overdue && s.overdueText]}>{loan.game_name}</Text>
                  <Text style={s.rowSub}>{loan.first_name} {loan.last_name} · {loan.checked_out_at?.slice(0, 10)}</Text>
                  {loan.due_date && <Text style={[s.rowSub, overdue && s.overdueText]}>Due: {loan.due_date}</Text>}
                </View>
              );
            })}
          </View>
        )}

        <View style={s.twoCol}>
          <View style={[s.card, { flex: 1 }]}>
            <Text style={s.sectionTitle}>Recent Plays</Text>
            {recent.length === 0
              ? <Text style={s.empty}>No plays yet.</Text>
              : recent.map((p, i) => (
                <Text key={i} style={s.listItem}>
                  <Text style={s.dim}>{p.played_at?.slice(0, 10)}  </Text>
                  {p.game_name}{p.winner ? `  🏆 ${p.winner}` : ''}
                </Text>
              ))}
          </View>
          <View style={{ flex: 1, gap: 10 }}>
            <View style={s.card}>
              <Text style={s.sectionTitle}>Most Played</Text>
              {topGames.length === 0
                ? <Text style={s.empty}>No plays yet.</Text>
                : topGames.map((g, i) => <Text key={i} style={s.listItem}>{i + 1}. {g.name} ({g.play_count})</Text>)}
            </View>
            <View style={s.card}>
              <Text style={s.sectionTitle}>Top Winners</Text>
              {topWins.length === 0
                ? <Text style={s.empty}>No winners yet.</Text>
                : topWins.map((w, i) => (
                  <View key={i} style={s.winnerRow}>
                    {i < 3
                      ? <RibbonBadge rank={(i + 1) as 1|2|3} size={0.55} />
                      : <Text style={s.winnerNum}>{i + 1}</Text>}
                    <Text style={s.winnerName}>{w.winner}</Text>
                    <Text style={s.winnerCount}>{w.win_count} win{w.win_count !== 1 ? 's' : ''}</Text>
                  </View>
                ))}
            </View>
          </View>
        </View>

        {/* Backup */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>Backup & Restore</Text>
          <View style={s.backupRow}>
            <TouchableOpacity style={s.backupBtn} onPress={onExport} accessibilityRole="button" accessibilityLabel="Export backup">
              <Ionicons name="download-outline" size={20} color={NAVY} />
              <Text style={s.backupBtnTxt}>Export Backup</Text>
              <Text style={s.backupBtnSub}>Save to Drive, email, etc.</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.backupBtn} onPress={onImport} accessibilityRole="button" accessibilityLabel="Import backup from a JSON file">
              <Ionicons name="cloud-upload-outline" size={20} color={NAVY} />
              <Text style={s.backupBtnTxt}>Import Backup</Text>
              <Text style={s.backupBtnSub}>Restore from a .json file</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  scroll:     { flex: 1, backgroundColor: '#f4f6fa' },
  statGrid:   { flexDirection: 'row', flexWrap: 'wrap', gap: 10, padding: 14 },
  statCard:   { flex: 1, minWidth: '45%', borderRadius: 10, padding: 14, alignItems: 'center' },
  statNum:    { color: '#fff', fontSize: 28, fontWeight: '700' },
  statLbl:    { color: 'rgba(255,255,255,.85)', fontSize: 12, marginTop: 2 },
  card:       { backgroundColor: '#fff', borderRadius: 10, padding: 14, margin: 7, marginTop: 0, shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: NAVY, marginBottom: 8 },
  twoCol:     { flexDirection: 'column' },
  row:        { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  rowTitle:   { fontSize: 14, fontWeight: '600' },
  rowSub:     { fontSize: 12, color: '#6b7280', marginTop: 2 },
  overdueRow: { backgroundColor: '#fff5f5' },
  overdueText:{ color: '#b71c1c' },
  listItem:   { fontSize: 13, paddingVertical: 3, color: '#333' },
  dim:        { color: '#9e9e9e' },
  empty:      { fontSize: 13, color: '#9e9e9e', fontStyle: 'italic' },
  winnerRow:  { flexDirection: 'row', alignItems: 'center', paddingVertical: 4, gap: 8 },
  winnerNum:  { width: 36, textAlign: 'center', fontSize: 13, color: '#9e9e9e', fontWeight: '600' },
  winnerName: { flex: 1, fontSize: 13, color: '#333' },
  winnerCount:{ fontSize: 12, color: '#9e9e9e' },
  backupRow:  { flexDirection: 'row', gap: 10 },
  backupBtn:  { flex: 1, borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, alignItems: 'center', gap: 4 },
  backupBtnTxt: { fontSize: 13, fontWeight: '600', color: NAVY, textAlign: 'center' },
  backupBtnSub: { fontSize: 11, color: '#9e9e9e', textAlign: 'center' },
});
