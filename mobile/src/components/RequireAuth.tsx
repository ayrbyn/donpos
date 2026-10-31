import { Redirect } from "expo-router";
import { type ReactNode, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";

import { fetchMe, fetchOutlets } from "../api/auth";
import { useAuthStore } from "../store/auth";

type Props = {
  children: ReactNode;
  needOutlet?: boolean;
};

function Loading() {
  return (
    <View className="flex-1 items-center justify-center bg-white">
      <ActivityIndicator size="large" color="#2563eb" />
    </View>
  );
}

export function RequireAuth({ children, needOutlet = true }: Props) {
  const hydrated = useAuthStore((s) => s.hydrated);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const outlets = useAuthStore((s) => s.outlets);
  const outletId = useAuthStore((s) => s.outletId);
  const setProfile = useAuthStore((s) => s.setProfile);
  const clearOutlet = useAuthStore((s) => s.clearOutlet);
  const logout = useAuthStore((s) => s.logout);

  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!hydrated || !token || user) {
      return;
    }
    let active = true;
    setError(null);
    Promise.all([fetchMe(), fetchOutlets()])
      .then(([me, list]) => {
        if (active) {
          setProfile(me, list);
        }
      })
      .catch((e: Error) => {
        if (active) {
          setError(e.message);
        }
      });
    return () => {
      active = false;
    };
  }, [hydrated, token, user, attempt, setProfile]);

  const outletValid =
    outletId !== null && outlets.some((o) => o.id === outletId);

  useEffect(() => {
    if (user && outletId && !outletValid) {
      clearOutlet();
    }
  }, [user, outletId, outletValid, clearOutlet]);

  if (!hydrated) {
    return <Loading />;
  }
  if (!token) {
    return <Redirect href="/login" />;
  }
  if (!user) {
    if (error) {
      return (
        <View className="flex-1 items-center justify-center bg-white px-6">
          <Text className="mb-4 text-center text-red-600">{error}</Text>
          <Pressable
            className="mb-3 rounded-lg bg-blue-600 px-5 py-3"
            onPress={() => setAttempt((n) => n + 1)}
          >
            <Text className="font-semibold text-white">Coba lagi</Text>
          </Pressable>
          <Pressable onPress={logout}>
            <Text className="text-slate-500">Keluar</Text>
          </Pressable>
        </View>
      );
    }
    return <Loading />;
  }
  if (needOutlet && !outletValid) {
    return <Redirect href="/outlet" />;
  }
  return <>{children}</>;
}