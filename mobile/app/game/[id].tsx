import { useCallback, useState } from 'react';
import { View, Text, ScrollView, Image, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Platform } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Game, Loan, Play, User } from '../../lib/types';

const NAVY = '#1a237e';

export default function GameDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const bggId = parseInt(id, 10);

  const [game, setGame] = useState<Game | null>(null);
  const [loan, setLoan] = useState<Loan | null>(null);
  const [plays, setPlays] = useState<Play[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [checkoutModal, setCheckoutModal] = useState(false);
  const [playModal, setPlayModal] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [dueDate, setDueDate] = useState('');
  const [playDate, setPlayDate] = useState(new Date().toISOString().slice(0, 10));
  const [players, setPlayers] = useState('');
  const [winner, setWinner] = useState('');
  const [duration, setDuration] = useState('');
  const [notes, setNotes] = useState('');

  const load = useCallback(() => {
    setGame(db.getGame(bggId));
    setLoan(db.openLoanForGame(bggId));
    setPlays(db.listPlays(bggId));
    setUsers(db.listUsers());
  }, [bggId]);

  // Load on mount and focus
  useState(() => { load(); });

  if (!game) return <View style={s.center}><Text>Loading…</Text></View>;

  const today = new Date().toISOString().slice(0, 10);
  const overdue = !!(loan?.due_date && loan.due_date < today);

  const doCheckOut = () => {
    if (!selectedUserId) { Alert.alert('Select a member first'); return; }
    try {
      db.checkOut(bggId, selectedUserId, '', dueDate || undefined);
      setCheckoutModal(false);
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const doCheckIn = () => {
    Alert.alert('Check In', `Mark "${game.name}" as returned?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Check In', onPress: () => { db.checkIn(bggId); load(); } },
    ]);
  };

  const doLogPlay = () => {
    if (!playDate) { Alert.alert('Date is required'); return; }
    db.logPlay(bggId, playDate, players, winner, notes, duration ? parseInt(duration) : undefined);
    setPlayModal(false);
    setPlayers(''); setWinner(''); setDuration(''); setNotes('');
    load();
  };

  const toggleFavorite = () => { db.setFavorite(bggId, !game.is_favorite); load(); };

  return (
    <ScrollView style={s.scroll} contentContainerStyle={{ paddingBottom: 40 }}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}>
          <Ionicons name="arrow-back" size={22} color="#fff" />
        </TouchableOpacity>
        <Text style={s.headerTitle} numberOfLines={1}>{game.name}</Text>
        <TouchableOpacity onPress={toggleFavorite} style={s.back}>
          <Ionicons name={game.is_favorite ? 'star' : 'star-outline'} size={22} color="#f0c674" />
        </TouchableOpacity>
      </View>

      <View style={s.detailHeader}>
        {game.thumbnail_url
          ? <Image source={{ uri: game.thumbnail_url }} style={s.boxArt} />
          : <View style={[s.boxArt, s.boxArtEmpty]}><Text style={{ fontSize: 40 }}>🎲</Text></View>}
        <View style={s.detailInfo}>
          <Text style={s.detailName}>{game.name}</Text>
          {game.year ? <Text style={s.detailMeta}>{game.year}</Text> : null}
          {game.min_players && game.max_players
            ? <Text style={s.detailMeta}>{game.min_players}–{game.max_players} players</Text> : null}
          {game.playing_time ? <Text style={s.detailMeta}>{game.playing_time} min</Text> : null}
          {game.weight ? <Text style={s.detailMeta}>Complexity {game.weight.toFixed(1)}/5</Text> : null}
          {game.avg_rating ? <Text style={s.detailMeta}>BGG ★ {game.avg_rating.toFixed(1)}</Text> : null}
        </View>
      </View>

      {/* Status banner */}
      <View style={[s.banner, loan ? (overdue ? s.bannerOverdue : s.bannerOut) : s.bannerIn]}>
        <Text style={[s.bannerTxt, loan ? (overdue ? s.txtRed : s.txtBrown) : s.txtGreen]}>
          {loan
            ? `${overdue ? '⚠ OVERDUE — ' : ''}Out: ${loan.first_name} ${loan.last_name} · ${loan.checked_out_at.slice(0, 10)}`
            : 'Available'}
        </Text>
        {loan
          ? <TouchableOpacity style={s.bannerBtn} onPress={doCheckIn}><Text style={s.bannerBtnTxt}>Check In</Text></TouchableOpacity>
          : users.length > 0 && <TouchableOpacity style={s.bannerBtn} onPress={() => setCheckoutModal(true)}><Text style={s.bannerBtnTxt}>Check Out</Text></TouchableOpacity>}
      </View>

      <TouchableOpacity style={s.logPlayBtn} onPress={() => setPlayModal(true)}>
        <Ionicons name="trophy-outline" size={16} color="#fff" />
        <Text style={s.logPlayTxt}>Log Play</Text>
      </TouchableOpacity>

      {/* Play history */}
      {plays.length > 0 && (
        <View style={s.card}>
          <Text style={s.sectionTitle}>Play History ({plays.length})</Text>
          {plays.slice(0, 10).map(p => (
            <View key={p.id} style={s.playRow}>
              <Text style={s.playDate}>{p.played_at.slice(0, 10)}</Text>
              <View style={{ flex: 1 }}>
                {p.player_names ? <Text style={s.playTxt}>{p.player_names}</Text> : null}
                {p.winner ? <Text style={s.playTxt}>🏆 {p.winner}</Text> : null}
              </View>
              {p.duration_minutes ? <Text style={s.playMeta}>{p.duration_minutes}m</Text> : null}
            </View>
          ))}
        </View>
      )}

      {/* Description */}
      {game.description ? (
        <View style={s.card}>
          <Text style={s.sectionTitle}>About</Text>
          <Text style={s.desc}>{game.description.slice(0, 600)}{game.description.length > 600 ? '…' : ''}</Text>
        </View>
      ) : null}

      {/* Check-out modal */}
      <Modal visible={checkoutModal} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setCheckoutModal(false)}>
        <View style={s.modal}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Check Out — {game.name}</Text>
            <TouchableOpacity onPress={() => setCheckoutModal(false)}><Ionicons name="close" size={24} color="#333" /></TouchableOpacity>
          </View>
          <ScrollView style={s.modalBody}>
            <Text style={s.label}>Member</Text>
            {users.map(u => (
              <TouchableOpacity key={u.id} style={[s.userRow, selectedUserId === u.id && s.userRowSel]} onPress={() => setSelectedUserId(u.id)}>
                <Text style={[s.userTxt, selectedUserId === u.id && s.userTxtSel]}>{u.first_name} {u.last_name}</Text>
                {selectedUserId === u.id && <Ionicons name="checkmark" size={18} color={NAVY} />}
              </TouchableOpacity>
            ))}
            <Text style={[s.label, { marginTop: 14 }]}>Due Date (optional, YYYY-MM-DD)</Text>
            <TextInput style={s.input} value={dueDate} onChangeText={setDueDate} placeholder="2025-12-31" />
          </ScrollView>
          <TouchableOpacity style={s.primaryBtn} onPress={doCheckOut}>
            <Text style={s.primaryBtnTxt}>Check Out</Text>
          </TouchableOpacity>
        </View>
      </Modal>

      {/* Log Play modal */}
      <Modal visible={playModal} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setPlayModal(false)}>
        <View style={s.modal}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Log Play — {game.name}</Text>
            <TouchableOpacity onPress={() => setPlayModal(false)}><Ionicons name="close" size={24} color="#333" /></TouchableOpacity>
          </View>
          <ScrollView style={s.modalBody}>
            <Text style={s.label}>Date Played</Text>
            <TextInput style={s.input} value={playDate} onChangeText={setPlayDate} placeholder="YYYY-MM-DD" />
            <Text style={s.label}>Players (comma-separated)</Text>
            <TextInput style={s.input} value={players} onChangeText={setPlayers} placeholder="Alice, Bob" />
            <Text style={s.label}>Winner</Text>
            <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Alice" />
            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" />
            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={notes} onChangeText={setNotes} multiline />
          </ScrollView>
          <TouchableOpacity style={s.primaryBtn} onPress={doLogPlay}>
            <Text style={s.primaryBtnTxt}>Log Play</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: '#f4f6fa' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', padding: 12, paddingTop: Platform.OS === 'ios' ? 50 : 12 },
  back: { padding: 6 },
  headerTitle: { flex: 1, color: '#fff', fontWeight: '700', fontSize: 17, textAlign: 'center' },
  detailHeader: { flexDirection: 'row', padding: 14, gap: 12, backgroundColor: '#fff' },
  boxArt: { width: 100, height: 100, borderRadius: 8 },
  boxArtEmpty: { backgroundColor: '#e8eaf6', alignItems: 'center', justifyContent: 'center' },
  detailInfo: { flex: 1 },
  detailName: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  detailMeta: { fontSize: 13, color: '#6b7280', marginBottom: 2 },
  banner: { flexDirection: 'row', alignItems: 'center', padding: 12, margin: 10, borderRadius: 10, gap: 10 },
  bannerIn: { backgroundColor: '#e8f5e9' },
  bannerOut: { backgroundColor: '#fff8e1' },
  bannerOverdue: { backgroundColor: '#ffebee' },
  bannerTxt: { flex: 1, fontSize: 13, fontWeight: '600' },
  txtGreen: { color: '#1b5e20' },
  txtBrown: { color: '#795548' },
  txtRed: { color: '#b71c1c' },
  bannerBtn: { backgroundColor: 'rgba(0,0,0,.1)', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6 },
  bannerBtnTxt: { fontWeight: '700', fontSize: 13 },
  logPlayBtn: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', marginHorizontal: 10, marginBottom: 10, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  logPlayTxt: { color: '#fff', fontWeight: '600', fontSize: 14 },
  card: { backgroundColor: '#fff', margin: 10, marginTop: 0, borderRadius: 10, padding: 14, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: NAVY, marginBottom: 8 },
  playRow: { flexDirection: 'row', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#f0f0f0', alignItems: 'flex-start' },
  playDate: { fontSize: 12, color: '#9e9e9e', width: 80 },
  playTxt: { fontSize: 13, color: '#333' },
  playMeta: { fontSize: 12, color: '#9e9e9e' },
  desc: { fontSize: 13, color: '#444', lineHeight: 20 },
  modal: { flex: 1, backgroundColor: '#fff' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 17, fontWeight: '700', flex: 1 },
  modalBody: { flex: 1, padding: 16 },
  label: { fontSize: 13, fontWeight: '600', color: '#333', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  userRow: { flexDirection: 'row', alignItems: 'center', padding: 12, borderRadius: 8, borderWidth: 1, borderColor: '#e5e7eb', marginBottom: 6 },
  userRowSel: { borderColor: NAVY, backgroundColor: '#e8eaf6' },
  userTxt: { flex: 1, fontSize: 15, color: '#333' },
  userTxtSel: { color: NAVY, fontWeight: '600' },
  primaryBtn: { backgroundColor: NAVY, margin: 16, padding: 14, borderRadius: 10, alignItems: 'center' },
  primaryBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
