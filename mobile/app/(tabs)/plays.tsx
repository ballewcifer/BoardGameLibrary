import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Pressable, RefreshControl, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import * as bgg from '../../lib/bgg';
import { loadSettings } from '../../lib/settings';
import { useFocusEffect } from 'expo-router';
import type { Play, Game, User } from '../../lib/types';
import PlayerPicker from '../../components/PlayerPicker';
import WinnerPicker from '../../components/WinnerPicker';
import ScreenHeader from '../../components/ScreenHeader';
import DateInput from '../../components/DateInput';
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
  dangerText: '#B3261E', dangerBg:'#FCEBEA',dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg: '#E7F0FB',
  starText:   '#B07A00', starFill:'#F2A900',
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

export default function Plays({ isActive = true }: { isActive?: boolean }) {
  const [plays, setPlays]           = useState<Play[]>([]);
  const [games, setGames]           = useState<Game[]>([]);
  const [users, setUsers]           = useState<User[]>([]);
  const [winners, setWinners]       = useState<{ winner: string; win_count: number }[]>([]);
  const [view, setView]             = useState<'log' | 'leaderboard'>('log');
  const [refreshing, setRefreshing] = useState(false);
  const [modalOpen, setModalOpen]   = useState(false);
  const [editingPlay, setEditingPlay] = useState<Play | null>(null);

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
    setGames(db.listGames('', false));
    setUsers(db.listUsers());
    setWinners(db.topWinners(0));
  }, []);
  useFocusEffect(useCallback(() => { if (isActive) load(); }, [isActive, load]));

  const openLog = (p?: Play) => {
    if (p) {
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
        own: 0,
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
          contentContainerStyle={{ padding: SP.lg, backgroundColor: DS.bg }}
          ListEmptyComponent={<Text style={s.empty}>No wins recorded yet. Log some plays!</Text>}
          ListHeaderComponent={
            <Text style={s.lbHeader}>
              {winners.length} player{winners.length !== 1 ? 's' : ''} · {plays.length} play{plays.length !== 1 ? 's' : ''} total
            </Text>
          }
          renderItem={({ item: w, index }) => {
            const topThree = index < 3;
            const maxWins = winners[0]?.win_count ?? 1;
            const pct = Math.round((w.win_count / maxWins) * 100);
            return (
              <View style={[s.lbRow, topThree && s.lbRowTop]}>
                {topThree ? (
                  <RibbonBadge rank={(index + 1) as 1 | 2 | 3} />
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
                      backgroundColor: index === 0 ? DS.starFill : index === 1 ? '#AAB8C2' : index === 2 ? '#CD7F32' : DS.blue600 }]} />
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
            contentContainerStyle={{ padding: SP.md, backgroundColor: DS.bg }}
            ItemSeparatorComponent={() => <View style={{ height: SP.sm }} />}
            ListEmptyComponent={<Text style={s.empty}>No plays logged yet.</Text>}
            renderItem={({ item: p }) => (
              <View style={s.card}>
                <View style={s.cardTop}>
                  <Text style={s.gameName} numberOfLines={1}>{p.game_name}</Text>
                  <View style={s.cardActions}>
                    <TouchableOpacity onPress={() => openLog(p)} style={s.iconBtn} accessibilityRole="button" accessibilityLabel={`Edit play of ${p.game_name}`}>
                      <Ionicons name="pencil-outline" size={17} color={DS.blue600} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => deletePlay(p)} style={s.iconBtn} accessibilityRole="button" accessibilityLabel={`Delete play of ${p.game_name}`}>
                      <Ionicons name="trash-outline" size={17} color={DS.dangerSolid} />
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
        <KeyboardAvoidingView style={s.modalRoot} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Pressable style={s.overlay} onPress={() => setModalOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>{editingPlay ? 'Edit Play' : 'Log a Play'}</Text>
          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={s.label}>Game *</Text>
            <TouchableOpacity style={s.gamePicker} onPress={() => setPickingGame(true)}>
              <Text style={selGame ? s.gamePickerTxt : s.gamePickerPlaceholder}>
                {selGame ? selGame.name : '— select game —'}
              </Text>
              <Ionicons name="chevron-down" size={16} color={DS.ink500} />
            </TouchableOpacity>

            <Text style={s.label}>Date *</Text>
            <DateInput value={date} onChange={setDate} />

            <Text style={s.label}>Players</Text>
            <PlayerPicker users={users} value={players} onChange={setPlayers} />

            <Text style={s.label}>Winner</Text>
            <WinnerPicker players={players} value={winner} onChange={setWinner} />

            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" placeholderTextColor={DS.ink500} />

            <Text style={s.label}>Scores</Text>
            <TextInput style={s.input} value={scores} onChangeText={setScores} placeholder='e.g. "Alice: 45, Bob: 37"' placeholderTextColor={DS.ink500} />

            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={notes} onChangeText={setNotes} placeholderTextColor={DS.ink500} />

            <TouchableOpacity style={s.sheetBtn} onPress={savePlay}>
              <Text style={s.sheetBtnTxt}>{editingPlay ? 'Save Changes' : 'Log Play'}</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Game picker modal */}
      <Modal visible={pickingGame} transparent animationType="slide" onRequestClose={() => { setPickingGame(false); setBggResults([]); setGameSearch(''); }} accessibilityViewIsModal={true}>
        <KeyboardAvoidingView style={s.modalRoot} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Pressable style={s.overlay} onPress={() => { setPickingGame(false); setBggResults([]); setGameSearch(''); }} />
        <View style={[s.sheet, { maxHeight: '85%' }]}>
          <Text style={s.sheetTitle}>Select Game</Text>
          <View style={s.pickerSearchRow}>
            <TextInput style={[s.input, { flex: 1, marginBottom: 0 }]} value={gameSearch} onChangeText={v => { setGameSearch(v); setBggResults([]); }} placeholder="Search your library…" placeholderTextColor={DS.ink500} autoFocus />
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
              ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: DS.line100 }} />}
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
                    <Ionicons name="add-circle-outline" size={20} color={DS.blue600} />
                  </TouchableOpacity>
                )}
                ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: DS.line100 }} />}
              />
            </>
          )}
        </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: DS.bg },
  count:        { paddingHorizontal: SP.lg, paddingVertical: SP.sm, color: DS.ink500, fontSize: 12 },
  card:         { backgroundColor: DS.surface, borderRadius: R.lg, borderWidth: 1, borderColor: DS.line200, padding: SP.lg, shadowColor: 'rgba(16,32,47,0.08)', shadowOpacity: 1, shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, elevation: 2 },
  cardTop:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SP.xs },
  gameName:     { fontSize: 15, fontWeight: '700', color: DS.ink900, flex: 1, marginRight: SP.sm },
  cardActions:  { flexDirection: 'row', gap: SP.xs },
  iconBtn:      { padding: SP.xs },
  date:         { fontSize: 12, color: DS.ink500, marginBottom: SP.xs },
  detail:       { fontSize: 13, color: DS.ink600, marginTop: SP.xs },
  empty:        { textAlign: 'center', color: DS.ink500, marginTop: 40, fontStyle: 'italic' },
  // Toggle
  toggle:       { flexDirection: 'row', backgroundColor: DS.surface, borderBottomWidth: 1, borderBottomColor: DS.line200 },
  toggleBtn:    { flex: 1, paddingVertical: 11, alignItems: 'center' },
  toggleActive: { borderBottomWidth: 3, borderBottomColor: DS.blue600 },
  toggleTxt:    { fontSize: 14, color: DS.ink500, fontWeight: '600' },
  toggleTxtActive: { color: DS.blue600 },
  // Leaderboard
  lbHeader:     { fontSize: 12, color: DS.ink500, marginBottom: SP.md },
  lbRow:        { backgroundColor: DS.surface, borderRadius: R.lg, borderWidth: 1, borderColor: DS.line200, padding: SP.lg, marginBottom: SP.sm, flexDirection: 'row', alignItems: 'center', shadowColor: 'rgba(16,32,47,0.08)', shadowOpacity: 1, shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, elevation: 1 },
  lbRowTop:     { shadowColor: 'rgba(16,32,47,0.10)', shadowOffset: { width: 0, height: 4 }, shadowRadius: 12, elevation: 3 },
  lbRank:       { fontSize: 16, width: 64, textAlign: 'center', color: DS.ink500, fontWeight: '600' },
  lbInfo:       { flex: 1, marginLeft: SP.sm },
  lbNameRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SP.sm },
  lbName:       { fontSize: 15, color: DS.ink900, flex: 1 },
  lbNameBold:   { fontWeight: '700', fontSize: 16, color: DS.ink900 },
  lbWins:       { fontSize: 13, color: DS.ink600, fontWeight: '600' },
  lbBarBg:      { height: 6, backgroundColor: DS.line200, borderRadius: R.pill, overflow: 'hidden' },
  lbBarFill:    { height: 6, borderRadius: R.pill },
  // Modal/sheet
  modalRoot:    { flex: 1 },
  overlay:      { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },
  sheet:        { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: SP.xxl, paddingBottom: 44, maxHeight: '90%' },
  sheetTitle:   { fontSize: 17, fontWeight: '700', color: DS.ink900, marginBottom: SP.lg },
  label:        { fontSize: 12, fontWeight: '700', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: SP.xs, color: DS.ink600 },
  input:        { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, fontSize: 15, marginBottom: SP.md, color: DS.ink900, backgroundColor: DS.surface },
  gamePicker:   { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, marginBottom: SP.md, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: DS.surface },
  gamePickerTxt: { fontSize: 15, color: DS.ink900 },
  gamePickerPlaceholder: { fontSize: 15, color: DS.ink500 },
  sheetBtn:     { backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.lg, alignItems: 'center', marginTop: SP.xs, marginBottom: SP.sm },
  sheetBtnTxt:  { color: '#fff', fontWeight: '700', fontSize: 15 },
  gameItem:       { paddingVertical: SP.md, paddingHorizontal: SP.xs, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gameItemTxt:    { fontSize: 15, flex: 1, color: DS.ink900 },
  gameItemYear:   { fontSize: 13, color: DS.ink500 },
  pickerSearchRow:{ flexDirection: 'row', gap: SP.sm, marginBottom: SP.md, alignItems: 'center' },
  bggBtn:         { backgroundColor: DS.blue600, borderRadius: R.md, paddingHorizontal: SP.lg, paddingVertical: SP.md, justifyContent: 'center', minWidth: 52, alignItems: 'center' },
  bggBtnTxt:      { color: '#fff', fontWeight: '700', fontSize: 13 },
  pickerHint:     { fontSize: 12, color: DS.ink500, fontStyle: 'italic', paddingVertical: SP.sm, textAlign: 'center' },
});
