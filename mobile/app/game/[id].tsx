import { useCallback, useState } from 'react';
import { View, Text, ScrollView, Image, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, Pressable, KeyboardAvoidingView, Platform } from 'react-native';
import { useLocalSearchParams, router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as db from '../../lib/db';
import type { Game, Loan, User } from '../../lib/types';
import PlayerPicker from '../../components/PlayerPicker';
import DateInput from '../../components/DateInput';

// Design tokens
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

const FONT = {
  display:   { fontSize: 22, fontWeight: '700' as const },
  title:     { fontSize: 17, fontWeight: '700' as const },
  cardTitle: { fontSize: 15, fontWeight: '700' as const },
  body:      { fontSize: 14, fontWeight: '400' as const },
  bodyBold:  { fontSize: 14, fontWeight: '700' as const },
  label:     { fontSize: 11, fontWeight: '700' as const, textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  caption:   { fontSize: 12, fontWeight: '400' as const },
};

export default function GameDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const bggId = parseInt(id, 10);

  const [game, setGame]       = useState<Game | null>(null);
  const [loan, setLoan]       = useState<Loan | null>(null);
  const [users, setUsers]     = useState<User[]>([]);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [noMemberOpen, setNoMemberOpen] = useState(false);
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
  const [playScores, setPlayScores]   = useState('');
  const [playNotes, setPlayNotes]     = useState('');

  // Edit game personal data
  const [editOpen, setEditOpen]     = useState(false);
  const [editComment, setEditComment] = useState('');
  const [editTags, setEditTags]       = useState('');
  const [editRating, setEditRating]   = useState('');

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
    db.logPlay(bggId, playDate, players, winner, playNotes,
      duration ? parseInt(duration, 10) : undefined,
      playScores.trim() || undefined);
    setLogPlayOpen(false);
    setPlayers(''); setWinner(''); setDuration(''); setPlayScores(''); setPlayNotes('');
  };

  const pickImage = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Permission needed', 'Allow photo library access to set a custom image.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      db.getDb().runSync('UPDATE games SET image_path = ? WHERE bgg_id = ?', [uri, bggId]);
      load();
    }
  };

  const openEditGame = () => {
    if (!game) return;
    setEditComment(game.my_comment ?? '');
    setEditTags(game.tags ?? '');
    setEditRating(game.my_rating != null ? String(game.my_rating) : '');
    setEditOpen(true);
  };

  const saveGameEdit = () => {
    const rating = editRating.trim() ? parseFloat(editRating.trim()) : null;
    db.getDb().runSync(
      'UPDATE games SET my_comment=?, tags=?, my_rating=? WHERE bgg_id=?',
      [editComment.trim() || null, editTags.trim() || null, rating, bggId]
    );
    setEditOpen(false);
    load();
  };

  const selUser = users.find(u => u.id === selUserId);

  // Status badge data
  const statusBadge = loan
    ? overdue
      ? { bg: DS.dangerBg, text: DS.dangerText, dot: DS.dangerSolid, label: `Overdue — ${loan.first_name} ${loan.last_name}` }
      : { bg: DS.warnBg,   text: DS.warnText,   dot: DS.warnSolid,   label: `Out · ${loan.first_name} ${loan.last_name}${loan.due_date ? ` · Due ${loan.due_date}` : ''}` }
    : { bg: DS.okBg, text: DS.okText, dot: DS.okSolid, label: 'Available' };

  return (
    <View style={s.container}>
      {/* Back button */}
      <TouchableOpacity style={s.back} onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Back to games list">
        <Ionicons name="arrow-back" size={22} color={DS.blue600} />
        <Text style={s.backTxt}>Games</Text>
      </TouchableOpacity>

      <ScrollView contentContainerStyle={s.scroll}>
        {/* Header card */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={pickImage} style={s.thumbWrap}
            accessibilityRole="button" accessibilityLabel="Change cover image">
            {game.image_path || game.thumbnail_url
              ? <Image
                  source={{ uri: game.image_path
                    ?? (game.thumbnail_url?.startsWith('//') ? `https:${game.thumbnail_url}` : game.thumbnail_url!) }}
                  style={s.thumb}
                />
              : <View style={[s.thumb, s.thumbPlaceholder]}><Text style={{ fontSize: 32 }}>🎲</Text></View>}
            <View style={s.camOverlay}>
              <Ionicons name="camera-outline" size={18} color="#fff" />
            </View>
          </TouchableOpacity>
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

        {/* Status banner — dot + word + bg */}
        <View style={[s.banner, { backgroundColor: statusBadge.bg }]}>
          <View style={[s.statusDot, { backgroundColor: statusBadge.dot }]} />
          <Text style={[s.bannerTxt, { color: statusBadge.text }]}>{statusBadge.label}</Text>
          {loan && <Text style={[s.bannerSub, { color: statusBadge.text }]}>{`since ${loan.checked_out_at?.slice(0, 10)}`}</Text>}
        </View>

        {/* Actions */}
        <View style={s.actions}>
          {loan
            ? <TouchableOpacity style={s.actionBtnOutline} onPress={checkIn} accessibilityRole="button" accessibilityLabel={`Check in ${game.name}`}>
                <Ionicons name="return-down-back" size={18} color={DS.ink900} />
                <Text style={s.actionTxtOutline}>Check In</Text>
              </TouchableOpacity>
            : <TouchableOpacity
                style={[s.actionBtnPrimary, users.length === 0 && s.actionBtnDisabled]}
                onPress={() => (users.length > 0 ? setCheckoutOpen(true) : setNoMemberOpen(true))}
                accessibilityRole="button"
                accessibilityState={{ disabled: users.length === 0 }}
                accessibilityLabel={`Check out ${game.name}`}>
                <Ionicons name="arrow-forward-circle" size={18} color="#fff" />
                <Text style={s.actionTxtPrimary}>Check Out</Text>
              </TouchableOpacity>}
          <TouchableOpacity style={s.actionBtnOutline} onPress={() => { setPlayDate(today); setLogPlayOpen(true); }} accessibilityRole="button" accessibilityLabel="Log a play for this game">
            <Ionicons name="trophy" size={18} color={DS.ink900} />
            <Text style={s.actionTxtOutline}>Log Play</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.actionBtnOutline, game.is_favorite && s.actionBtnFav]}
            onPress={() => { db.setFavorite(bggId, !game.is_favorite); load(); }}
            accessibilityRole="button"
            accessibilityLabel={game.is_favorite ? 'Remove from favorites' : 'Add to favorites'}>
            <Text style={{ fontSize: 16, color: game.is_favorite ? DS.starFill : DS.ink500 }} accessible={false}>{game.is_favorite ? '★' : '☆'}</Text>
            <Text style={[s.actionTxtOutline, game.is_favorite && { color: DS.starText }]}>
              {game.is_favorite ? 'Unfavorite' : 'Favorite'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.actionBtnOutline} onPress={openEditGame} accessibilityRole="button" accessibilityLabel="Edit game details">
            <Ionicons name="pencil-outline" size={18} color={DS.ink900} />
            <Text style={s.actionTxtOutline}>Edit</Text>
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
      <Modal visible={checkoutOpen} transparent animationType="slide" onRequestClose={() => setCheckoutOpen(false)} accessibilityViewIsModal={true}>
        <KeyboardAvoidingView style={s.modalRoot} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Pressable style={s.overlay} onPress={() => setCheckoutOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetGrab} />
          <Text style={s.sheetTitle}>Check Out — {game.name}</Text>

          <Text style={s.label}>Member *</Text>
          <TouchableOpacity style={s.picker} onPress={() => setPickingUser(true)}>
            <Text style={selUser ? s.pickerTxt : s.pickerPlaceholder}>{selUser ? `${selUser.first_name} ${selUser.last_name}` : '— select member —'}</Text>
            <Ionicons name="chevron-down" size={16} color={DS.ink500} />
          </TouchableOpacity>

          <Text style={s.label}>Due Date (optional)</Text>
          <DateInput value={dueDate} onChange={setDueDate} placeholder="Optional" nullable />

          <Text style={s.label}>Notes</Text>
          <TextInput style={s.input} value={coNotes} onChangeText={setCoNotes} placeholder="Optional" placeholderTextColor={DS.ink500} />

          <TouchableOpacity style={s.sheetBtn} onPress={checkOut}>
            <Text style={s.sheetBtnTxt}>Check Out</Text>
          </TouchableOpacity>
        </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* No-member notice */}
      <Modal visible={noMemberOpen} transparent animationType="slide" onRequestClose={() => setNoMemberOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setNoMemberOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetGrab} />
          <Text style={s.sheetTitle}>Add a member first</Text>
          <Text style={s.body}>You need at least one member before you can check out a game. Add one on the Members tab, then try again.</Text>
          <TouchableOpacity style={s.sheetBtn} onPress={() => { setNoMemberOpen(false); router.push('/members'); }}>
            <Text style={s.sheetBtnTxt}>Go to Members</Text>
          </TouchableOpacity>
        </View>
      </Modal>

      {/* Member picker */}
      <Modal visible={pickingUser} transparent animationType="slide" onRequestClose={() => setPickingUser(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setPickingUser(false)} />
        <View style={s.sheet}>
          <View style={s.sheetGrab} />
          <Text style={s.sheetTitle}>Select Member</Text>
          {users.map(u => (
            <TouchableOpacity key={u.id} style={s.gameItem} onPress={() => { setSelUserId(u.id); setPickingUser(false); }}>
              <Text style={s.gameItemTxt}>{u.first_name} {u.last_name}</Text>
              {selUserId === u.id && <Ionicons name="checkmark" size={18} color={DS.blue600} />}
            </TouchableOpacity>
          ))}
        </View>
      </Modal>

      {/* Log play sheet */}
      <Modal visible={logPlayOpen} transparent animationType="slide" onRequestClose={() => setLogPlayOpen(false)} accessibilityViewIsModal={true}>
        <KeyboardAvoidingView style={s.modalRoot} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Pressable style={s.overlay} onPress={() => setLogPlayOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetGrab} />
          <Text style={s.sheetTitle}>Log Play — {game.name}</Text>
          <ScrollView>
            <Text style={s.label}>Date *</Text>
            <DateInput value={playDate} onChange={setPlayDate} />
            <Text style={s.label}>Players</Text>
            <PlayerPicker users={users} value={players} onChange={setPlayers} />
            <Text style={s.label}>Winner</Text>
            <TextInput style={s.input} value={winner} onChangeText={setWinner} placeholder="Alice" placeholderTextColor={DS.ink500} />
            <Text style={s.label}>Duration (minutes)</Text>
            <TextInput style={s.input} value={duration} onChangeText={setDuration} keyboardType="number-pad" placeholder="90" placeholderTextColor={DS.ink500} />
            <Text style={s.label}>Scores</Text>
            <TextInput style={s.input} value={playScores} onChangeText={setPlayScores} placeholder='e.g. "Alice: 45, Bob: 37"' placeholderTextColor={DS.ink500} />
            <Text style={s.label}>Notes</Text>
            <TextInput style={s.input} value={playNotes} onChangeText={setPlayNotes} placeholderTextColor={DS.ink500} />
            <TouchableOpacity style={s.sheetBtn} onPress={savePlay}>
              <Text style={s.sheetBtnTxt}>Save Play</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Edit Game personal data modal */}
      <Modal visible={editOpen} transparent animationType="slide" onRequestClose={() => setEditOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setEditOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetGrab} />
          <Text style={s.sheetTitle}>Edit — {game.name}</Text>
          <ScrollView>
            <Text style={s.label}>My Rating (1–10)</Text>
            <TextInput style={s.input} value={editRating} onChangeText={setEditRating} keyboardType="decimal-pad" placeholder="e.g. 8.5" placeholderTextColor={DS.ink500} />
            <Text style={s.label}>Tags (comma-separated)</Text>
            <TextInput style={s.input} value={editTags} onChangeText={setEditTags} placeholder="Family, Strategy, Filler" placeholderTextColor={DS.ink500} />
            <Text style={s.label}>My Note / Comment</Text>
            <TextInput
              style={[s.input, { height: 90, textAlignVertical: 'top' }]}
              value={editComment}
              onChangeText={setEditComment}
              placeholder="Your thoughts on this game…"
              placeholderTextColor={DS.ink500}
              multiline
            />
            <View style={s.btnRow}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => setEditOpen(false)}>
                <Text style={s.cancelBtnTxt}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn} onPress={saveGameEdit}>
                <Text style={s.saveBtnTxt}>Save</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:        { flex: 1, backgroundColor: DS.bg },
  back:             { flexDirection: 'row', alignItems: 'center', gap: SP.xs, paddingHorizontal: SP.lg, paddingTop: 52, paddingBottom: SP.md, backgroundColor: DS.navy900, borderBottomWidth: 0 },
  backTxt:          { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
  scroll:           { padding: SP.lg, gap: SP.md },
  headerRow:        { flexDirection: 'row', gap: SP.md, backgroundColor: DS.surface, borderRadius: R.lg, padding: SP.md, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, shadowOpacity: 1, elevation: 1 },
  thumbWrap:        { position: 'relative', width: 90, height: 90 },
  thumb:            { width: 90, height: 90, borderRadius: R.md, resizeMode: 'cover' },
  thumbPlaceholder: { backgroundColor: DS.blue050, alignItems: 'center', justifyContent: 'center' },
  camOverlay:       { position: 'absolute', bottom: SP.xs, right: SP.xs, backgroundColor: 'rgba(0,0,0,0.55)', borderRadius: R.md, padding: 3 },
  headerInfo:       { flex: 1 },
  title:            { fontSize: 16, fontWeight: '700', color: DS.ink900, marginBottom: SP.xs, lineHeight: 22 },
  meta:             { fontSize: 12, color: DS.ink600, marginTop: 2 },
  banner:           { flexDirection: 'row', alignItems: 'center', gap: SP.sm, borderRadius: R.md, paddingHorizontal: SP.md, paddingVertical: SP.sm },
  statusDot:        { width: 7, height: 7, borderRadius: R.pill },
  bannerTxt:        { fontSize: 13, fontWeight: '600', flex: 1 },
  bannerSub:        { fontSize: 12, fontWeight: '400' },
  actions:          { flexDirection: 'row', gap: SP.sm, flexWrap: 'wrap' },
  actionBtnPrimary: { flexDirection: 'row', alignItems: 'center', gap: SP.sm, backgroundColor: DS.blue600, borderRadius: R.md, paddingHorizontal: SP.md, paddingVertical: 11 },
  actionBtnDisabled:{ backgroundColor: DS.line200, opacity: 0.6 },
  actionTxtPrimary: { color: '#FFFFFF', fontWeight: '600', fontSize: 14 },
  actionBtnOutline: { flexDirection: 'row', alignItems: 'center', gap: SP.sm, backgroundColor: DS.surface, borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, paddingHorizontal: SP.md, paddingVertical: 11 },
  actionTxtOutline: { color: DS.ink900, fontWeight: '600', fontSize: 14 },
  actionBtnFav:     { borderColor: DS.starFill, backgroundColor: '#FFFBF0' },
  tags:             { flexDirection: 'row', flexWrap: 'wrap', gap: SP.sm },
  tag:              { backgroundColor: DS.blue050, borderRadius: R.pill, paddingHorizontal: SP.md, paddingVertical: SP.xs },
  tagTxt:           { color: DS.blue700, fontSize: 12, fontWeight: '600' },
  card:             { backgroundColor: DS.surface, borderRadius: R.lg, padding: SP.md, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, shadowOpacity: 1, elevation: 1 },
  sectionTitle:     { fontSize: 15, fontWeight: '700', color: DS.navy900, marginBottom: SP.sm },
  body:             { fontSize: 14, color: DS.ink600, lineHeight: 21 },
  detailRow:        { fontSize: 14, color: DS.ink900, marginBottom: SP.xs, lineHeight: 20 },
  detailKey:        { fontWeight: '600', color: DS.ink500 },
  empty:            { textAlign: 'center', color: DS.ink500, marginTop: 80, fontSize: 15 },
  modalRoot:        { flex: 1 },
  overlay:          { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },
  sheet:            { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: SP.lg, paddingBottom: 44, maxHeight: '85%' },
  sheetGrab:        { width: 40, height: 5, backgroundColor: DS.line200, borderRadius: R.pill, alignSelf: 'center', marginBottom: SP.md },
  sheetTitle:       { fontSize: 17, fontWeight: '700', marginBottom: SP.lg, color: DS.ink900 },
  label:            { fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: SP.xs, color: DS.ink600 },
  input:            { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, fontSize: 15, marginBottom: SP.md, color: DS.ink900, backgroundColor: DS.surface },
  picker:           { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, marginBottom: SP.md, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: DS.surface },
  pickerTxt:        { fontSize: 15, color: DS.ink900 },
  pickerPlaceholder:{ fontSize: 15, color: DS.ink500 },
  sheetBtn:         { backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.md, alignItems: 'center', marginTop: SP.xs, marginBottom: SP.sm },
  sheetBtnTxt:      { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
  gameItem:         { paddingVertical: SP.md, borderBottomWidth: 1, borderBottomColor: DS.line100, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  gameItemTxt:      { fontSize: 15, color: DS.ink900 },
  btnRow:           { flexDirection: 'row', gap: SP.md, marginTop: SP.sm, marginBottom: SP.sm },
  cancelBtn:        { flex: 1, backgroundColor: DS.bg, borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, alignItems: 'center' },
  cancelBtnTxt:     { color: DS.ink600, fontWeight: '600', fontSize: 14 },
  saveBtn:          { flex: 1, backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.md, alignItems: 'center' },
  saveBtnTxt:       { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },
});
