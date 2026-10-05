import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { Text } from "react-native";

import Insights from "../screens/Insights";
import Calendar from "../screens/Calendar";
import Memos from "../screens/Memos";
import Schedule from "../screens/Schedule";
import { colors } from "../theme";
import Today from "../screens/Today";

const Tab = createBottomTabNavigator();

const icon = (label: string) =>
  ({ focused }: { focused: boolean }) =>
    <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{label}</Text>;

export default function TabNavigator() {
  return (
    <Tab.Navigator screenOptions={{ headerShown: true, tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border }, tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted }}>
      <Tab.Screen name="Today" component={Today} options={{ tabBarIcon: icon("☀️") }} />
      <Tab.Screen name="Memos" component={Memos} options={{ tabBarIcon: icon("🎙️") }} />
      <Tab.Screen name="Calendar" component={Calendar} options={{ tabBarIcon: icon("🗓️") }} />
      <Tab.Screen name="Plan" component={Schedule} options={{ title: "Plan", tabBarIcon: icon("✦") }} />
      <Tab.Screen name="Insights" component={Insights} options={{ tabBarIcon: icon("🧠") }} />
    </Tab.Navigator>
  );
}
