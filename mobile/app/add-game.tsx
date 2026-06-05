import { useState } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, Platform } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { searchGames, fetchGameDetails } from '../lib/bgg';
import * as db from '../lib/db';
import type { SearchResult } from '../lib/bgg';

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
          placeholderTextColor={DS.ink500}
          returnKeyType="search"
          onSubmitEditing={search}
          autoFocus
        />
        <TouchableOpacity style={s.searchBtn} onPress={search}>
          <Ionicons name="search" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
      {loading && <ActivityIndicator style={{ marginTop: SP.xxxl }} color={DS.blue600} size="large" />}
      {adding && (
        <View style={s.overlay}>
          <ActivityIndicator color={DS.blue600} size="large" />
          <Text style={s.overlayText}>Fetching details…</Text>
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
            <Ionicons name="add-circle-outline" size={24} color={DS.blue600} />
          </TouchableOpacity>
        )}
        contentContainerStyle={{ padding: SP.md }}
        ItemSeparatorComponent={() => <View style={s.sep} />}
        ListEmptyComponent={!loading ? <Text style={s.empty}>Search BGG to add a game to your library.</Text> : null}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: DS.bg,
  },
  header: {
    backgroundColor: DS.navy900,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SP.lg,
    paddingBottom: SP.md,
    paddingTop: Platform.OS === 'ios' ? 50 : SP.md,
  },
  back: {
    padding: SP.sm,
    marginRight: SP.sm,
  },
  title: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  searchRow: {
    flexDirection: 'row',
    gap: SP.sm,
    padding: SP.md,
    paddingBottom: 0,
  },
  input: {
    flex: 1,
    backgroundColor: DS.surface,
    borderRadius: R.md,
    borderWidth: 1,
    borderColor: DS.line200,
    paddingVertical: SP.md,
    paddingHorizontal: SP.md,
    fontSize: 15,
    color: DS.ink900,
    shadowColor: 'rgba(16,32,47,0.08)',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 3,
    elevation: 2,
  },
  searchBtn: {
    backgroundColor: DS.blue600,
    borderRadius: R.md,
    paddingHorizontal: SP.lg,
    justifyContent: 'center',
  },
  result: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: DS.surface,
    paddingVertical: SP.md,
    paddingHorizontal: SP.lg,
    borderRadius: R.md,
    borderWidth: 1,
    borderColor: DS.line200,
  },
  resultName: {
    fontSize: 15,
    fontWeight: '600',
    color: DS.ink900,
  },
  resultYear: {
    fontSize: 12,
    color: DS.ink600,
    marginTop: SP.xs,
  },
  sep: {
    height: SP.sm,
  },
  empty: {
    textAlign: 'center',
    color: DS.ink500,
    padding: SP.xxxl + SP.sm,
    fontSize: 14,
  },
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(255,255,255,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  overlayText: {
    marginTop: SP.md,
    color: DS.blue600,
    fontWeight: '600',
    fontSize: 14,
  },
});
