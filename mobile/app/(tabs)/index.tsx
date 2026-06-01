import { useCallback, useState, useRef } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, Modal, TextInput, Alert, ActivityIndicator, Pressable,
} from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import * as bgg from '../../lib/bgg';
import { loadSettings, saveSettings } from '../../lib/settings';
import type { Stats, Loan, Play } from '../../lib/types';

const NAVY = '#1a237e';

export default function Dashboard() {
  const [stats, setStats]           = useState<Stats>({ total_games: 0, total_plays: 0, total_members: 0, checked_out: 0 });
  const [checkedOut, setCheckedOut] = useState<Loan[]>([]);
  const [recent, setRecent]         = useState<Play[]>([]);
  const [topGames, setTopGames]     = useState<any[]>([]);
  const [topWins, setTopWins]       = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  // Sync state
  const [syncing, setSyncing]         = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  // Settings modal
  const [settingsOpen, setSettingsOpen]     = useState(false);
  const [bggUsername, setBggUsername]       = useState('');
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  const load = useCallback(() => {
    setStats(db.statsSummary());
    setCheckedOut(db.currentlyCheckedOut());
    setRecent(db.recentPlays(8));
    setTopGames(db.topGamesByPlays(5));
    setTopWins(db.topWinners(5));
  }, []);

  useFocusEffect(useCallback(() => {
    load();
    if (!settingsLoaded) {
      loadSettings().then(s => { setBggUsername(s.bgg_username); setSettingsLoaded(true); });
    }
  }, [load, settingsLoaded]));

  const onRefresh = useCallback(() => {
    setRefreshing(true); load(); setRefreshing(false);
  }, [load]);

  const openSettings = async () => {
    const s = await loadSettings();
    setBggUsername(s.bgg_username);
    setSettingsOpen(true);
  };

  const saveAndClose = async () => {
    await saveSettings({ bgg_username: bggUsername.trim() });
    setSettingsOpen(false);
  };

  const onSync = async () => {
    const settings = await loadSettings();
    if (!settings.bgg_username) {
      Alert.alert('BGG Username required', 'Tap the ⚙ icon to set your BGG username first.');
      return;
    }
    setSyncing(true);
    setSyncMessage('Fetching collection…');
    try {
      const games = await bgg.fetchCollection(settings.bgg_username);
      setSyncMessage(`Saving ${games.length} games…`);
      for (const g of games) {
        db.upsertGame({
          bgg_id:       g.bgg_id,
          name:         g.name,
          year:         g.year,
          image_url:    g.image_url,
          thumbnail_url:g.thumbnail_url,
          min_players:  g.min_players,
          max_players:  g.max_players,
          playing_time: g.playing_time,
          weight:       g.weight,
          avg_rating:   g.avg_rating,
          description:  g.description,
          categories:   g.categories?.join(', '),
          mechanics:    g.mechanics?.join(', '),
          designers:    g.designers?.join(', '),
          publishers:   g.publishers?.join(', '),
          own:          1,
          is_expansion: g.is_expansion ? 1 : 0,
        });
      }
      load();
      setSyncMessage(`✓ Synced ${games.length} games`);
      setTimeout(() => setSyncMessage(''), 3000);
    } catch (e: any) {
      Alert.alert('Sync failed', e.message ?? String(e));
      setSyncMessage('');
    } finally {
      setSyncing(false);
    }
  };

  const today = new Date().toISOString().slice(0, 10);

  return (
    <View style={{ flex: 1 }}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>🎲 Board Game Library</Text>
        <View style={s.headerRight}>
          {syncing
            ? <ActivityIndicator color="#fff" style={{ marginRight: 12 }} />
            : <TouchableOpacity onPress={onSync} style={s.headerBtn}>
                <Ionicons name="sync" size={20} color="#fff" />
              </TouchableOpacity>}
          <TouchableOpacity onPress={openSettings} style={s.headerBtn}>
            <Ionicons name="settings-outline" size={20} color="#fff" />
          </TouchableOpacity>
        </View>
      </View>

      {syncMessage ? (
        <View style={s.syncBanner}>
          <Text style={s.syncBannerTxt}>{syncMessage}</Text>
        </View>
      ) : null}

      <ScrollView style={s.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
        {/* Stat cards */}
        <View style={s.statGrid}>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#1a237e' }]} onPress={() => router.push('/games')}>
            <Text style={s.statNum}>{stats.total_games}</Text>
            <Text style={s.statLbl}>Games</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#1b5e20' }]} onPress={() => router.push('/plays')}>
            <Text style={s.statNum}>{stats.total_plays}</Text>
            <Text style={s.statLbl}>Total Plays</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: '#4a148c' }]} onPress={() => router.push('/members')}>
            <Text style={s.statNum}>{stats.total_members}</Text>
            <Text style={s.statLbl}>Members</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.statCard, { backgroundColor: stats.checked_out ? '#b71c1c' : '#37474f' }]} onPress={() => router.push('/history')}>
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
                : topGames.map((g, i) => (
                  <Text key={i} style={s.listItem}>{i + 1}. {g.name} ({g.play_count})</Text>
                ))}
            </View>
            <View style={s.card}>
              <Text style={s.sectionTitle}>Top Winners</Text>
              {topWins.length === 0
                ? <Text style={s.empty}>No winners yet.</Text>
                : topWins.map((w, i) => (
                  <Text key={i} style={s.listItem}>{i + 1}. {w.winner} ({w.win_count})</Text>
                ))}
            </View>
          </View>
        </View>
      </ScrollView>

      {/* Settings modal */}
      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setSettingsOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Settings</Text>
          <Text style={s.sheetLabel}>BGG Username</Text>
          <TextInput
            style={s.sheetInput}
            value={bggUsername}
            onChangeText={setBggUsername}
            placeholder="e.g. Ballewcifer"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={s.sheetHint}>Used to sync your BGG collection. Tap ⟳ on the dashboard to sync.</Text>
          <TouchableOpacity style={s.sheetBtn} onPress={saveAndClose}>
            <Text style={s.sheetBtnTxt}>Save</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 52, paddingBottom: 12 },
  headerTitle: { color: '#fff', fontSize: 17, fontWeight: '700' },
  headerRight: { flexDirection: 'row', gap: 4 },
  headerBtn: { padding: 8 },
  syncBanner: { backgroundColor: '#e8f5e9', padding: 8, alignItems: 'center' },
  syncBannerTxt: { color: '#1b5e20', fontSize: 13 },
  scroll: { flex: 1, backgroundColor: '#f4f6fa' },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, padding: 14 },
  statCard: { flex: 1, minWidth: '45%', borderRadius: 10, padding: 14, alignItems: 'center' },
  statNum: { color: '#fff', fontSize: 28, fontWeight: '700' },
  statLbl: { color: 'rgba(255,255,255,.85)', fontSize: 12, marginTop: 2 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, margin: 7, marginTop: 0, shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: NAVY, marginBottom: 8 },
  twoCol: { flexDirection: 'column' },
  row: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  rowTitle: { fontSize: 14, fontWeight: '600' },
  rowSub: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  overdueRow: { backgroundColor: '#fff5f5' },
  overdueText: { color: '#b71c1c' },
  listItem: { fontSize: 13, paddingVertical: 3, color: '#333' },
  dim: { color: '#9e9e9e' },
  empty: { fontSize: 13, color: '#9e9e9e', fontStyle: 'italic' },
  // Settings sheet
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  sheetTitle: { fontSize: 18, fontWeight: '700', marginBottom: 20, color: NAVY },
  sheetLabel: { fontSize: 13, fontWeight: '600', marginBottom: 6, color: '#333' },
  sheetInput: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 8 },
  sheetHint: { fontSize: 12, color: '#9e9e9e', marginBottom: 20 },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center' },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
