import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

const NAVY = '#1a237e';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{
      tabBarActiveTintColor: NAVY,
      tabBarInactiveTintColor: '#9e9e9e',
      tabBarStyle: { borderTopColor: '#e5e7eb' },
      headerStyle: { backgroundColor: NAVY },
      headerTintColor: '#fff',
      headerTitleStyle: { fontWeight: '700' },
    }}>
      <Tabs.Screen name="index" options={{
        title: 'Dashboard',
        tabBarIcon: ({ color, size }) => <Ionicons name="bar-chart" size={size} color={color} />,
        headerTitle: '🎲 Board Game Library',
      }} />
      <Tabs.Screen name="games" options={{
        title: 'Games',
        headerShown: false,
        tabBarIcon: ({ color, size }) => <Ionicons name="dice" size={size} color={color} />,
      }} />
      <Tabs.Screen name="members" options={{
        title: 'Members',
        tabBarIcon: ({ color, size }) => <Ionicons name="people" size={size} color={color} />,
      }} />
      <Tabs.Screen name="history" options={{
        title: 'History',
        tabBarIcon: ({ color, size }) => <Ionicons name="time" size={size} color={color} />,
      }} />
      <Tabs.Screen name="plays" options={{
        title: 'Plays',
        tabBarIcon: ({ color, size }) => <Ionicons name="trophy" size={size} color={color} />,
      }} />
    </Tabs>
  );
}
