import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React from "react";

import RecordMemo from "../screens/RecordMemo";
import RoutineWeekScreen from "../screens/RoutineWeekScreen";
import AddCalendarBlock from "../screens/AddCalendarBlock";
import TabNavigator from "./TabNavigator";

export type RootStackParams = {
  Tabs: undefined;
  RecordMemo: { eventTitle?: string; eventId?: string } | undefined;
  AddCalendarBlock: undefined;
  RoutineWeek: undefined;
};

const Stack = createNativeStackNavigator<RootStackParams>();

export default function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
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
        <Stack.Screen
          name="AddCalendarBlock"
          component={AddCalendarBlock}
          options={{ presentation: "modal", title: "Add calendar block" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
