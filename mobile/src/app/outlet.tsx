import { useRouter } from "expo-router";
import { FlatList, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../components/Button";
import { RequireAuth } from "../components/RequireAuth";
import { useAuthStore } from "../store/auth";

function OutletList() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);
  const outlets = useAuthStore((s) => s.outlets);
  const outletId = useAuthStore((s) => s.outletId);
  const selectOutlet = useAuthStore((s) => s.selectOutlet);
  const logout = useAuthStore((s) => s.logout);

  async function choose(id: string) {
    await selectOutlet(id);
    router.replace("/kasir");
  }

  return (
    <View
      className="flex-1 bg-white px-6"
      style={{ paddingTop: insets.top + 24, paddingBottom: insets.bottom + 16 }}
    >
      <Text className="text-2xl font-bold text-slate-900">Pilih outlet</Text>
      <Text className="mb-6 mt-1 text-slate-500">
        Halo, {user?.full_name}. Pilih outlet tempat kamu bekerja.
      </Text>

      <FlatList
        data={outlets}
        keyExtractor={(item) => item.id}
        ItemSeparatorComponent={() => <View className="h-3" />}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => choose(item.id)}
            className={
              "rounded-xl border p-4 " +
              (item.id === outletId
                ? "border-blue-600 bg-blue-50"
                : "border-slate-200 bg-white")
            }
          >
            <Text className="text-lg font-semibold text-slate-900">
              {item.name}
            </Text>
            <Text className="text-slate-500">Kode: {item.code}</Text>
          </Pressable>
        )}
      />

      <View className="pt-4">
        <Button title="Keluar" variant="outline" onPress={logout} />
      </View>
    </View>
  );
}

export default function OutletScreen() {
  return (
    <RequireAuth needOutlet={false}>
      <OutletList />
    </RequireAuth>
  );
}