import { DarkTheme, NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";
import { StatusBar } from "react-native";

import RecordMemo from "../screens/RecordMemo";
import RoutineWeekScreen from "../screens/RoutineWeekScreen";
import { colors } from "../theme";
import TabNavigator from "./TabNavigator";

export type RootStackParams = {
  Tabs: undefined;
  RecordMemo: { eventTitle?: string; eventId?: string } | undefined;
  RoutineWeek: undefined;
};

const Stack = createNativeStackNavigator<RootStackParams>();
const navigationTheme = { ...DarkTheme, colors: { ...DarkTheme.colors, primary: colors.primary, background: colors.canvas, card: colors.surface, text: colors.ink, border: colors.border, notification: colors.primary } };

export default function RootNavigator() {
  return (
    <NavigationContainer theme={navigationTheme}>
      <StatusBar barStyle="light-content" backgroundColor={colors.canvas} />
      <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: colors.surface }, headerTintColor: colors.ink, headerShadowVisible: false, contentStyle: { backgroundColor: colors.canvas } }}>
        <Stack.Screen name="Tabs" component={TabNavigator} options={{ headerShown: false }} />
        <Stack.Screen
          name="RecordMemo"
          component={RecordMemo}
          options={{ presentation: "modal", title: "Record Memo" }}
        />
        <Stack.Screen
          name="RoutineWeek"
          component={RoutineWeekScreen}
          options={{ presentation: "modal", title: "Weekly Routine" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
