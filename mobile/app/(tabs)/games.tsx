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
import { exportBackup, importBackup } from '../../lib/backup';
import type { Game, Loan } from '../../lib/types';

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
  okText:     '#1E6E32', okBg:    '#E6F4EA', okSolid:    '#2E7D32',
  warnText:   '#8A5300', warnBg:  '#FFF3E0', warnSolid:  '#B26A00',
  dangerText: '#B3261E', dangerBg:'#FCEBEA', dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg:  '#E7F0FB',
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

/** Stable image component with error → placeholder fallback */
const GameThumb = memo(({ uri }: { uri: string }) => {
  const [err, setErr] = useState(false);
  if (err) return <Text style={{ fontSize: 36 }}>🎲</Text>;
  return <Image source={{ uri }} style={{ width: '100%', height: '100%', resizeMode: 'cover' }} onError={() => setErr(true)} accessible={false} />;
});

export default function Games({ isActive = true }: { isActive?: boolean }) {
  const [games, setGames]           = useState<Game[]>([]);
  const [openLoans, setOpenLoans]   = useState<Record<number, Loan>>({});
  const [playCounts, setPlayCounts] = useState<Record<number, number>>({});
  const [search, setSearch]         = useState('');
  const [statusFilter, setStatus]   = useState<'all' | 'available' | 'out'>('all');
  const [favOnly, setFavOnly]       = useState(false);
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
    loadSettings().then(s => { setBggUsername(s.bgg_username); });
  }, [isActive]);

  // ── Sync ──────────────────────────────────────────────────────────────────

  const onSync = async () => {
    const settings = await loadSettings();
    if (!settings.bgg_username) {
      // No username — open Settings so they can enter one immediately
      setMenuOpen(false);
      const s = await loadSettings();
      setBggUsername(s.bgg_username); setBggPassword(s.bgg_password);
      setSettingsOpen(true);
      return;
    }
    setSyncing(true);
    setSyncMessage('Connecting to BGG…');
    try {
      // BG Stats approach: login for session cookies AND send Bearer token
      // together — private collections work without making them public.
      if (settings.bgg_password) {
        setSyncMessage('Logging in to BGG…');
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
      const details = await bgg.fetchGameDetails(result.bgg_id);
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

  const onExport = async () => {
    setMenuOpen(false);
    try {
      await exportBackup();
    } catch (e: any) {
      Alert.alert('Export failed', e.message ?? String(e));
    }
  };

  const onImport = async () => {
    setMenuOpen(false);
    try {
      const counts = await importBackup();
      load();
      Alert.alert(
        'Import complete',
        `Members: ${counts.members} added\n` +
        `Plays: ${counts.plays} added\n` +
        `Loans: ${counts.loans} added\n` +
        `Customisations: ${counts.customisations} applied\n` +
        `Skipped (already exist): ${counts.skipped}`
      );
    } catch (e: any) {
      if (e.message !== 'Cancelled') Alert.alert('Import failed', e.message ?? String(e));
    }
  };

  const openSettings = async () => {
    setMenuOpen(false);
    const s = await loadSettings();
    setBggUsername(s.bgg_username); setBggPassword(s.bgg_password);
    setSettingsOpen(true);
  };

  const saveAndClose = async () => {
    // Preserve the existing token (from build-time env var) — don't expose or overwrite it
    const existing = await loadSettings();
    await saveSettings({ bgg_username: bggUsername.trim(), bgg_token: existing.bgg_token, bgg_password: bggPassword });
    setSettingsOpen(false);
  };

  const filtered = games.filter(g => {
    if (favOnly && !g.is_favorite) return false;
    if (statusFilter === 'available' && openLoans[g.bgg_id]) return false;
    if (statusFilter === 'out' && !openLoans[g.bgg_id]) return false;
    return true;
  });

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
        <TouchableOpacity onPress={() => setMenuOpen(true)} style={s.headerBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} accessibilityRole="button" accessibilityLabel="More options">
          <Ionicons name="ellipsis-vertical" size={22} color="#fff" />
        </TouchableOpacity>
      </View>

      {syncMessage ? (
        <View style={[s.syncBanner, syncMessage.startsWith('✓') && s.syncBannerOk]}>
          <Text style={[s.syncBannerTxt, syncMessage.startsWith('✓') && s.syncBannerTxtOk]}>{syncMessage}</Text>
        </View>
      ) : null}

      {/* Search bar */}
      <View style={s.searchBar}>
        <Ionicons name="search" size={16} color={DS.ink500} style={{ marginRight: SP.sm - 2 }} />
        <TextInput
          style={s.searchInput}
          placeholder="Search games…"
          placeholderTextColor={DS.ink500}
          value={search}
          onChangeText={q => { setSearch(q); load(q); }}
          returnKeyType="search"
          accessibilityLabel="Search games"
          accessibilityHint="Type to filter the game list"
        />
        {search ? (
          <TouchableOpacity onPress={() => { setSearch(''); load(''); }}>
            <Ionicons name="close-circle" size={16} color={DS.ink500} />
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Quick filters */}
      <View style={s.filterRow}>
        {(['all', 'available', 'out'] as const).map(f => (
          <TouchableOpacity key={f} style={[s.filterChip, statusFilter === f && s.filterChipActive]} onPress={() => setStatus(f)} accessibilityRole="button" accessibilityLabel={f === 'all' ? 'Show all games' : f === 'available' ? 'Show available games only' : 'Show checked out games only'} accessibilityState={{ selected: statusFilter === f }}>
            <Text style={[s.filterChipTxt, statusFilter === f && s.filterChipTxtActive]}>
              {f === 'all' ? 'All' : f === 'available' ? 'Available' : 'Out'}
            </Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity style={[s.filterChip, favOnly && s.filterChipFav]} onPress={() => setFavOnly(v => !v)} accessibilityRole="button" accessibilityLabel="Show favorites only" accessibilityState={{ selected: favOnly }}>
          <Text style={[s.filterChipTxt, favOnly && s.filterChipFavTxt]}>★ Favs</Text>
        </TouchableOpacity>
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
          // Determine status badge style
          const isOverdue = loan && loan.overdue;
          const badgeContainerStyle = isOverdue ? s.badgeOverdue : loan ? s.badgeOut : s.badgeIn;
          const badgeDotStyle       = isOverdue ? s.badgeDotOverdue : loan ? s.badgeDotOut : s.badgeDotIn;
          const badgeTextStyle      = isOverdue ? s.badgeTxtOverdue : loan ? s.badgeTxtOut : s.badgeTxtIn;
          const badgeLabel          = isOverdue
            ? `Overdue · ${loan.first_name}`
            : loan
            ? `Out · ${loan.first_name}`
            : 'Available';
          return (
            <TouchableOpacity style={s.card} onPress={() => router.push(`/game/${g.bgg_id}`)} accessibilityRole="button" accessibilityLabel={`${g.name}, ${loan ? 'checked out' : 'available'}`}>
              {g.is_favorite ? (
                <View style={s.favBadge} accessible={true} accessibilityLabel="Favorite">
                  <Text style={s.favBadgeTxt}>★</Text>
                </View>
              ) : null}
              <View style={s.imgBox}>
                {uri ? <GameThumb uri={uri} /> : <Text style={s.imgPlaceholder}>🎲</Text>}
              </View>
              <View style={s.cardBody}>
                {/* Status badge above title */}
                <View style={[s.badge, badgeContainerStyle]}>
                  <View style={[s.badgeDot, badgeDotStyle]} />
                  <Text style={[s.badgeTxt, badgeTextStyle]}>{badgeLabel}</Text>
                </View>
                <Text style={s.cardName} numberOfLines={2}>{g.name}</Text>
                <Text style={s.cardMeta}>
                  {[g.year, g.min_players && g.max_players ? `${g.min_players}–${g.max_players}p` : null, g.playing_time ? `${g.playing_time}m` : null].filter(Boolean).join(' · ')}
                </Text>
                {plays > 0 && <Text style={s.cardPlays}>{plays} play{plays !== 1 ? 's' : ''}</Text>}
              </View>
            </TouchableOpacity>
          );
        }}
        extraData={{ openLoans, playCounts }}
        removeClippedSubviews={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); setRefreshing(false); }} />}
        contentContainerStyle={{ padding: SP.sm }}
        columnWrapperStyle={{ gap: SP.sm }}
        ItemSeparatorComponent={() => <View style={{ height: SP.sm }} />}
      />

      {/* ⋯ menu */}
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setMenuOpen(false)} />
        <View style={s.menu}>
          {syncing
            ? <View style={s.menuItem}>
                <ActivityIndicator size="small" color={DS.blue600} />
                <Text style={s.menuTxt}>{syncMessage || 'Syncing…'}</Text>
              </View>
            : <TouchableOpacity style={s.menuItem} onPress={() => { setMenuOpen(false); onSync(); }} accessibilityRole="button" accessibilityLabel="Sync collection from BGG">
                <Ionicons name="sync-outline" size={20} color={DS.blue600} />
                <Text style={s.menuTxt}>Sync Collection</Text>
              </TouchableOpacity>}
          <View style={s.menuDivider} />
          <TouchableOpacity style={s.menuItem} onPress={() => { setMenuOpen(false); openAdd(); }} accessibilityRole="button" accessibilityLabel="Add individual game">
            <Ionicons name="add-circle-outline" size={20} color={DS.blue600} />
            <Text style={s.menuTxt}>Add Game</Text>
          </TouchableOpacity>
          <View style={s.menuDivider} />
          <TouchableOpacity style={s.menuItem} onPress={openSettings}>
            <Ionicons name="settings-outline" size={20} color={DS.blue600} />
            <Text style={s.menuTxt}>BGG Settings</Text>
          </TouchableOpacity>
        </View>
      </Modal>

      {/* ── Add Game modal ─────────────────────────────────────────────────── */}
      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={() => setAddOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setAddOpen(false)} />
        <View style={s.sheet}>
          <View style={s.grabHandle} />
          <View style={s.sheetHeaderRow}>
            <Text style={s.sheetTitle}>Add Game</Text>
            <TouchableOpacity onPress={() => setAddOpen(false)}>
              <Ionicons name="close" size={22} color={DS.ink500} />
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
                  placeholderTextColor={DS.ink500}
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
                style={{ marginTop: SP.sm, maxHeight: 360 }}
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
                    <Ionicons name="chevron-forward" size={16} color={DS.line200} />
                  </TouchableOpacity>
                )}
                ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: DS.line100 }} />}
              />
            </>
          ) : (
            /* Confirm step */
            <ScrollView>
              <TouchableOpacity style={s.backRow} onPress={() => { setAddSelected(null); setAddDetails(null); }}>
                <Ionicons name="arrow-back" size={16} color={DS.blue600} />
                <Text style={s.backTxt}>Back to results</Text>
              </TouchableOpacity>
              {!addDetails
                ? <ActivityIndicator style={{ marginTop: SP.xxl }} color={DS.blue600} />
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
                    <TouchableOpacity style={[s.sheetBtn, { marginTop: SP.lg }]} onPress={confirmAdd} disabled={addSaving}>
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
      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)} accessibilityViewIsModal={true}>
        <Pressable style={s.overlay} onPress={() => setSettingsOpen(false)} />
        <View style={s.sheet}>
          <View style={s.grabHandle} />
          <Text style={s.sheetTitle}>BGG Settings</Text>
          <Text style={s.label}>BGG Username</Text>
          <TextInput style={s.input} value={bggUsername} onChangeText={setBggUsername} placeholder="e.g. Ballewcifer" placeholderTextColor={DS.ink500} autoCapitalize="none" autoCorrect={false} />
          <Text style={s.label}>BGG Password</Text>
          <Text style={s.settingsHint}>Needed for private collections. Leave blank if your collection is public.</Text>
          <TextInput style={s.input} value={bggPassword} onChangeText={setBggPassword} placeholder="Optional" placeholderTextColor={DS.ink500} secureTextEntry autoCapitalize="none" autoCorrect={false} />
          <TouchableOpacity style={s.sheetBtn} onPress={saveAndClose}>
            <Text style={s.sheetBtnTxt}>Save</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container:  { flex: 1, backgroundColor: DS.bg },

  // Header
  header:      { backgroundColor: DS.navy900, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SP.lg, paddingVertical: SP.md },
  headerTitle: { color: '#fff', fontSize: 19, fontWeight: '700' },
  headerBtn:   { padding: 7 },

  // Sync banner
  syncBanner:      { backgroundColor: DS.infoBg, padding: SP.sm, alignItems: 'center' },
  syncBannerOk:    { backgroundColor: DS.okBg },
  syncBannerTxt:   { color: DS.infoText, fontSize: 13 },
  syncBannerTxtOk: { color: DS.okText },

  // Search bar
  searchBar:   { flexDirection: 'row', alignItems: 'center', backgroundColor: DS.surface, marginHorizontal: SP.lg, marginVertical: SP.sm, borderRadius: R.md, paddingHorizontal: SP.md, paddingVertical: SP.sm + 2, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.08)', shadowOpacity: 1, shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, elevation: 2 },
  searchInput: { flex: 1, fontSize: 15, color: DS.ink900 },

  // Filter chips
  filterRow:           { flexDirection: 'row', paddingHorizontal: SP.lg, paddingVertical: SP.xs, gap: SP.sm },
  filterChip:          { paddingHorizontal: SP.md, paddingVertical: SP.xs + 2, borderRadius: R.pill, backgroundColor: DS.surface, borderWidth: 1, borderColor: DS.line200 },
  filterChipActive:    { backgroundColor: DS.blue050, borderColor: '#B9D3F2' },
  filterChipFav:       { backgroundColor: DS.blue050, borderColor: '#B9D3F2' },
  filterChipTxt:       { fontSize: 13, fontWeight: '600', color: DS.ink600 },
  filterChipTxtActive: { color: DS.blue700 },
  filterChipFavTxt:    { color: DS.blue700 },

  // Count label
  count: { paddingHorizontal: SP.lg, paddingBottom: SP.xs, color: DS.ink500, fontSize: 12 },

  // Game card
  card:    { flex: 1, backgroundColor: DS.surface, borderRadius: R.lg, borderWidth: 1, borderColor: DS.line200, overflow: 'hidden', shadowColor: 'rgba(16,32,47,0.08)', shadowOpacity: 1, shadowOffset: { width: 0, height: 1 }, shadowRadius: 3, elevation: 2 },
  imgBox:  { aspectRatio: 1, backgroundColor: DS.line100, justifyContent: 'center', alignItems: 'center' },
  imgPlaceholder: { fontSize: 36 },
  cardBody: { padding: SP.sm },

  // Status badge (dot + word + bg)
  badge:          { flexDirection: 'row', alignItems: 'center', gap: SP.xs, alignSelf: 'flex-start', borderRadius: R.pill, paddingHorizontal: SP.sm + 1, paddingVertical: 3, marginBottom: SP.xs },
  badgeDot:       { width: 6, height: 6, borderRadius: 3 },
  badgeIn:        { backgroundColor: DS.okBg },
  badgeOut:       { backgroundColor: DS.warnBg },
  badgeOverdue:   { backgroundColor: DS.dangerBg },
  badgeDotIn:     { backgroundColor: DS.okSolid },
  badgeDotOut:    { backgroundColor: DS.warnSolid },
  badgeDotOverdue:{ backgroundColor: DS.dangerSolid },
  badgeTxt:       { fontSize: 11, fontWeight: '700' },
  badgeTxtIn:     { color: DS.okText },
  badgeTxtOut:    { color: DS.warnText },
  badgeTxtOverdue:{ color: DS.dangerText },

  cardName:  { fontSize: 15, fontWeight: '700', color: DS.ink900, lineHeight: 20, marginTop: 2 },
  cardMeta:  { fontSize: 12, color: DS.ink600, marginTop: 2 },
  cardPlays: { fontSize: 12, color: DS.ink500, marginTop: 2 },

  // Favorite badge
  favBadge:    { position: 'absolute', top: SP.xs, right: SP.xs, backgroundColor: DS.starFill, borderRadius: R.sm, paddingHorizontal: SP.xs, paddingVertical: 2, zIndex: 1 },
  favBadgeTxt: { fontSize: 12, color: DS.navy900 },

  // Modal overlay
  overlay: { flex: 1, backgroundColor: 'rgba(11,26,42,0.35)' },

  // ⋯ dropdown menu
  menu:        { position: 'absolute', top: 100, right: SP.md, backgroundColor: DS.surface, borderRadius: R.md, borderWidth: 1, borderColor: DS.line200, shadowColor: 'rgba(16,32,47,0.10)', shadowOpacity: 1, shadowOffset: { width: 0, height: 4 }, shadowRadius: 12, elevation: 6, minWidth: 190 },
  menuItem:    { flexDirection: 'row', alignItems: 'center', gap: SP.sm + 2, padding: SP.md + 2 },
  menuDivider: { height: 1, backgroundColor: DS.line100, marginHorizontal: SP.md },
  menuTxt:     { fontSize: 15, color: DS.ink900, fontWeight: '600' },

  // Bottom sheets
  sheet:          { backgroundColor: DS.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: SP.xxl, paddingBottom: 44, maxHeight: '85%' },
  grabHandle:     { width: 40, height: 5, backgroundColor: DS.line200, borderRadius: R.pill, alignSelf: 'center', marginBottom: SP.md },
  sheetHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SP.lg },
  sheetTitle:     { fontSize: 17, fontWeight: '700', color: DS.ink900, marginBottom: SP.lg },

  // Form elements
  label: { ...FONT.label, color: DS.ink600, marginBottom: SP.xs },
  settingsHint: { fontSize: 12, color: DS.ink500, marginBottom: SP.xs, fontStyle: 'italic' },
  input: { borderWidth: 1, borderColor: DS.line200, borderRadius: R.md, padding: SP.sm + 2, fontSize: 15, color: DS.ink900, marginBottom: SP.md, backgroundColor: DS.surface },

  // Primary action button
  sheetBtn:    { backgroundColor: DS.blue600, borderRadius: R.md, padding: SP.md + 2, alignItems: 'center' },
  sheetBtnTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },

  // Add game search
  addSearchRow: { flexDirection: 'row', gap: SP.sm, marginBottom: SP.xs },
  searchBtn:    { backgroundColor: DS.blue600, borderRadius: R.md, paddingHorizontal: SP.md, justifyContent: 'center', alignItems: 'center' },
  resultRow:    { flexDirection: 'row', alignItems: 'center', paddingVertical: SP.md - 2 },
  resultName:   { fontSize: 15, fontWeight: '500', color: DS.ink900 },
  resultYear:   { fontSize: 12, color: DS.ink500, marginTop: 1 },
  emptyTxt:     { textAlign: 'center', color: DS.ink500, marginTop: SP.xl, fontStyle: 'italic' },
  backRow:      { flexDirection: 'row', alignItems: 'center', gap: SP.xs, marginBottom: SP.md },
  backTxt:      { color: DS.blue600, fontSize: 14, fontWeight: '600' },
  confirmName:  { fontSize: 18, fontWeight: '700', color: DS.ink900, marginBottom: SP.sm - 2 },
  confirmMeta:  { fontSize: 13, color: DS.ink600, marginBottom: 3 },
  confirmDesc:  { fontSize: 13, color: DS.ink600, marginTop: SP.sm + 2, lineHeight: 19 },
});
