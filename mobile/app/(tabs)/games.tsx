import { useCallback, useState, memo, useEffect } from 'react';
import {
  View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet,
  Image, RefreshControl, Modal, Pressable, Alert, ActivityIndicator, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as db from '../../lib/db';
import * as bgg from '../../lib/bgg';
import { loadSettings, saveSettings } from '../../lib/settings';
import type { Game, Loan } from '../../lib/types';

const NAVY = '#1a237e';

/** Stable image component with error → placeholder fallback */
const GameThumb = memo(({ uri }: { uri: string }) => {
  const [err, setErr] = useState(false);
  if (err) return <Text style={{ fontSize: 36 }}>🎲</Text>;
  return <Image source={{ uri }} style={{ width: '100%', height: '100%', resizeMode: 'cover' }} onError={() => setErr(true)} />;
});

export default function Games({ isActive = true }: { isActive?: boolean }) {
  const [games, setGames]           = useState<Game[]>([]);
  const [openLoans, setOpenLoans]   = useState<Record<number, Loan>>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [search, setSearch]         = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // Sync
  const [syncing, setSyncing]         = useState(false);
  const [syncMessage, setSyncMessage] = useState('');

  // Add game
  const [addOpen, setAddOpen]           = useState(false);
  const [addQuery, setAddQuery]         = useState('');
  const [addSearching, setAddSearching] = useState(false);
  const [addResults, setAddResults]     = useState<bgg.SearchResult[]>([]);
  const [addSelected, setAddSelected]   = useState<bgg.SearchResult | null>(null);
  const [addDetails, setAddDetails]     = useState<bgg.GameDetails | null>(null);
  const [addSaving, setAddSaving]       = useState(false);

  // Settings (behind ⋯)
  const [menuOpen, setMenuOpen]         = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [bggUsername, setBggUsername]   = useState('');
  const [bggToken, setBggToken]         = useState('');
  const [bggPassword, setBggPassword]   = useState('');

  // Separate loans/counts from games so loan changes never re-mount image components
  const loadGames = useCallback((q = search) => {
    setGames(db.listGames(q));
  }, [search]);

  const loadLoans = useCallback(() => {
    const loans: Record<number, Loan> = {};
    db.currentlyCheckedOut().forEach(l => { if (l.bgg_id) loans[l.bgg_id] = l; });
    setOpenLoans(loans);
    setPlayCounts(db.playCounts());
  }, []);

  const load = useCallback((q = search) => {
    loadGames(q);
    loadLoans();
  }, [loadGames, loadLoans, search]);

  // On focus: always refresh loans; only reload games on first mount
  const mountedRef = useState(false);
  useEffect(() => {
    if (!isActive) return;
    if (!mountedRef[0]) { mountedRef[1](true); loadGames(); }
    loadLoans();
    loadSettings().then(s => { setBggUsername(s.bgg_username); setBggToken(s.bgg_token); });
  }, [isActive]);

  // ── Sync ──────────────────────────────────────────────────────────────────

  const onSync = async () => {
    const settings = await loadSettings();
    if (!settings.bgg_username) {
      Alert.alert('BGG Username required', 'Tap ⋯ → Settings to set your BGG username.');
      return;
    }
    setSyncing(true);
    setSyncMessage('Connecting to BGG…');
    try {
      if (!settings.bgg_token && settings.bgg_password) {
        setSyncMessage('Logging in…');
        await bgg.loginBgg(settings.bgg_username, settings.bgg_password);
      }
      setSyncMessage('Fetching collection…');
      const collection = await bgg.fetchCollection(settings.bgg_username, settings.bgg_token || undefined);
      setSyncMessage(`Saving ${collection.length} games…`);
      for (const g of collection) {
        db.upsertGame({
          bgg_id: g.bgg_id, name: g.name, year: g.year,
          image_url: g.image_url, thumbnail_url: g.thumbnail_url,
          min_players: g.min_players, max_players: g.max_players,
          playing_time: g.playing_time, weight: g.weight, avg_rating: g.avg_rating,
          description: g.description,
          categories: g.categories?.join(', '), mechanics: g.mechanics?.join(', '),
          designers: g.designers?.join(', '), publishers: g.publishers?.join(', '),
          own: 1, is_expansion: g.is_expansion ? 1 : 0,
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

  // ── Add individual game ───────────────────────────────────────────────────

  const openAdd = () => {
    setAddQuery(''); setAddResults([]); setAddSelected(null); setAddDetails(null);
    setAddOpen(true);
  };

  const doSearch = async () => {
    if (!addQuery.trim()) return;
    setAddSearching(true);
    setAddResults([]);
    setAddSelected(null);
    setAddDetails(null);
    try {
      const results = await bgg.searchGames(addQuery.trim());
      setAddResults(results.slice(0, 30));
    } catch (e: any) {
      Alert.alert('Search failed', e.message ?? String(e));
    } finally {
      setAddSearching(false);
    }
  };

  const selectResult = async (result: bgg.SearchResult) => {
    setAddSelected(result);
    setAddDetails(null);
    setAddSaving(false);
    try {
      const settings = await loadSettings();
      const details = await bgg.fetchGameDetails(result.bgg_id, settings.bgg_token || undefined);
      setAddDetails(details);
    } catch (e: any) {
      Alert.alert('Error loading details', e.message ?? String(e));
    }
  };

  const confirmAdd = () => {
    if (!addDetails) return;
    setAddSaving(true);
    try {
      db.upsertGame({
        bgg_id: addDetails.bgg_id, name: addDetails.name, year: addDetails.year,
        image_url: addDetails.image_url, thumbnail_url: addDetails.thumbnail_url,
        min_players: addDetails.min_players, max_players: addDetails.max_players,
        playing_time: addDetails.playing_time, weight: addDetails.weight,
        avg_rating: addDetails.avg_rating, description: addDetails.description,
        categories: addDetails.categories?.join(', '), mechanics: addDetails.mechanics?.join(', '),
        designers: addDetails.designers?.join(', '), publishers: addDetails.publishers?.join(', '),
        own: 1, is_expansion: addDetails.is_expansion ? 1 : 0,
      });
      load();
      setAddOpen(false);
      Alert.alert('Added!', `"${addDetails.name}" has been added to your library.`);
    } catch (e: any) {
      Alert.alert('Error', e.message ?? String(e));
    } finally {
      setAddSaving(false);
    }
  };

  // ── Settings ──────────────────────────────────────────────────────────────

  const openSettings = async () => {
    setMenuOpen(false);
    const s = await loadSettings();
    setBggUsername(s.bgg_username); setBggToken(s.bgg_token); setBggPassword(s.bgg_password);
    setSettingsOpen(true);
  };

  const saveAndClose = async () => {
    await saveSettings({ bgg_username: bggUsername.trim(), bgg_token: bggToken.trim(), bgg_password: bggPassword });
    setSettingsOpen(false);
  };

  const filtered = games.filter(g => !g.is_expansion);

  // Normalise protocol-relative URLs stored before the https fix
  const thumbUri = (url?: string | null) => {
    if (!url) return null;
    return url.startsWith('//') ? `https:${url}` : url;
  };

  return (
    <View style={s.container}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Games</Text>
        <View style={s.headerRight}>
          {syncing
            ? <ActivityIndicator color="#fff" style={{ marginRight: 4 }} />
            : <TouchableOpacity onPress={onSync} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Ionicons name="sync" size={22} color="#fff" />
              </TouchableOpacity>}
          <TouchableOpacity onPress={openAdd} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="add-circle-outline" size={24} color="#fff" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setMenuOpen(true)} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="ellipsis-vertical" size={22} color="#fff" />
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
          const uri = thumbUri(g.thumbnail_url);
          return (
            <TouchableOpacity style={[s.card, loan && s.cardOut]} onPress={() => router.push(`/game/${g.bgg_id}`)}>
              {g.is_favorite ? <Text style={s.favBadge}>★</Text> : null}
              <View style={s.imgBox}>
                {uri ? <GameThumb uri={uri} /> : <Text style={s.imgPlaceholder}>🎲</Text>}
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
        extraData={{ openLoans, playCounts }}
        removeClippedSubviews={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
        contentContainerStyle={{ padding: 8 }}
        columnWrapperStyle={{ gap: 8 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
      />

      {/* ⋯ menu */}
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setMenuOpen(false)} />
        <View style={s.menu}>
          <TouchableOpacity style={s.menuItem} onPress={openSettings}>
            <Ionicons name="settings-outline" size={20} color={NAVY} />
            <Text style={s.menuTxt}>BGG Settings</Text>
          </TouchableOpacity>
        </View>
      </Modal>

      {/* ── Add Game modal ─────────────────────────────────────────────────── */}
      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={() => setAddOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setAddOpen(false)} />
        <View style={s.sheet}>
          <View style={s.sheetHeaderRow}>
            <Text style={s.sheetTitle}>Add Game</Text>
            <TouchableOpacity onPress={() => setAddOpen(false)}>
              <Ionicons name="close" size={22} color="#9e9e9e" />
            </TouchableOpacity>
          </View>

          {/* Search step */}
          {!addSelected ? (
            <>
              <View style={s.addSearchRow}>
                <TextInput
                  style={[s.input, { flex: 1, marginBottom: 0 }]}
                  value={addQuery}
                  onChangeText={setAddQuery}
                  placeholder="Search BoardGameGeek…"
                  returnKeyType="search"
                  onSubmitEditing={doSearch}
                  autoFocus
                />
                <TouchableOpacity style={s.searchBtn} onPress={doSearch}>
                  {addSearching
                    ? <ActivityIndicator color="#fff" size="small" />
                    : <Ionicons name="search" size={18} color="#fff" />}
                </TouchableOpacity>
              </View>
              <FlatList
                data={addResults}
                keyExtractor={r => String(r.bgg_id)}
                style={{ marginTop: 8, maxHeight: 360 }}
                ListEmptyComponent={
                  !addSearching && addQuery.length > 0
                    ? <Text style={s.emptyTxt}>No results — try a different title.</Text>
                    : null
                }
                renderItem={({ item: r }) => (
                  <TouchableOpacity style={s.resultRow} onPress={() => selectResult(r)}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.resultName}>{r.name}</Text>
                      {r.year ? <Text style={s.resultYear}>{r.year}</Text> : null}
                    </View>
                    <Ionicons name="chevron-forward" size={16} color="#d1d5db" />
                  </TouchableOpacity>
                )}
                ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: '#f3f4f6' }} />}
              />
            </>
          ) : (
            /* Confirm step */
            <ScrollView>
              <TouchableOpacity style={s.backRow} onPress={() => { setAddSelected(null); setAddDetails(null); }}>
                <Ionicons name="arrow-back" size={16} color={NAVY} />
                <Text style={s.backTxt}>Back to results</Text>
              </TouchableOpacity>
              {!addDetails
                ? <ActivityIndicator style={{ marginTop: 24 }} />
                : (
                  <View>
                    <Text style={s.confirmName}>{addDetails.name}</Text>
                    <Text style={s.confirmMeta}>
                      {[addDetails.year,
                        addDetails.min_players && addDetails.max_players ? `${addDetails.min_players}–${addDetails.max_players} players` : null,
                        addDetails.playing_time ? `${addDetails.playing_time} min` : null,
                        addDetails.weight ? `Complexity ${addDetails.weight.toFixed(1)}/5` : null,
                      ].filter(Boolean).join(' · ')}
                    </Text>
                    {addDetails.designers?.length ? <Text style={s.confirmMeta}>By {addDetails.designers.join(', ')}</Text> : null}
                    {addDetails.description
                      ? <Text style={s.confirmDesc} numberOfLines={4}>{addDetails.description}</Text>
                      : null}
                    <TouchableOpacity style={[s.sheetBtn, { marginTop: 16 }]} onPress={confirmAdd} disabled={addSaving}>
                      {addSaving
                        ? <ActivityIndicator color="#fff" />
                        : <Text style={s.sheetBtnTxt}>Add to Library</Text>}
                    </TouchableOpacity>
                  </View>
                )}
            </ScrollView>
          )}
        </View>
      </Modal>

      {/* Settings modal */}
      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)}>
        <Pressable style={s.overlay} onPress={() => setSettingsOpen(false)} />
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>BGG Settings</Text>
          <Text style={s.label}>BGG Username</Text>
          <TextInput style={s.input} value={bggUsername} onChangeText={setBggUsername} placeholder="e.g. Ballewcifer" autoCapitalize="none" autoCorrect={false} />
          <Text style={s.label}>BGG Token</Text>
          <TextInput style={s.input} value={bggToken} onChangeText={setBggToken} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autoCapitalize="none" autoCorrect={false} />
          <Text style={s.label}>BGG Password (fallback)</Text>
          <TextInput style={s.input} value={bggPassword} onChangeText={setBggPassword} placeholder="Only needed if no token" secureTextEntry autoCapitalize="none" autoCorrect={false} />
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
  header: { backgroundColor: NAVY, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 56, paddingBottom: 14 },
  headerTitle: { color: '#fff', fontSize: 20, fontWeight: '700' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  headerBtn: { padding: 7 },
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
  // ⋯ menu
  menu: { position: 'absolute', top: 100, right: 12, backgroundColor: '#fff', borderRadius: 10, shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 8, elevation: 6, minWidth: 160 },
  menuItem: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14 },
  menuTxt: { fontSize: 15, color: NAVY },
  // Sheets
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 44, maxHeight: '85%' },
  sheetHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  sheetTitle: { fontSize: 18, fontWeight: '700', color: NAVY, marginBottom: 16 },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 4, color: '#333' },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, fontSize: 15, marginBottom: 12 },
  sheetBtn: { backgroundColor: NAVY, borderRadius: 8, padding: 14, alignItems: 'center' },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  // Add game
  addSearchRow: { flexDirection: 'row', gap: 8, marginBottom: 4 },
  searchBtn: { backgroundColor: NAVY, borderRadius: 8, paddingHorizontal: 14, justifyContent: 'center', alignItems: 'center' },
  resultRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12 },
  resultName: { fontSize: 15, fontWeight: '500' },
  resultYear: { fontSize: 12, color: '#9e9e9e', marginTop: 1 },
  emptyTxt: { textAlign: 'center', color: '#9e9e9e', marginTop: 20, fontStyle: 'italic' },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 14 },
  backTxt: { color: NAVY, fontSize: 14 },
  confirmName: { fontSize: 18, fontWeight: '700', marginBottom: 6 },
  confirmMeta: { fontSize: 13, color: '#6b7280', marginBottom: 3 },
  confirmDesc: { fontSize: 13, color: '#555', marginTop: 10, lineHeight: 19 },
});
