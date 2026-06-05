import { useCallback, useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl, Alert } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import { exportBackup, importBackup } from '../../lib/backup';
import type { Stats, Loan, Play } from '../../lib/types';
import ScreenHeader from '../../components/ScreenHeader';
import RibbonBadge from '../../components/RibbonBadge';

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
  dangerText: '#B3261E', dangerBg:'#FCEBEA', dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg: '#E7F0FB',
  starText:   '#B07A00', starFill:'#F2A900',
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

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
    <View style={{ flex: 1, backgroundColor: DS.bg }}>
      <ScreenHeader title="🎲 Board Game Library" />

      <ScrollView
        style={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
      >
        {/* Stat cards */}
        <View style={s.statGrid}>
          <TouchableOpacity style={[s.statCard, { backgroundColor: DS.navy900 }]} onPress={() => router.push('/games')} accessibilityRole="button" accessibilityLabel={`Games: ${stats.total_games}, navigate to games list`}>
            <Text style={s.statNum}>{stats.total_games}</Text>
            <Text style={s.statLbl}>Games</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: DS.okSolid }]} onPress={() => router.push('/plays')} accessibilityRole="button" accessibilityLabel={`Total Plays: ${stats.total_plays}, navigate to plays`}>
            <Text style={s.statNum}>{stats.total_plays}</Text>
            <Text style={s.statLbl}>Total Plays</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#4a148c' }]} onPress={() => router.push('/members')} accessibilityRole="button" accessibilityLabel={`Members: ${stats.total_members}, navigate to members`}>
            <Text style={s.statNum}>{stats.total_members}</Text>
            <Text style={s.statLbl}>Members</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: stats.checked_out ? DS.dangerSolid : DS.ink500 }]} onPress={() => router.push('/history')} accessibilityRole="button" accessibilityLabel={`Checked Out: ${stats.checked_out}, navigate to history`}>
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
                <View key={loan.id} style={[s.row, overdue ? s.overdueRow : s.loanRow]}>
                  <Text style={[s.rowTitle, overdue ? s.overdueText : s.loanText]}>{loan.game_name}</Text>
                  <Text style={[s.rowSub, overdue ? s.overdueText : s.loanSubText]}>{loan.first_name} {loan.last_name} · {loan.checked_out_at?.slice(0, 10)}</Text>
                  {loan.due_date && <Text style={[s.rowSub, overdue ? s.overdueText : s.loanSubText]}>Due: {loan.due_date}</Text>}
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
          <View style={{ flex: 1, gap: SP.sm }}>
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
              <Ionicons name="download-outline" size={20} color={DS.surface} />
              <Text style={s.backupBtnTxt}>Export Backup</Text>
              <Text style={s.backupBtnSub}>Save to Drive, email, etc.</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.backupBtn} onPress={onImport} accessibilityRole="button" accessibilityLabel="Import backup from a JSON file">
              <Ionicons name="cloud-upload-outline" size={20} color={DS.surface} />
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
  scroll:       { flex: 1, backgroundColor: DS.bg },
  statGrid:     { flexDirection: 'row', flexWrap: 'wrap', gap: SP.sm, padding: SP.lg },
  statCard:     { flex: 1, minWidth: '45%', borderRadius: R.md, padding: SP.lg, alignItems: 'center' },
  statNum:      { color: DS.surface, fontSize: 28, fontWeight: '700' },
  statLbl:      { color: 'rgba(255,255,255,0.85)', fontSize: 12, marginTop: SP.xs },
  card:         { backgroundColor: DS.surface, borderRadius: R.lg, padding: SP.lg, margin: SP.sm, marginTop: 0, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 1, shadowRadius: 3, elevation: 2 },
  sectionTitle: { fontSize: 17, fontWeight: '700', color: DS.navy900, marginBottom: SP.sm },
  twoCol:       { flexDirection: 'column' },
  row:          { paddingVertical: SP.sm, borderBottomWidth: 1, borderBottomColor: DS.line100, borderRadius: R.sm, paddingHorizontal: SP.sm, marginBottom: SP.xs },
  rowTitle:     { fontSize: 14, fontWeight: '600', color: DS.ink900 },
  rowSub:       { fontSize: 12, color: DS.ink600, marginTop: 2 },
  loanRow:      { backgroundColor: DS.warnBg },
  loanText:     { color: DS.warnText },
  loanSubText:  { color: DS.warnText },
  overdueRow:   { backgroundColor: DS.dangerBg },
  overdueText:  { color: DS.dangerText },
  listItem:     { fontSize: 13, paddingVertical: 3, color: DS.ink900 },
  dim:          { color: DS.ink500 },
  empty:        { fontSize: 13, color: DS.ink500, fontStyle: 'italic' },
  winnerRow:    { flexDirection: 'row', alignItems: 'center', paddingVertical: SP.xs, gap: SP.sm },
  winnerNum:    { width: 36, textAlign: 'center', fontSize: 13, color: DS.ink500, fontWeight: '600' },
  winnerName:   { flex: 1, fontSize: 13, color: DS.ink900 },
  winnerCount:  { fontSize: 12, color: DS.ink500 },
  backupRow:    { flexDirection: 'row', gap: SP.sm },
  backupBtn:    { flex: 1, backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.md, alignItems: 'center', gap: SP.xs },
  backupBtnTxt: { fontSize: 13, fontWeight: '600', color: DS.surface, textAlign: 'center' },
  backupBtnSub: { fontSize: 11, color: 'rgba(255,255,255,0.80)', textAlign: 'center' },
});
