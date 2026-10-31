import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Text,
  TextInput,
  View,
} from "react-native";

import { fetchMe, fetchOutlets, login } from "../api/auth";
import { ApiError } from "../api/client";
import { Button } from "../components/Button";
import { useAuthStore } from "../store/auth";

export default function LoginScreen() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit =
    username.trim().length > 0 && password.length > 0 && !loading;

  async function onSubmit() {
    if (!canSubmit) {
      return;
    }
    setError(null);
    setLoading(true);
    const store = useAuthStore.getState();
    try {
      const res = await login(username, password);
      await store.setToken(res.access_token);
      const [me, outlets] = await Promise.all([fetchMe(), fetchOutlets()]);

      if (outlets.length === 0) {
        store.logout();
        setError("Akun ini belum ditugaskan ke outlet. Hubungi pemilik usaha.");
        return;
      }

      store.setProfile(me, outlets);
      if (outlets.length === 1) {
        await store.selectOutlet(outlets[0].id);
        router.replace("/kasir");
      } else {
        router.replace("/outlet");
      }
    } catch (e) {
      useAuthStore.getState().logout();
      setError(
        e instanceof ApiError ? e.message : "Terjadi kesalahan. Coba lagi."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      className="flex-1 bg-white"
    >
      <View className="flex-1 justify-center px-6">
        <Text className="text-3xl font-bold text-slate-900">DonPOS</Text>
        <Text className="mb-8 mt-1 text-slate-500">
          Masuk untuk mulai berjualan
        </Text>

        <Text className="mb-1 text-sm font-medium text-slate-700">Username</Text>
        <TextInput
          className="mb-4 rounded-lg border border-slate-300 px-4 py-3 text-base text-slate-900"
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="contoh: kasir1"
          placeholderTextColor="#94a3b8"
          returnKeyType="next"
        />

        <Text className="mb-1 text-sm font-medium text-slate-700">Password</Text>
        <TextInput
          className="mb-4 rounded-lg border border-slate-300 px-4 py-3 text-base text-slate-900"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="Password"
          placeholderTextColor="#94a3b8"
          returnKeyType="done"
          onSubmitEditing={onSubmit}
        />

        {error ? <Text className="mb-4 text-red-600">{error}</Text> : null}

        <Button
          title="Masuk"
          onPress={onSubmit}
          loading={loading}
          disabled={!canSubmit}
        />
      </View>
    </KeyboardAvoidingView>
  );
}