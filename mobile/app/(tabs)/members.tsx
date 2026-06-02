import { useCallback, useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Modal, TextInput, Alert, Pressable, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { User } from '../../lib/types';

const NAVY = '#1a237e';

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
      <TouchableOpacity style={s.addBtn} onPress={() => setModalOpen(true)}>
        <Ionicons name="person-add" size={18} color="#fff" />
        <Text style={s.addBtnTxt}>Add Member</Text>
      </TouchableOpacity>

      <FlatList
        data={users}
        keyExtractor={u => String(u.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
        contentContainerStyle={{ padding: 12 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        ListEmptyComponent={<Text style={s.empty}>No members yet. Add one to enable check-outs.</Text>}
        renderItem={({ item: u }) => (
          <View style={s.card}>
            <View style={s.avatar}>
              <Text style={s.avatarTxt}>{u.first_name[0]}{u.last_name[0]}</Text>
            </View>
            <View style={s.info}>
              <Text style={s.name}>{u.first_name} {u.last_name}</Text>
              <Text style={s.since}>Member since {u.created_at.slice(0, 10)}</Text>
            </View>
            <TouchableOpacity onPress={() => remove(u)} style={s.removeBtn}>
              <Ionicons name="trash-outline" size={20} color="#b71c1c" />
            </TouchableOpacity>
          </View>
        )}
      />

      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setModalOpen(false)} />
        <View style={s.sheet}>
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
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: NAVY, margin: 12, borderRadius: 10, padding: 12, justifyContent: 'center' },
  addBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, flexDirection: 'row', alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 4, elevation: 2 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: NAVY, alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  avatarTxt: { color: '#fff', fontWeight: '700', fontSize: 16 },
  info: { flex: 1 },
  name: { fontSize: 15, fontWeight: '600' },
  since: { fontSize: 12, color: '#9e9e9e', marginTop: 2 },
  removeBtn: { padding: 6 },
  empty: { textAlign: 'center', color: '#9e9e9e', marginTop: 40, fontStyle: 'italic' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  sheetTitle: { fontSize: 18, fontWeight: '700', marginBottom: 16, color: NAVY },
  label: { fontSize: 13, fontWeight: '600', color: '#333', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center', marginTop: 4 },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
