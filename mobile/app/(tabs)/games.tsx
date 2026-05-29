import { useCallback, useState } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, Image, RefreshControl } from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import type { Game, Loan } from '../../lib/types';

export default function Games() {
  const [games, setGames] = useState<Game[]>([]);
  const [openLoans, setOpenLoans] = useState<Record<number, Loan>>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [search, setSearch] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((q = search) => {
    setGames(db.listGames(q));
    const loans: Record<number, Loan> = {};
    db.currentlyCheckedOut().forEach(l => { loans[l.bgg_id!] = l; });
    setOpenLoans(loans);
    setPlayCounts(db.playCounts());
  }, [search]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = () => { setRefreshing(true); load(); setRefreshing(false); };

  const filtered = games.filter(g => !g.is_expansion);

  return (
    <View style={s.container}>
      <View style={s.searchBar}>
        <Ionicons name="search" size={16} color="#9e9e9e" style={{ marginRight: 6 }} />
        <TextInput
          style={s.searchInput}
          placeholder="Search games…"
          value={search}
          onChangeText={q => { setSearch(q); load(q); }}
          returnKeyType="search"
        />
        {search ? (
          <TouchableOpacity onPress={() => { setSearch(''); load(''); }}>
            <Ionicons name="close-circle" size={16} color="#9e9e9e" />
          </TouchableOpacity>
        ) : null}
      </View>
      <Text style={s.count}>{filtered.length} game{filtered.length !== 1 ? 's' : ''}</Text>
      <FlatList
        data={filtered}
        numColumns={2}
        keyExtractor={g => String(g.bgg_id)}
        renderItem={({ item: g }) => {
          const loan = openLoans[g.bgg_id];
          const plays = playCounts[g.bgg_id] ?? 0;
          return (
            <TouchableOpacity style={[s.card, loan && s.cardOut]} onPress={() => router.push(`/game/${g.bgg_id}`)}>
              {g.is_favorite ? <Text style={s.favBadge}>★</Text> : null}
              <View style={s.imgBox}>
                {g.thumbnail_url
                  ? <Image source={{ uri: g.thumbnail_url }} style={s.img} />
                  : <Text style={s.imgPlaceholder}>🎲</Text>}
              </View>
              <View style={s.cardBody}>
                <Text style={s.cardName} numberOfLines={2}>{g.name}</Text>
                <Text style={s.cardMeta}>
                  {[g.year, g.min_players && g.max_players ? `${g.min_players}–${g.max_players}p` : null, g.playing_time ? `${g.playing_time}m` : null].filter(Boolean).join(' · ')}
                </Text>
                {plays > 0 && <Text style={s.cardPlays}>{plays} play{plays !== 1 ? 's' : ''}</Text>}
              </View>
              <View style={[s.badge, loan ? s.badgeOut : s.badgeIn]}>
                <Text style={[s.badgeTxt, loan ? s.badgeOutTxt : s.badgeInTxt]}>
                  {loan ? `Out: ${loan.first_name}` : 'Available'}
                </Text>
              </View>
            </TouchableOpacity>
          );
        }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ padding: 8 }}
        columnWrapperStyle={{ gap: 8 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  searchBar: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', margin: 10, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  searchInput: { flex: 1, fontSize: 15 },
  count: { paddingHorizontal: 14, paddingBottom: 4, color: '#9e9e9e', fontSize: 12 },
  card: { flex: 1, backgroundColor: '#fff', borderRadius: 10, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 4, elevation: 2 },
  cardOut: { borderWidth: 2, borderColor: '#f0c674' },
  imgBox: { height: 120, backgroundColor: '#e8eaf6', justifyContent: 'center', alignItems: 'center' },
  img: { width: '100%', height: '100%', resizeMode: 'cover' },
  imgPlaceholder: { fontSize: 36 },
  cardBody: { padding: 8 },
  cardName: { fontSize: 13, fontWeight: '600', lineHeight: 18 },
  cardMeta: { fontSize: 11, color: '#9e9e9e', marginTop: 2 },
  cardPlays: { fontSize: 11, color: '#9e9e9e' },
  badge: { margin: 8, marginTop: 0, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeIn: { backgroundColor: '#e8f5e9' },
  badgeOut: { backgroundColor: '#fff8e1' },
  badgeTxt: { fontSize: 11, fontWeight: '600' },
  badgeInTxt: { color: '#1b5e20' },
  badgeOutTxt: { color: '#795548' },
  favBadge: { position: 'absolute', top: 4, right: 4, backgroundColor: '#f0c674', borderRadius: 4, paddingHorizontal: 4, fontSize: 12, zIndex: 1 },
});
