import { useRef, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import PagerView from 'react-native-pager-view';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';

import DashboardScreen from './index';
import GamesScreen     from './games';
import MembersScreen   from './members';
import HistoryScreen   from './history';
import PlaysScreen     from './plays';

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
  dangerText: '#B3261E', dangerBg:'#FCEBEA',dangerSolid:'#C62828',
  infoText:   '#0F52A3', infoBg: '#E7F0FB',
  starText:   '#B07A00', starFill:'#F2A900',
};

const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 };
const R  = { sm: 6, md: 10, lg: 14, pill: 999 };

const TABS = [
  { name: 'Dashboard', icon: 'bar-chart' as const, Component: DashboardScreen },
  { name: 'Games',     icon: 'dice'      as const, Component: GamesScreen },
  { name: 'Members',   icon: 'people'    as const, Component: MembersScreen },
  { name: 'History',   icon: 'time'      as const, Component: HistoryScreen },
  { name: 'Plays',     icon: 'trophy'    as const, Component: PlaysScreen },
];

export default function TabLayout() {
  const pagerRef               = useRef<PagerView>(null);
  const [activeIndex, setActive] = useState(0);
  const insets                 = useSafeAreaInsets();

  const goTo = useCallback((i: number) => {
    pagerRef.current?.setPage(i);
    setActive(i);
  }, []);

  return (
    <View style={s.root}>
      <StatusBar style="light" backgroundColor={DS.navy900} translucent={false} />

      {/* Navy status-bar spacer — fills the area behind the status bar */}
      <View style={{ height: insets.top, backgroundColor: DS.navy900 }} />

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
      <View style={[s.tabBar, { paddingBottom: insets.bottom || SP.sm }]}>
        {TABS.map(({ name, icon }, i) => {
          const active = activeIndex === i;
          return (
            <TouchableOpacity key={name} style={s.tabItem} onPress={() => goTo(i)}>
              <Ionicons
                name={active ? icon : `${icon}-outline` as any}
                size={24}
                color={active ? DS.surface : DS.ink500}
              />
              <Text style={[s.tabLabel, active && s.tabLabelActive]}>{name}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root:           { flex: 1, backgroundColor: DS.navy900 },
  pager:          { flex: 1, backgroundColor: DS.bg },
  page:           { flex: 1 },
  tabBar: {
    flexDirection:    'row',
    backgroundColor:  DS.navy800,
    borderTopWidth:   1,
    borderTopColor:   DS.navy700,
  },
  tabItem: {
    flex:           1,
    alignItems:     'center',
    paddingTop:     SP.sm,
    paddingBottom:  SP.xs / 2,
  },
  tabLabel: {
    fontSize:   10,
    color:      DS.ink500,
    marginTop:  SP.xs / 2,
    fontWeight: '400',
  },
  tabLabelActive: {
    color:      DS.surface,
    fontWeight: '600',
  },
});