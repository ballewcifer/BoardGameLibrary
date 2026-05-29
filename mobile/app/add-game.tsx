import { useState } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, Platform } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { searchGames, fetchGameDetails } from '../lib/bgg';
import * as db from '../lib/db';
import type { SearchResult } from '../lib/bgg';

const NAVY = '#1a237e';

export default function AddGame() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setResults([]);
    try {
      const r = await searchGames(query.trim());
      setResults(r.slice(0, 30));
    } catch (e: any) {
      Alert.alert('Search failed', e.message);
    } finally { setLoading(false); }
  };

  const addGame = async (item: SearchResult) => {
    setAdding(true);
    try {
      const d = await fetchGameDetails(item.bgg_id);
      if (!d) { Alert.alert('Not found'); return; }
      db.upsertGame({
        bgg_id: d.bgg_id, name: d.name, year: d.year,
        image_url: d.image_url, thumbnail_url: d.thumbnail_url,
        min_players: d.min_players, max_players: d.max_players,
        playing_time: d.playing_time, min_age: d.min_age,
        weight: d.weight, avg_rating: d.avg_rating,
        description: d.description,
        categories: d.categories.join(', '),
        mechanics: d.mechanics.join(', '),
        designers: d.designers.join(', '),
        publishers: d.publishers.join(', '),
        is_expansion: d.is_expansion ? 1 : 0,
        own: 1,
      });
      Alert.alert('Added!', `"${d.name}" added to your library.`, [
        { text: 'OK', onPress: () => router.back() }
      ]);
    } catch (e: any) {
      Alert.alert('Error', e.message);
    } finally { setAdding(false); }
  };

  return (
    <View style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}>
          <Ionicons name="arrow-back" size={22} color="#fff" />
        </TouchableOpacity>
        <Text style={s.title}>Add Game from BGG</Text>
      </View>
      <View style={s.searchRow}>
        <TextInput
          style={s.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Search BoardGameGeek…"
          returnKeyType="search"
          onSubmitEditing={search}
          autoFocus
        />
        <TouchableOpacity style={s.searchBtn} onPress={search}>
          <Ionicons name="search" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
      {loading && <ActivityIndicator style={{ marginTop: 30 }} color={NAVY} size="large" />}
      {adding && (
        <View style={s.overlay}>
          <ActivityIndicator color={NAVY} size="large" />
          <Text style={{ marginTop: 10, color: NAVY, fontWeight: '600' }}>Fetching details…</Text>
        </View>
      )}
      <FlatList
        data={results}
        keyExtractor={r => String(r.bgg_id)}
        renderItem={({ item }) => (
          <TouchableOpacity style={s.result} onPress={() => addGame(item)}>
            <View style={{ flex: 1 }}>
              <Text style={s.resultName}>{item.name}</Text>
              {item.year ? <Text style={s.resultYear}>{item.year}</Text> : null}
            </View>
            <Ionicons name="add-circle-outline" size={24} color={NAVY} />
          </TouchableOpacity>
        )}
        contentContainerStyle={{ padding: 10 }}
        ItemSeparatorComponent={() => <View style={s.sep} />}
        ListEmptyComponent={!loading ? <Text style={s.empty}>Search BGG to add a game to your library.</Text> : null}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', padding: 12, paddingTop: Platform.OS === 'ios' ? 50 : 12 },
  back: { padding: 6, marginRight: 8 },
  title: { color: '#fff', fontWeight: '700', fontSize: 17 },
  searchRow: { flexDirection: 'row', gap: 8, padding: 12, paddingBottom: 0 },
  input: { flex: 1, backgroundColor: '#fff', borderRadius: 10, padding: 12, fontSize: 15, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  searchBtn: { backgroundColor: NAVY, borderRadius: 10, paddingHorizontal: 16, justifyContent: 'center' },
  result: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', padding: 14, borderRadius: 10 },
  resultName: { fontSize: 15, fontWeight: '600', color: '#1a1a2e' },
  resultYear: { fontSize: 12, color: '#9e9e9e', marginTop: 2 },
  sep: { height: 6 },
  empty: { textAlign: 'center', color: '#9e9e9e', padding: 40, fontSize: 14 },
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(255,255,255,.85)', alignItems: 'center', justifyContent: 'center', zIndex: 10 },
});
