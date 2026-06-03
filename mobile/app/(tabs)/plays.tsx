import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Pressable, RefreshControl, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import * as bgg from '../../lib/bgg';
import { loadSettings } from '../../lib/settings';
import type { Play, Game, User } from '../../lib/types';
import PlayerPicker from '../../components/PlayerPicker';
import ScreenHeader from '../../components/ScreenHeader';
import DateInput from '../../components/DateInput';

const NAVY = '#1a237e';

export default function Plays({ isActive = true }: { isActive?: boolean }) {
  const [plays, setPlays]           = useState<Play[]>([]);
  const [games, setGames]           = useState<Game[]>([]);
  const [users, setUsers]           = useState<User[]>([]);
  const [winners, setWinners]       = useState<{ winner: string; win_count: number }[]>([]);
  const [view, setView]             = useState<'log' | 'leaderboard'>('log');
  const [refreshing, setRefreshing] = useState(false);
  const [modalOpen, setModalOpen]   = useState(false);
  const [editingPlay, setEditingPlay] = useState<Play | null>(null);

  // Form fields
  const [selGame, setSelGame]   = useState<Game | null>(null);
  const [date, setDate]         = useState('');
  const [players, setPlayers]   = useState('');
  const [winner, setWinner]     = useState('');
  const [duration, setDuration] = useState('');
  const [scores, setScores]     = useState('');
  const [notes, setNotes]       = useState('');
  const [pickingGame, setPickingGame]       = useState(false);
  const [gameSearch, setGameSearch]         = useState('');
  const [bggResults, setBggResults]         = useState<bgg.SearchResult[]>([]);
  const [bggSearching, setBggSearching]     = useState(false);

  const load = useCallback(() => {
    setPlays(db.listPlays());
    setGames(db.listGames());
    setUsers(db.listUsers());
    setWinners(db.topWinners(0));
  }, []);
  useEffect(() => { if (isActive) load(); }, [isActive]);

  const openLog = (p?: Play) => {
    if (p) {
      // Edit mode — pre-fill from existing play
      setEditingPlay(p);
      const g = games.find(g => g.bgg_id === p.game_id) ?? null;
      setSelGame(g);
      setDate(p.played_at?.slice(0, 10) ?? new Date().toISOString().slice(0, 10));
      setPlayers(p.player_names ?? '');
      setWinner(p.winner ?? '');
      setDuration(p.duration_minutes ? String(p.duration_minutes) : '');
      setScores(p.scores ?? '');
      setNotes(p.notes ?? '');
    } else {
      setEditingPlay(null);
      setSelGame(null);
      setDate(new Date().toISOString().slice(0, 10));
      setPlayers(''); setWinner(''); setDuration(''); setScores(''); setNotes('');
    }
    setModalOpen(true);
  };

  const savePlay = () => {
    if (!selGame) { Alert.alert('Select a game'); return; }
    if (!date)    { Alert.alert('Date required'); return; }
    const dur = duration ? parseInt(duration, 10) : undefined;
    const sc  = scores.trim() || undefined;
    if (editingPlay) {
      db.updatePlay(editingPlay.id, selGame.bgg_id, date, players, winner, notes, dur, sc);
    } else {
      db.logPlay(selGame.bgg_id, date, players, winner, notes, dur, sc);
    }
    setModalOpen(false);
    load();
  };

  const deletePlay = (p: Play) => {
    Alert.alert('Delete play?', `Delete this play of ${p.game_name}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => { db.deletePlay(p.id); load(); } },
    ]);
  };

  const filteredGames = games.filter(g =>
    g.name.toLowerCase().includes(gameSearch.toLowerCase())
  );

  const searchBGG = async () => {
    if (!gameSearch.trim()) return;
    setBggSearching(true);
    setBggResults([]);
    try {
      const settings = await loadSettings();
      const results = await bgg.searchGames(gameSearch.trim(), settings.bgg_token || undefined);
      setBggResults(results.slice(0, 20));
    } catch (e: any) {
      Alert.alert('BGG search failed', e.message ?? String(e));
    } finally {
      setBggSearching(false);
    }
  };

  const addFromBGG = async (result: bgg.SearchResult) => {
    try {
      const settings = await loadSettings();
      const details = await bgg.fetchGameDetails(result.bgg_id, settings.bgg_token || undefined);
      if (!details) { Alert.alert('Game not found'); return; }
      db.upsertGame({
        bgg_id: details.bgg_id, name: details.name, year: details.year,
        image_url: details.image_url, thumbnail_url: details.thumbnail_url,
        min_players: details.min_players, max_players: details.max_players,
        playing_time: details.playing_time, weight: details.weight,
        avg_rating: details.avg_rating, description: details.description,
        categories: details.categories?.join(', '), mechanics: details.mechanics?.join(', '),
        designers: details.designers?.join(', '), publishers: details.publishers?.join(', '),
        own: 0,   // not in collection — play-log only
        is_expansion: details.is_expansion ? 1 : 0,
      });
      const newGame = db.getGame(details.bgg_id);
      if (newGame) setSelGame(newGame);
      load();
      setPickingGame(false);
      setGameSearch('');
      setBggResults([]);
    } catch (e: any) {
      Alert.alert('Error', e.message ?? String(e));
    }
  };

  return (
    <View style={s.container}>
      <ScreenHeader
        title="Play Log"
        right={
          <TouchableOpacity onPress={() => openLog()} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} accessibilityRole="button" accessibilityLabel="Log a new play">
            <Ionicons name="add-circle-outline" size={26} color="#fff" />
          </TouchableOpacity>
        }
      />

      {/* View toggle */}
      <View style={s.toggle}>
        <TouchableOpacity style={[s.toggleBtn, view === 'log' && s.toggleActive]} onPress={() => setView('log')} accessibilityRole="button" accessibilityLabel="Play Log" accessibilityState={{ selected: view === 'log' }}>
          <Text style={[s.toggleTxt, view === 'log' && s.toggleTxtActive]}>Play Log</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.toggleBtn, view === 'leaderboard' && s.toggleActive]} onPress={() => setView('leaderboard')} accessibilityRole="button" accessibilityLabel="Leaderboard" accessibilityState={{ selected: view === 'leaderboard' }}>
          <Text style={[s.toggleTxt, view === 'leaderboard' && s.toggleTxtActive]}>🏆 Leaderboard</Text>
        </TouchableOpacity>
      </View>

      {view === 'leaderboard' ? (
        <FlatList
          data={winners}
          keyExtractor={w => w.winner}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
          contentContainerStyle={{ padding: 14 }}
          ListEmptyComponent={<Text style={s.empty}>No wins recorded yet. Log some plays!</Text>}
          ListHeaderComponent={
            <Text style={s.lbHeader}>
              {winners.length} player{winners.length !== 1 ? 's' : ''} · {plays.length} play{plays.length !== 1 ? 's' : ''} total
            </Text>
          }
          renderItem={({ item: w, index }) => {
            const ribbonColors = ['#d4a017', '#8a9ba8', '#a0522d'];
            const ribbonLabels = ['1st', '2nd', '3rd'];
            const ribbonA11y  = ['First place', 'Second place', 'Third place'];
            const topThree = index < 3;
            const maxWins = winners[0]?.win_count ?? 1;
            const pct = Math.round((w.win_count / maxWins) * 100);
            return (
              <View style={[s.lbRow, topThree && s.lbRowTop]}>
                {topThree ? (
                  <View
                    style={[s.ribbon, { backgroundColor: ribbonColors[index] }]}
                    accessible={true}
                    accessibilityLabel={ribbonA11y[index]}
                  >
                    <Text style={s.ribbonTxt}>{ribbonLabels[index]}</Text>
                  </View>
                ) : (
                  <Text style={s.lbRank} accessible={true} accessibilityLabel={`Rank ${index + 1}`}>{index + 1}</Text>
                )}
                <View style={s.lbInfo}>
                  <View style={s.lbNameRow}>
                    <Text style={[s.lbName, topThree && s.lbNameBold]}>{w.winner}</Text>
                    <Text style={s.lbWins}>{w.win_count} win{w.win_count !== 1 ? 's' : ''}</Text>
                  </View>
                  <View style={s.lbBarBg}>
                    <View style={[s.lbBarFill, { width: `${pct}%` as any,
                      backgroundColor: index === 0 ? '#f0c050' : index === 1 ? '#aab8c2' : index === 2 ? '#cd7f32' : NAVY }]} />
                  </View>
                </View>
              </View>
            );
          }}
        />
      ) : (
        <>
          <Text style={s.count}>{plays.length} play{plays.length !== 1 ? 's' : ''}</Text>
          <FlatList
            data={plays}
            keyExtractor={p => String(p.id)}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
            contentContainerStyle={{ padding: 12 }}
            ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
            ListEmptyComponent={<Text style={s.empty}>No plays logged yet.</Text>}
            renderItem={({ item: p }) => (
              <View style={s.card}>
                <View style={s.cardTop}>
                  <Text style={s.gameName} numberOfLines={1}>{p.game_name}</Text>
                  <View style={s.cardActions}>
                    <TouchableOpacity onPress={() => openLog(p)} style={s.iconBtn} accessibilityRole="button" accessibilityLabel={`Edit play of ${p.game_name}`}>
                      <Ionicons name="pencil-outline" size={17} color={NAVY} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => deletePlay(p)} style={s.iconBtn} accessibilityRole="button" accessibilityLabel={`Delete play of ${p.game_name}`}>
                      <Ionicons name="trash-outline" size={17} color="#b71c1c" />
                    </TouchableOpacity>
                  </View>
                </View>
                <Text style={s.date}>{p.played_at?.slice(0, 10)}</Text>
                {p.player_names     ? <Text style={s.detail}>👥 {p.player_names}</Text>         : null}
                {p.winner           ? <Text style={s.detail}>🏆 {p.winner}</Text>               : null}
                {p.duration_minutes ? <Text style={s.detail}>⏱ {p.duration_minutes} min</Text>  : null}
                {p.scores           ? <Text style={s.detail}>📊 {p.scores}</Text>               : null}
                {p.notes            ? <Text style={s.detail}>📝 {p.notes}</Text>                : null}
              </View>
            )}
          />
        </>
      )}

      {/* ── Log / Edit Play modal ────────────────────────────────────────── */}
      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setModalOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>{editingPlay ? 'Edit Play' : 'Log a Play'}</Text>
          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={s.label}>Game *</Text>
            <TouchableOpacity style={s.gamePicker} onPress={() => setPickingGame(true)}>
              <Text style={selGame ? s.gamePickerTxt : s.gamePickerPlaceholder}>
                {selGame ? selGame.name : '— select game —'}
              </Text>
              <Ionicons name="chevron-down" size={16} color="#9e9e9e" />
            </TouchableOpacity>

            <Text style={s.label}>Date *</Text>
            <DateInput value={date} onChange={setDate} />

            <Text style={s.label}>Players</Text>
            <PlayerPicker users={users} value={players} onChange={setPlayers} />

            <Text style={s.label}>Winner</Text>
            <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Name, All, or None" />

            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" />

            <Text style={s.label}>Scores</Text>
            <TextInput style={s.input} value={scores} onChangeText={setScores} placeholder='e.g. "Alice: 45, Bob: 37"' />

            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={notes} onChangeText={setNotes} />

            <TouchableOpacity style={s.sheetBtn} onPress={savePlay}>
              <Text style={s.sheetBtnTxt}>{editingPlay ? 'Save Changes' : 'Log Play'}</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>

      {/* Game picker modal */}
      <Modal visible={pickingGame} transparent animationType="slide" onRequestClose={() => { setPickingGame(false); setBggResults([]); setGameSearch(''); }} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => { setPickingGame(false); setBggResults([]); setGameSearch(''); }} />
        <View style={[s.sheet, { maxHeight: '85%' }]}>
          <Text style={s.sheetTitle}>Select Game</Text>
          <View style={s.pickerSearchRow}>
            <TextInput style={[s.input, { flex: 1, marginBottom: 0 }]} value={gameSearch} onChangeText={v => { setGameSearch(v); setBggResults([]); }} placeholder="Search your library…" autoFocus />
            <TouchableOpacity style={s.bggBtn} onPress={searchBGG} accessibilityLabel="Search BGG for this game">
              {bggSearching ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.bggBtnTxt}>BGG</Text>}
            </TouchableOpacity>
          </View>

          {/* Local results */}
          {bggResults.length === 0 && (
            <FlatList
              data={filteredGames}
              keyExtractor={g => String(g.bgg_id)}
              style={{ maxHeight: 240 }}
              ListEmptyComponent={gameSearch ? <Text style={s.pickerHint}>Not in library — tap BGG to search</Text> : null}
              renderItem={({ item: g }) => (
                <TouchableOpacity style={s.gameItem} onPress={() => { setSelGame(g); setPickingGame(false); setGameSearch(''); }}>
                  <Text style={s.gameItemTxt}>{g.name}</Text>
                  {g.year ? <Text style={s.gameItemYear}>{g.year}</Text> : null}
                </TouchableOpacity>
              )}
              ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: '#f0f0f0' }} />}
            />
          )}

          {/* BGG results */}
          {bggResults.length > 0 && (
            <>
              <Text style={s.pickerHint}>BGG results — tap to add & select</Text>
              <FlatList
                data={bggResults}
                keyExtractor={r => String(r.bgg_id)}
                style={{ maxHeight: 300 }}
                renderItem={({ item: r }) => (
                  <TouchableOpacity style={s.gameItem} onPress={() => addFromBGG(r)}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.gameItemTxt}>{r.name}</Text>
                      {r.year ? <Text style={s.gameItemYear}>{r.year}</Text> : null}
                    </View>
                    <Ionicons name="add-circle-outline" size={20} color={NAVY} />
                  </TouchableOpacity>
                )}
                ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: '#f0f0f0' }} />}
              />
            </>
          )}
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#fff' },
  count:        { paddingHorizontal: 14, paddingVertical: 6, color: '#9e9e9e', fontSize: 12 },
  card:         { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 4, elevation: 2 },
  cardTop:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  gameName:     { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 8 },
  cardActions:  { flexDirection: 'row', gap: 4 },
  iconBtn:      { padding: 4 },
  date:         { fontSize: 12, color: '#9e9e9e', marginBottom: 4 },
  detail:       { fontSize: 13, color: '#555', marginTop: 2 },
  empty:        { textAlign: 'center', color: '#9e9e9e', marginTop: 40, fontStyle: 'italic' },
  // Toggle
  toggle:       { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  toggleBtn:    { flex: 1, paddingVertical: 11, alignItems: 'center' },
  toggleActive: { borderBottomWidth: 3, borderBottomColor: NAVY },
  toggleTxt:    { fontSize: 14, color: '#9e9e9e', fontWeight: '600' },
  toggleTxtActive: { color: NAVY },
  // Leaderboard
  lbHeader:     { fontSize: 12, color: '#9e9e9e', marginBottom: 10 },
  lbRow:        { backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 8, flexDirection: 'row', alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 3, elevation: 1 },
  lbRowTop:     { shadowOpacity: 0.12, elevation: 3 },
  lbRank:       { fontSize: 16, width: 44, textAlign: 'center', color: '#6b7280', fontWeight: '600' },
  ribbon:       { width: 44, height: 44, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
                  shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 3, elevation: 3 },
  ribbonTxt:    { color: '#fff', fontWeight: '900', fontSize: 13, letterSpacing: 0.5 },
  lbInfo:       { flex: 1, marginLeft: 8 },
  lbNameRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  lbName:       { fontSize: 15, color: '#333', flex: 1 },
  lbNameBold:   { fontWeight: '700', fontSize: 16 },
  lbWins:       { fontSize: 13, color: '#6b7280', fontWeight: '600' },
  lbBarBg:      { height: 6, backgroundColor: '#f0f0f0', borderRadius: 3, overflow: 'hidden' },
  lbBarFill:    { height: 6, borderRadius: 3 },
  // Modal/sheet
  overlay:      { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet:        { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 44, maxHeight: '90%' },
  sheetTitle:   { fontSize: 18, fontWeight: '700', color: NAVY, marginBottom: 16 },
  label:        { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input:        { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  gamePicker:   { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, marginBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gamePickerTxt: { fontSize: 15, color: '#333' },
  gamePickerPlaceholder: { fontSize: 15, color: '#aaa' },
  sheetBtn:     { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4, marginBottom: 8 },
  sheetBtnTxt:  { color: '#fff', fontWeight: '700', fontSize: 15 },
  gameItem:       { paddingVertical: 12, paddingHorizontal: 4, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gameItemTxt:    { fontSize: 15, flex: 1 },
  gameItemYear:   { fontSize: 13, color: '#9e9e9e' },
  pickerSearchRow:{ flexDirection: 'row', gap: 8, marginBottom: 10, alignItems: 'center' },
  bggBtn:         { backgroundColor: NAVY, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, justifyContent: 'center', minWidth: 52, alignItems: 'center' },
  bggBtnTxt:      { color: '#fff', fontWeight: '700', fontSize: 13 },
  pickerHint:     { fontSize: 12, color: '#9e9e9e', fontStyle: 'italic', paddingVertical: 8, textAlign: 'center' },
});
