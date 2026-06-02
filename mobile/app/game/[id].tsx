import { useCallback, useState } from 'react';
import { View, Text, ScrollView, Image, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Pressable } from 'react-native';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Game, Loan, User } from '../../lib/types';
import PlayerPicker from '../../components/PlayerPicker';

const NAVY = '#1a237e';

export default function GameDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const bggId = parseInt(id, 10);

  const [game, setGame]       = useState<Game | null>(null);
  const [loan, setLoan]       = useState<Loan | null>(null);
  const [users, setUsers]     = useState<User[]>([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [logPlayOpen, setLogPlayOpen]   = useState(false);

  // Checkout form
  const [selUserId, setSelUserId] = useState<number | null>(null);
  const [dueDate, setDueDate]     = useState('');
  const [coNotes, setCoNotes]     = useState('');
  const [pickingUser, setPickingUser] = useState(false);

  // Log play form
  const [playDate, setPlayDate]       = useState('');
  const [players, setPlayers]         = useState('');
  const [winner, setWinner]           = useState('');
  const [duration, setDuration]       = useState('');
  const [playNotes, setPlayNotes]     = useState('');

  const load = useCallback(() => {
    setGame(db.getGame(bggId));
    setLoan(db.openLoanForGame(bggId));
    setUsers(db.listUsers());
  }, [bggId]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (!game) return <View style={s.container}><Text style={s.empty}>Game not found.</Text></View>;

  const today = new Date().toISOString().slice(0, 10);
  const overdue = !!(loan?.due_date && loan.due_date < today);

  const checkOut = () => {
    if (!selUserId) { Alert.alert('Select a member'); return; }
    try {
      db.checkOut(bggId, selUserId, coNotes, dueDate || undefined);
      setCheckoutOpen(false);
      setSelUserId(null); setDueDate(''); setCoNotes('');
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const checkIn = () => {
    Alert.alert('Check in', `Mark "${game.name}" as returned?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Check In', onPress: () => { try { db.checkIn(bggId); load(); } catch (e: any) { Alert.alert('Error', e.message); } } },
    ]);
  };

  const savePlay = () => {
    if (!playDate) { Alert.alert('Date required'); return; }
    db.logPlay(bggId, playDate, players, winner, playNotes, duration ? parseInt(duration, 10) : undefined);
    setLogPlayOpen(false);
    setPlayers(''); setWinner(''); setDuration(''); setPlayNotes('');
  };

  const selUser = users.find(u => u.id === selUserId);

  return (
    <View style={s.container}>
      {/* Back button */}
      <TouchableOpacity style={s.back} onPress={() => router.back()}>
        <Ionicons name="arrow-back" size={22} color={NAVY} />
        <Text style={s.backTxt}>Games</Text>
      </TouchableOpacity>

      <ScrollView contentContainerStyle={s.scroll}>
        {/* Header */}
        <View style={s.headerRow}>
          {game.thumbnail_url
            ? <Image source={{ uri: game.thumbnail_url }} style={s.thumb} />
            : <View style={[s.thumb, s.thumbPlaceholder]}><Text style={{ fontSize: 32 }}>🎲</Text></View>}
          <View style={s.headerInfo}>
            <Text style={s.title}>{game.name}</Text>
            <Text style={s.meta}>
              {[game.year,
                game.min_players && game.max_players ? `${game.min_players}–${game.max_players}p` : null,
                game.playing_time ? `${game.playing_time} min` : null,
                game.weight ? `Complexity ${game.weight.toFixed(1)}/5` : null,
              ].filter(Boolean).join(' · ')}
            </Text>
            {game.avg_rating ? <Text style={s.meta}>BGG ★ {game.avg_rating.toFixed(1)}</Text> : null}
            {game.designers ? <Text style={s.meta}>By {game.designers}</Text> : null}
          </View>
        </View>

        {/* Status banner */}
        <View style={[s.banner, loan ? (overdue ? s.bannerOverdue : s.bannerOut) : s.bannerIn]}>
          <Text style={[s.bannerTxt, loan ? (overdue ? s.bannerTxtRed : s.bannerTxtBrown) : s.bannerTxtGreen]}>
            {loan
              ? `${overdue ? '⚠ OVERDUE — ' : ''}Out: ${loan.first_name} ${loan.last_name} (since ${loan.checked_out_at?.slice(0, 10)})${loan.due_date ? ` · Due ${loan.due_date}` : ''}`
              : '✓ Available'}
          </Text>
        </View>

        {/* Actions */}
        <View style={s.actions}>
          {loan
            ? <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#e8eaf6' }]} onPress={checkIn}>
                <Ionicons name="return-down-back" size={18} color={NAVY} />
                <Text style={[s.actionTxt, { color: NAVY }]}>Check In</Text>
              </TouchableOpacity>
            : users.length > 0
              ? <TouchableOpacity style={s.actionBtn} onPress={() => setCheckoutOpen(true)}>
                  <Ionicons name="arrow-forward-circle" size={18} color="#fff" />
                  <Text style={s.actionTxt}>Check Out</Text>
                </TouchableOpacity>
              : null}
          <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#1b5e20' }]} onPress={() => { setPlayDate(today); setLogPlayOpen(true); }}>
            <Ionicons name="trophy" size={18} color="#fff" />
            <Text style={s.actionTxt}>Log Play</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.actionBtn, { backgroundColor: game.is_favorite ? '#f0c674' : '#e8eaf6' }]}
            onPress={() => { db.setFavorite(bggId, !game.is_favorite); load(); }}>
            <Text style={{ fontSize: 16 }}>{game.is_favorite ? '★' : '☆'}</Text>
            <Text style={[s.actionTxt, { color: game.is_favorite ? '#5d4037' : NAVY }]}>
              {game.is_favorite ? 'Unfavorite' : 'Favorite'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Tags */}
        {game.tags ? (
          <View style={s.tags}>
            {game.tags.split(',').map((t, i) => (
              <View key={i} style={s.tag}><Text style={s.tagTxt}>{t.trim()}</Text></View>
            ))}
          </View>
        ) : null}

        {/* Comment */}
        {game.my_comment ? (
          <View style={s.card}>
            <Text style={s.sectionTitle}>Your Note</Text>
            <Text style={s.body}>{game.my_comment}</Text>
          </View>
        ) : null}

        {/* Description */}
        {game.description ? (
          <View style={s.card}>
            <Text style={s.sectionTitle}>Description</Text>
            <Text style={s.body} numberOfLines={6}>{game.description}</Text>
          </View>
        ) : null}

        {/* Details */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>Details</Text>
          {game.categories ? <Text style={s.detailRow}><Text style={s.detailKey}>Categories: </Text>{game.categories}</Text> : null}
          {game.mechanics  ? <Text style={s.detailRow}><Text style={s.detailKey}>Mechanics: </Text>{game.mechanics}</Text>  : null}
          {game.publishers ? <Text style={s.detailRow}><Text style={s.detailKey}>Publisher: </Text>{game.publishers}</Text> : null}
        </View>
      </ScrollView>

      {/* Check-out sheet */}
      <Modal visible={checkoutOpen} transparent animationType="slide" onRequestClose={() => setCheckoutOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setCheckoutOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Check Out — {game.name}</Text>

          <Text style={s.label}>Member *</Text>
          <TouchableOpacity style={s.picker} onPress={() => setPickingUser(true)}>
            <Text style={selUser ? s.pickerTxt : s.pickerPlaceholder}>{selUser ? `${selUser.first_name} ${selUser.last_name}` : '— select member —'}</Text>
            <Ionicons name="chevron-down" size={16} color="#9e9e9e" />
          </TouchableOpacity>

          <Text style={s.label}>Due Date (optional)</Text>
          <TextInput style={s.input} value={dueDate} onChangeText={setDueDate} placeholder="YYYY-MM-DD" />

          <Text style={s.label}>Notes</Text>
          <TextInput style={s.input} value={coNotes} onChangeText={setCoNotes} placeholder="Optional" />

          <TouchableOpacity style={s.sheetBtn} onPress={checkOut}>
            <Text style={s.sheetBtnTxt}>Check Out</Text>
          </TouchableOpacity>
        </View>
      </Modal>

      {/* Member picker */}
      <Modal visible={pickingUser} transparent animationType="slide" onRequestClose={() => setPickingUser(false)}>
        <Pressable style={s.overlay} onPress={() => setPickingUser(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Select Member</Text>
          {users.map(u => (
            <TouchableOpacity key={u.id} style={s.gameItem} onPress={() => { setSelUserId(u.id); setPickingUser(false); }}>
              <Text style={s.gameItemTxt}>{u.first_name} {u.last_name}</Text>
              {selUserId === u.id && <Ionicons name="checkmark" size={18} color={NAVY} />}
            </TouchableOpacity>
          ))}
        </View>
      </Modal>

      {/* Log play sheet */}
      <Modal visible={logPlayOpen} transparent animationType="slide" onRequestClose={() => setLogPlayOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setLogPlayOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Log Play — {game.name}</Text>
          <ScrollView>
            <Text style={s.label}>Date *</Text>
            <TextInput style={s.input} value={playDate} onChangeText={setPlayDate} placeholder="YYYY-MM-DD" />
            <Text style={s.label}>Players</Text>
            <PlayerPicker users={users} value={players} onChange={setPlayers} />
            <Text style={s.label}>Winner</Text>
            <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Alice" />
            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" />
            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={playNotes} onChangeText={setPlayNotes} />
            <TouchableOpacity style={s.sheetBtn} onPress={savePlay}>
              <Text style={s.sheetBtnTxt}>Save Play</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  back: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: 16, paddingTop: 52, backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  backTxt: { color: NAVY, fontSize: 16 },
  scroll: { padding: 14, gap: 12 },
  headerRow: { flexDirection: 'row', gap: 14, backgroundColor: '#fff', borderRadius: 12, padding: 14 },
  thumb: { width: 90, height: 90, borderRadius: 8, resizeMode: 'cover' },
  thumbPlaceholder: { backgroundColor: '#e8eaf6', alignItems: 'center', justifyContent: 'center' },
  headerInfo: { flex: 1 },
  title: { fontSize: 16, fontWeight: '700', marginBottom: 4, lineHeight: 22 },
  meta: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  banner: { borderRadius: 10, padding: 12 },
  bannerIn: { backgroundColor: '#e8f5e9' },
  bannerOut: { backgroundColor: '#fff8e1' },
  bannerOverdue: { backgroundColor: '#ffebee' },
  bannerTxt: { fontSize: 13, fontWeight: '600' },
  bannerTxtGreen: { color: '#1b5e20' },
  bannerTxtBrown: { color: '#795548' },
  bannerTxtRed: { color: '#b71c1c' },
  actions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: NAVY, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10 },
  actionTxt: { color: '#fff', fontWeight: '600', fontSize: 14 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tag: { backgroundColor: '#e3f2fd', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 },
  tagTxt: { color: '#0d47a1', fontSize: 12 },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: 14 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: NAVY, marginBottom: 8 },
  body: { fontSize: 13, color: '#444', lineHeight: 20 },
  detailRow: { fontSize: 13, color: '#555', marginBottom: 4 },
  detailKey: { fontWeight: '600' },
  empty: { textAlign: 'center', color: '#9e9e9e', marginTop: 80 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 44, maxHeight: '85%' },
  sheetTitle: { fontSize: 17, fontWeight: '700', marginBottom: 16, color: NAVY },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  picker: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, marginBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  pickerTxt: { fontSize: 15, color: '#333' },
  pickerPlaceholder: { fontSize: 15, color: '#aaa' },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4, marginBottom: 8 },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  gameItem: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#f0f0f0', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gameItemTxt: { fontSize: 15 },
});
