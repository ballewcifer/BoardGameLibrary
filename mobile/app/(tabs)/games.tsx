import { useCallback, useState } from 'react';
import {
  View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet,
  Image, RefreshControl, Modal, Pressable, Alert, ActivityIndicator,
} from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import * as bgg from '../../lib/bgg';
import { loadSettings, saveSettings } from '../../lib/settings';
import type { Game, Loan } from '../../lib/types';

const NAVY = '#1a237e';

export default function Games() {
  const [games, setGames]           = useState<Game[]>([]);
  const [openLoans, setOpenLoans]   = useState<Record<number, Loan>>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [search, setSearch]         = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // Sync
  const [syncing, setSyncing]         = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  // Settings modal
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [bggUsername, setBggUsername]   = useState('');
  const [bggToken, setBggToken]         = useState('');
  const [bggPassword, setBggPassword]   = useState('');

  const load = useCallback((q = search) => {
    setGames(db.listGames(q));
    const loans: Record<number, Loan> = {};
    db.currentlyCheckedOut().forEach(l => { if (l.bgg_id) loans[l.bgg_id] = l; });
    setOpenLoans(loans);
    setPlayCounts(db.playCounts());
  }, [search]);

  useFocusEffect(useCallback(() => {
    load();
    loadSettings().then(s => { setBggUsername(s.bgg_username); setBggToken(s.bgg_token); });
  }, [load]));

  const onRefresh = () => { setRefreshing(true); load(); setRefreshing(false); };

  const openSettings = async () => {
    const s = await loadSettings();
    setBggUsername(s.bgg_username);
    setBggToken(s.bgg_token);
    setBggPassword(s.bgg_password);
    setSettingsOpen(true);
  };

  const saveAndClose = async () => {
    await saveSettings({ bgg_username: bggUsername.trim(), bgg_token: bggToken.trim(), bgg_password: bggPassword });
    setSettingsOpen(false);
  };

  const onSync = async () => {
    const settings = await loadSettings();
    if (!settings.bgg_username) {
      Alert.alert('BGG Username required', 'Tap ⚙ to set your BGG username first.');
      return;
    }
    setSyncing(true);
    setSyncMessage('Logging in to BGG…');
    try {
      // Log in first so the session cookie is set for the collection request
      if (settings.bgg_password) {
        await bgg.loginBgg(settings.bgg_username, settings.bgg_password);
      }
      setSyncMessage('Fetching collection…');
      const collection = await bgg.fetchCollection(settings.bgg_username, settings.bgg_token || undefined);
      setSyncMessage(`Saving ${collection.length} games…`);
      for (const g of collection) {
        db.upsertGame({
          bgg_id:       g.bgg_id,
          name:         g.name,
          year:         g.year,
          image_url:    g.image_url,
          thumbnail_url:g.thumbnail_url,
          min_players:  g.min_players,
          max_players:  g.max_players,
          playing_time: g.playing_time,
          weight:       g.weight,
          avg_rating:   g.avg_rating,
          description:  g.description,
          categories:   g.categories?.join(', '),
          mechanics:    g.mechanics?.join(', '),
          designers:    g.designers?.join(', '),
          publishers:   g.publishers?.join(', '),
          own:          1,
          is_expansion: g.is_expansion ? 1 : 0,
        });
      }
      load();
      setSyncMessage(`✓ Synced ${collection.length} games`);
      setTimeout(() => setSyncMessage(''), 3500);
    } catch (e: any) {
      Alert.alert('Sync failed', e.message ?? String(e));
      setSyncMessage('');
    } finally {
      setSyncing(false);
    }
  };

  const filtered = games.filter(g => !g.is_expansion);

  return (
    <View style={s.container}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Games</Text>
        <View style={s.headerRight}>
          {syncing
            ? <ActivityIndicator color="#fff" style={{ marginRight: 8 }} />
            : <TouchableOpacity onPress={onSync} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="sync" size={22} color="#fff" />
              </TouchableOpacity>}
          <TouchableOpacity onPress={openSettings} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="settings-outline" size={22} color="#fff" />
          </TouchableOpacity>
        </View>
      </View>

      {syncMessage ? (
        <View style={[s.syncBanner, syncMessage.startsWith('✓') && s.syncBannerOk]}>
          <Text style={[s.syncBannerTxt, syncMessage.startsWith('✓') && s.syncBannerTxtOk]}>{syncMessage}</Text>
        </View>
      ) : null}

      {/* Search bar */}
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

      {/* Settings modal */}
      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setSettingsOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>BGG Settings</Text>

          <Text style={s.label}>BGG Username</Text>
          <TextInput
            style={s.input}
            value={bggUsername}
            onChangeText={setBggUsername}
            placeholder="e.g. Ballewcifer"
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={s.label}>BGG Password</Text>
          <TextInput
            style={s.input}
            value={bggPassword}
            onChangeText={setBggPassword}
            placeholder="Your BGG password"
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={s.hint}>
            Used to log in and sync private collections.{'\n'}
            Stored securely on your device, never sent anywhere except BGG.
          </Text>

          <TouchableOpacity style={s.sheetBtn} onPress={saveAndClose}>
            <Text style={s.sheetBtnTxt}>Save</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4f6fa' },
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 52, paddingBottom: 12 },
  headerTitle: { color: '#fff', fontSize: 20, fontWeight: '700' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  headerBtn: { padding: 8 },
  syncBanner: { backgroundColor: '#e3f2fd', padding: 8, alignItems: 'center' },
  syncBannerOk: { backgroundColor: '#e8f5e9' },
  syncBannerTxt: { color: '#0d47a1', fontSize: 13 },
  syncBannerTxtOk: { color: '#1b5e20' },
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
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 44 },
  sheetTitle: { fontSize: 18, fontWeight: '700', marginBottom: 20, color: NAVY },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  hint: { fontSize: 12, color: '#9e9e9e', marginBottom: 20, lineHeight: 17 },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center' },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
