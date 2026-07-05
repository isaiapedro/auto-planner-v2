import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { Text } from "react-native";

import Dashboard from "../screens/Dashboard";
import Insights from "../screens/Insights";
import Schedule from "../screens/Schedule";
import Today from "../screens/Today";

const Tab = createBottomTabNavigator();

const icon = (label: string) =>
  ({ focused }: { focused: boolean }) =>
    <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.5 }}>{label}</Text>;

export default function TabNavigator() {
  return (
    <Tab.Navigator screenOptions={{ headerShown: true }}>
      <Tab.Screen name="Today"     component={Today}     options={{ tabBarIcon: icon("📅") }} />
      <Tab.Screen name="Dashboard" component={Dashboard} options={{ tabBarIcon: icon("📊") }} />
      <Tab.Screen name="Insights"  component={Insights}  options={{ tabBarIcon: icon("🧠") }} />
      <Tab.Screen name="Schedule"  component={Schedule}  options={{ tabBarIcon: icon("🗓️") }} />
    </Tab.Navigator>
  );
}
