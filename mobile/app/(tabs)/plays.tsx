import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, RefreshControl } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Play, Game } from '../../lib/types';

const NAVY = '#1a237e';

export default function Plays() {
  const [plays, setPlays] = useState<Play[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [modal, setModal] = useState(false);
  const [selectedGame, setSelectedGame] = useState<number | null>(null);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [players, setPlayers] = useState('');
  const [winner, setWinner] = useState('');
  const [duration, setDuration] = useState('');
  const [notes, setNotes] = useState('');
  const [gameSearch, setGameSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    setPlays(db.listPlays());
    setGames(db.listGames());
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = () => { setRefreshing(true); load(); setRefreshing(false); };

  const openModal = () => {
    setSelectedGame(null); setDate(new Date().toISOString().slice(0, 10));
    setPlayers(''); setWinner(''); setDuration(''); setNotes(''); setGameSearch('');
    setModal(true);
  };

  const savePlay = () => {
    if (!selectedGame) { Alert.alert('Select a game first'); return; }
    if (!date) { Alert.alert('Date is required'); return; }
    db.logPlay(selectedGame, date, players, winner, notes, duration ? parseInt(duration) : undefined);
    setModal(false);
    load();
  };

  const deletePlay = (p: Play) => {
    Alert.alert('Delete Play', 'Remove this play record?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => { db.deletePlay(p.id); load(); } },
    ]);
  };

  const filteredGames = games.filter(g => g.name.toLowerCase().includes(gameSearch.toLowerCase()));

  return (
    <View style={s.container}>
      <View style={s.topBar}>
        <Text style={s.count}>{plays.length} play{plays.length !== 1 ? 's' : ''}</Text>
        <TouchableOpacity style={s.addBtn} onPress={openModal}>
          <Ionicons name="add" size={16} color="#fff" />
          <Text style={s.addTxt}>Log Play</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={plays}
        keyExtractor={p => String(p.id)}
        renderItem={({ item: p }) => (
          <View style={s.card}>
            <View style={s.cardTop}>
              <Text style={s.gameName} numberOfLines={1}>{p.game_name}</Text>
              <Text style={s.dateVal}>{p.played_at.slice(0, 10)}</Text>
            </View>
            {p.player_names ? <Text style={s.detail}>{p.player_names}</Text> : null}
            {p.winner ? <Text style={s.detail}>🏆 {p.winner}</Text> : null}
            <View style={s.cardBottom}>
              {p.duration_minutes ? <Text style={s.meta}>{p.duration_minutes} min</Text> : null}
              {p.scores ? <Text style={s.meta}>{p.scores}</Text> : null}
              <TouchableOpacity style={s.delBtn} onPress={() => deletePlay(p)}>
                <Ionicons name="trash-outline" size={16} color="#e53935" />
              </TouchableOpacity>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ padding: 10, gap: 8 }}
        ListEmptyComponent={<Text style={s.empty}>No plays logged yet.</Text>}
      />

      {/* Log Play modal */}
      <Modal visible={modal} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setModal(false)}>
        <View style={s.modal}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Log a Play</Text>
            <TouchableOpacity onPress={() => setModal(false)}><Ionicons name="close" size={24} color="#333" /></TouchableOpacity>
          </View>
          <FlatList
            data={[]}
            ListHeaderComponent={
              <View style={s.modalBody}>
                <Text style={s.label}>Game</Text>
                <TextInput style={s.input} value={gameSearch} onChangeText={setGameSearch} placeholder="Search games…" />
                {filteredGames.slice(0, 8).map(g => (
                  <TouchableOpacity key={g.bgg_id} style={[s.gameRow, selectedGame === g.bgg_id && s.gameRowSel]} onPress={() => setSelectedGame(g.bgg_id)}>
                    <Text style={[s.gameTxt, selectedGame === g.bgg_id && s.gameTxtSel]}>{g.name}</Text>
                    {selectedGame === g.bgg_id && <Ionicons name="checkmark" size={18} color={NAVY} />}
                  </TouchableOpacity>
                ))}
                <Text style={[s.label, { marginTop: 14 }]}>Date Played</Text>
                <TextInput style={s.input} value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" />
                <Text style={s.label}>Players (comma-separated)</Text>
                <TextInput style={s.input} value={players} onChangeText={setPlayers} placeholder="Alice, Bob" />
                <Text style={s.label}>Winner</Text>
                <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Alice, All, or None" />
                <Text style={s.label}>Duration (minutes)</Text>
                <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" />
                <Text style={s.label}>Notes</Text>
                <TextInput style={s.input} value={notes} onChangeText={setNotes} multiline />
              </View>
            }
            renderItem={() => null}
            keyExtractor={() => '0'}
          />
          <TouchableOpacity style={s.primaryBtn} onPress={savePlay}>
            <Text style={s.primaryBtnTxt}>Log Play</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12 },
  count: { color: '#6b7280', fontSize: 13 },
  addBtn: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  addTxt: { color: '#fff', fontWeight: '600', fontSize: 14 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 },
  gameName: { fontSize: 15, fontWeight: '700', flex: 1, marginRight: 8 },
  dateVal: { fontSize: 12, color: '#9e9e9e' },
  detail: { fontSize: 13, color: '#444', marginBottom: 2 },
  cardBottom: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 },
  meta: { fontSize: 12, color: '#9e9e9e', flex: 1 },
  delBtn: { padding: 4 },
  empty: { textAlign: 'center', color: '#9e9e9e', padding: 40, fontSize: 14 },
  modal: { flex: 1, backgroundColor: '#fff' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 17, fontWeight: '700' },
  modalBody: { padding: 16 },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 8 },
  gameRow: { flexDirection: 'row', alignItems: 'center', padding: 10, borderRadius: 8, borderWidth: 1, borderColor: '#e5e7eb', marginBottom: 4 },
  gameRowSel: { borderColor: NAVY, backgroundColor: '#e8eaf6' },
  gameTxt: { flex: 1, fontSize: 14, color: '#333' },
  gameTxtSel: { color: NAVY, fontWeight: '600' },
  primaryBtn: { backgroundColor: NAVY, margin: 16, padding: 14, borderRadius: 10, alignItems: 'center' },
  primaryBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
