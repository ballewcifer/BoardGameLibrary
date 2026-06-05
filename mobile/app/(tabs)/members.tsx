import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Modal, TextInput, Alert, Pressable, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { User } from '../../lib/types';
import ScreenHeader from '../../components/ScreenHeader';

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

export default function Members({ isActive = true }: { isActive?: boolean }) {
  const [users, setUsers]           = useState<User[]>([]);
  const [modalOpen, setModalOpen]   = useState(false);
  const [first, setFirst]           = useState('');
  const [last, setLast]             = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => setUsers(db.listUsers()), []);
  useEffect(() => { if (isActive) load(); }, [isActive]);

  const add = () => {
    if (!first.trim() || !last.trim()) { Alert.alert('Both names required'); return; }
    db.addUser(first.trim(), last.trim());
    setFirst(''); setLast('');
    setModalOpen(false);
    load();
  };

  const remove = (u: User) => {
    Alert.alert('Remove member?', `Remove ${u.first_name} ${u.last_name}? Their checkout history will also be deleted.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => { db.deleteUser(u.id); load(); } },
    ]);
  };

  return (
    <View style={s.container}>
      <ScreenHeader
        title="Members"
        right={
          <TouchableOpacity onPress={() => setModalOpen(true)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} accessibilityRole="button" accessibilityLabel="Add new member">
            <Ionicons name="person-add-outline" size={24} color="#fff" />
          </TouchableOpacity>
        }
      />

      <FlatList
        data={users}
        keyExtractor={u => String(u.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
        contentContainerStyle={{ padding: SP.md }}
        ItemSeparatorComponent={() => <View style={{ height: SP.sm }} />}
        ListEmptyComponent={<Text style={s.empty}>No members yet. Add one to enable check-outs.</Text>}
        renderItem={({ item: u }) => (
          <View style={s.card}>
            <View style={s.avatar}>
              <Text style={s.avatarTxt} accessible={false}>{u.first_name[0]}{u.last_name[0]}</Text>
            </View>
            <View style={s.info}>
              <Text style={s.name}>{u.first_name} {u.last_name}</Text>
              <Text style={s.since}>Member since {u.created_at.slice(0, 10)}</Text>
            </View>
            <TouchableOpacity onPress={() => remove(u)} style={s.removeBtn} accessibilityRole="button" accessibilityLabel={`Remove ${u.first_name} ${u.last_name}`}>
              <Ionicons name="trash-outline" size={20} color={DS.dangerSolid} />
            </TouchableOpacity>
          </View>
        )}
      />

      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setModalOpen(false)} />
        <View style={s.sheet}>
          <View style={s.grab} />
          <Text style={s.sheetTitle}>Add Member</Text>
          <Text style={s.label}>First Name</Text>
          <TextInput style={s.input} placeholder="e.g. Jane" value={first} onChangeText={setFirst} autoFocus />
          <Text style={s.label}>Last Name</Text>
          <TextInput style={s.input} placeholder="e.g. Smith" value={last} onChangeText={setLast} returnKeyType="done" onSubmitEditing={add} />
          <TouchableOpacity style={s.sheetBtn} onPress={add}>
            <Text style={s.sheetBtnTxt}>Add</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: DS.bg },
  card:         { backgroundColor: DS.surface, borderRadius: R.lg, padding: SP.lg, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOpacity: 1, shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, elevation: 2 },
  avatar:       { width: 44, height: 44, borderRadius: 22, backgroundColor: DS.navy900, alignItems: 'center', justifyContent: 'center', marginRight: SP.md },
  avatarTxt:    { color: '#fff', fontWeight: '700', fontSize: 15 },
  info:         { flex: 1 },
  name:         { fontSize: 15, fontWeight: '600', color: DS.ink900 },
  since:        { fontSize: 12, color: DS.ink500, marginTop: 2 },
  removeBtn:    { padding: SP.sm },
  empty:        { textAlign: 'center', color: DS.ink500, marginTop: 40, fontStyle: 'italic', fontSize: 14 },
  overlay:      { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },
  sheet:        { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: SP.xxl, paddingBottom: 40 },
  grab:         { width: 40, height: 5, backgroundColor: DS.line200, borderRadius: R.pill, alignSelf: 'center', marginBottom: SP.lg },
  sheetTitle:   { fontSize: 17, fontWeight: '700', marginBottom: SP.lg, color: DS.ink900 },
  label:        { fontSize: 12, fontWeight: '700', color: DS.ink600, marginBottom: SP.xs, letterSpacing: 0.4, textTransform: 'uppercase' },
  input:        { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.md, fontSize: 15, marginBottom: SP.md, color: DS.ink900, backgroundColor: DS.surface },
  sheetBtn:     { backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.lg, alignItems: 'center', marginTop: SP.xs },
  sheetBtnTxt:  { color: '#fff', fontWeight: '700', fontSize: 15 },
});
