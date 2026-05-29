import { useCallback, useState } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert, Modal, TextInput, RefreshControl } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { User } from '../../lib/types';

const NAVY = '#1a237e';

export default function Members() {
  const [users, setUsers] = useState<User[]>([]);
  const [modal, setModal] = useState(false);
  const [first, setFirst] = useState('');
  const [last, setLast] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => setUsers(db.listUsers()), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = () => { setRefreshing(true); load(); setRefreshing(false); };

  const addMember = () => {
    if (!first.trim() || !last.trim()) { Alert.alert('First and last name are required'); return; }
    db.addUser(first.trim(), last.trim());
    setFirst(''); setLast('');
    setModal(false);
    load();
  };

  const deleteMember = (u: User) => {
    Alert.alert('Remove Member', `Remove ${u.first_name} ${u.last_name}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => { db.deleteUser(u.id); load(); } },
    ]);
  };

  return (
    <View style={s.container}>
      <View style={s.topBar}>
        <Text style={s.count}>{users.length} member{users.length !== 1 ? 's' : ''}</Text>
        <TouchableOpacity style={s.addBtn} onPress={() => setModal(true)}>
          <Ionicons name="person-add" size={16} color="#fff" />
          <Text style={s.addTxt}>Add Member</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={users}
        keyExtractor={u => String(u.id)}
        renderItem={({ item: u }) => (
          <View style={s.card}>
            <View style={s.avatar}>
              <Text style={s.avatarTxt}>{u.first_name[0]}{u.last_name[0]}</Text>
            </View>
            <View style={s.info}>
              <Text style={s.name}>{u.first_name} {u.last_name}</Text>
              <Text style={s.since}>Member since {u.created_at.slice(0, 10)}</Text>
            </View>
            <TouchableOpacity onPress={() => deleteMember(u)} style={s.deleteBtn}>
              <Ionicons name="trash-outline" size={20} color="#e53935" />
            </TouchableOpacity>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ padding: 10, gap: 8 }}
        ListEmptyComponent={<Text style={s.empty}>No members yet. Add one to enable check-outs.</Text>}
      />

      <Modal visible={modal} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setModal(false)}>
        <View style={s.modal}>
          <View style={s.modalHeader}>
            <Text style={s.modalTitle}>Add Member</Text>
            <TouchableOpacity onPress={() => setModal(false)}><Ionicons name="close" size={24} color="#333" /></TouchableOpacity>
          </View>
          <View style={s.modalBody}>
            <Text style={s.label}>First Name</Text>
            <TextInput style={s.input} value={first} onChangeText={setFirst} placeholder="Alice" autoFocus />
            <Text style={s.label}>Last Name</Text>
            <TextInput style={s.input} value={last} onChangeText={setLast} placeholder="Smith" />
          </View>
          <TouchableOpacity style={s.primaryBtn} onPress={addMember}>
            <Text style={s.primaryBtnTxt}>Add</Text>
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
  card: { backgroundColor: '#fff', borderRadius: 10, padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: NAVY, alignItems: 'center', justifyContent: 'center' },
  avatarTxt: { color: '#fff', fontWeight: '700', fontSize: 16 },
  info: { flex: 1 },
  name: { fontSize: 16, fontWeight: '600' },
  since: { fontSize: 12, color: '#9e9e9e', marginTop: 2 },
  deleteBtn: { padding: 6 },
  empty: { textAlign: 'center', color: '#9e9e9e', padding: 40, fontSize: 14 },
  modal: { flex: 1, backgroundColor: '#fff' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 17, fontWeight: '700' },
  modalBody: { flex: 1, padding: 16 },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4 },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  primaryBtn: { backgroundColor: NAVY, margin: 16, padding: 14, borderRadius: 10, alignItems: 'center' },
  primaryBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
