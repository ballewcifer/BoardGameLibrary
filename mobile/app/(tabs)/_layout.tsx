import { useRef, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import PagerView from 'react-native-pager-view';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

// Import screens directly so we can embed them in the PagerView
import DashboardScreen from './index';
import GamesScreen from './games';
import MembersScreen from './members';
import HistoryScreen from './history';
import PlaysScreen from './plays';

const NAVY = '#1a237e';

const TABS = [
  { name: 'Dashboard', icon: 'bar-chart'  as const, Component: DashboardScreen },
  { name: 'Games',     icon: 'dice'       as const, Component: GamesScreen },
  { name: 'Members',   icon: 'people'     as const, Component: MembersScreen },
  { name: 'History',   icon: 'time'       as const, Component: HistoryScreen },
  { name: 'Plays',     icon: 'trophy'     as const, Component: PlaysScreen },
];

export default function TabLayout() {
  const pagerRef                    = useRef<PagerView>(null);
  const [activeIndex, setActive]    = useState(0);
  const insets                      = useSafeAreaInsets();

  const goTo = useCallback((i: number) => {
    pagerRef.current?.setPage(i);
    setActive(i);
  }, []);

  return (
    <View style={s.root}>
      <StatusBar style="light" />

      {/* Swipeable page content */}
      <PagerView
        ref={pagerRef}
        style={s.pager}
        initialPage={0}
        onPageSelected={e => setActive(e.nativeEvent.position)}
        overScrollMode="never"
      >
        {TABS.map(({ name, Component }, i) => (
          <View key={name} style={s.page}>
            <Component isActive={activeIndex === i} />
          </View>
        ))}
      </PagerView>

      {/* Bottom tab bar */}
      <View style={[s.tabBar, { paddingBottom: insets.bottom || 8 }]}>
        {TABS.map(({ name, icon }, i) => {
          const active = activeIndex === i;
          return (
            <TouchableOpacity key={name} style={s.tabItem} onPress={() => goTo(i)}>
              <Ionicons name={active ? icon : `${icon}-outline` as any} size={24} color={active ? NAVY : '#9e9e9e'} />
              <Text style={[s.tabLabel, active && s.tabLabelActive]}>{name}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root:         { flex: 1, backgroundColor: '#f4f6fa' },
  pager:        { flex: 1 },
  page:         { flex: 1 },
  tabBar:       { flexDirection: 'row', backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#e5e7eb' },
  tabItem:      { flex: 1, alignItems: 'center', paddingTop: 8, paddingBottom: 2 },
  tabLabel:     { fontSize: 10, color: '#9e9e9e', marginTop: 2 },
  tabLabelActive: { color: NAVY, fontWeight: '600' },
});
