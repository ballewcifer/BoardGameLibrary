import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Pressable, RefreshControl, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Play, Game, User } from '../../lib/types';
import PlayerPicker from '../../components/PlayerPicker';

const NAVY = '#1a237e';

export default function Plays({ isActive = true }: { isActive?: boolean }) {
  const [plays, setPlays]           = useState<Play[]>([]);
  const [games, setGames]           = useState<Game[]>([]);
  const [users, setUsers]           = useState<User[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [modalOpen, setModalOpen]   = useState(false);

  // Log play form
  const [selGame, setSelGame]   = useState<Game | null>(null);
  const [date, setDate]         = useState('');
  const [players, setPlayers]   = useState('');
  const [winner, setWinner]     = useState('');
  const [duration, setDuration] = useState('');
  const [notes, setNotes]       = useState('');
  const [pickingGame, setPickingGame] = useState(false);
  const [gameSearch, setGameSearch]   = useState('');

  const load = useCallback(() => {
    setPlays(db.listPlays());
    setGames(db.listGames());
    setUsers(db.listUsers());
  }, []);
  useEffect(() => { if (isActive) load(); }, [isActive]);

  const openLog = () => {
    setDate(new Date().toISOString().slice(0, 10));
    setPlayers(''); setWinner(''); setDuration(''); setNotes('');
    setSelGame(null);
    setModalOpen(true);
  };

  const savePlay = () => {
    if (!selGame) { Alert.alert('Select a game'); return; }
    if (!date)    { Alert.alert('Date required'); return; }
    db.logPlay(selGame.bgg_id, date, players, winner, notes,
      duration ? parseInt(duration, 10) : undefined);
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

  return (
    <View style={s.container}>
      <TouchableOpacity style={s.addBtn} onPress={openLog}>
        <Ionicons name="add-circle-outline" size={18} color="#fff" />
        <Text style={s.addBtnTxt}>Log Play</Text>
      </TouchableOpacity>

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
              <TouchableOpacity onPress={() => deletePlay(p)} style={{ padding: 4 }}>
                <Ionicons name="trash-outline" size={18} color="#b71c1c" />
              </TouchableOpacity>
            </View>
            <Text style={s.date}>{p.played_at?.slice(0, 10)}</Text>
            {p.player_names ? <Text style={s.detail}>👥 {p.player_names}</Text> : null}
            {p.winner       ? <Text style={s.detail}>🏆 {p.winner}</Text>       : null}
            {p.duration_minutes ? <Text style={s.detail}>⏱ {p.duration_minutes} min</Text> : null}
            {p.scores       ? <Text style={s.detail}>📊 {p.scores}</Text>       : null}
            {p.notes        ? <Text style={s.detail}>📝 {p.notes}</Text>        : null}
          </View>
        )}
      />

      {/* Log Play modal */}
      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setModalOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Log a Play</Text>
          <ScrollView showsVerticalScrollIndicator={false}>
            {/* Game picker */}
            <Text style={s.label}>Game *</Text>
            <TouchableOpacity style={s.gamePicker} onPress={() => setPickingGame(true)}>
              <Text style={selGame ? s.gamePickerTxt : s.gamePickerPlaceholder}>
                {selGame ? selGame.name : '— select game —'}
              </Text>
              <Ionicons name="chevron-down" size={16} color="#9e9e9e" />
            </TouchableOpacity>

            <Text style={s.label}>Date *</Text>
            <TextInput style={s.input} value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" />

            <Text style={s.label}>Players</Text>
            <PlayerPicker users={users} value={players} onChange={setPlayers} />

            <Text style={s.label}>Winner</Text>
            <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Alice" />

            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" />

            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={notes} onChangeText={setNotes} placeholder="Optional" />

            <TouchableOpacity style={s.sheetBtn} onPress={savePlay}>
              <Text style={s.sheetBtnTxt}>Save Play</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>

      {/* Game search modal */}
      <Modal visible={pickingGame} transparent animationType="slide" onRequestClose={() => setPickingGame(false)}>
        <Pressable style={s.overlay} onPress={() => setPickingGame(false)} />
        <View style={[s.sheet, { maxHeight: '80%' }]}>
          <Text style={s.sheetTitle}>Select Game</Text>
          <TextInput style={[s.input, { marginBottom: 8 }]} value={gameSearch} onChangeText={setGameSearch} placeholder="Search…" autoFocus />
          <FlatList
            data={filteredGames}
            keyExtractor={g => String(g.bgg_id)}
            renderItem={({ item: g }) => (
              <TouchableOpacity style={s.gameItem} onPress={() => { setSelGame(g); setPickingGame(false); setGameSearch(''); }}>
                <Text style={s.gameItemTxt}>{g.name}</Text>
                {g.year ? <Text style={s.gameItemYear}>{g.year}</Text> : null}
              </TouchableOpacity>
            )}
            ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: '#f0f0f0' }} />}
          />
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: NAVY, margin: 12, borderRadius: 10, padding: 12, justifyContent: 'center' },
  addBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  count: { paddingHorizontal: 14, paddingBottom: 4, color: '#9e9e9e', fontSize: 12 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 4, elevation: 2 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  gameName: { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 8 },
  date: { fontSize: 12, color: '#9e9e9e', marginBottom: 4 },
  detail: { fontSize: 13, color: '#555', marginTop: 2 },
  empty: { textAlign: 'center', color: '#9e9e9e', marginTop: 40, fontStyle: 'italic' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  sheetTitle: { fontSize: 18, fontWeight: '700', marginBottom: 16, color: NAVY },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  gamePicker: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, marginBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gamePickerTxt: { fontSize: 15, color: '#333' },
  gamePickerPlaceholder: { fontSize: 15, color: '#aaa' },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4, marginBottom: 8 },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  gameItem: { paddingVertical: 12, paddingHorizontal: 4, flexDirection: 'row', justifyContent: 'space-between' },
  gameItemTxt: { fontSize: 15, flex: 1 },
  gameItemYear: { fontSize: 13, color: '#9e9e9e' },
});
