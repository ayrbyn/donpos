import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "../api/client";
import { Button } from "../components/Button";
import { RequireAuth } from "../components/RequireAuth";
import { formatRupiah } from "../lib/money";
import { useAuthStore } from "../store/auth";
import type { Product } from "../types/api";

function Home() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);
  const outlets = useAuthStore((s) => s.outlets);
  const outletId = useAuthStore((s) => s.outletId);
  const logout = useAuthStore((s) => s.logout);

  const outlet = outlets.find((o) => o.id === outletId);

  const products = useQuery({
    queryKey: ["products", outletId, "preview"],
    queryFn: () => api<Product[]>("/products?limit=5"),
  });

  return (
    <View
      className="flex-1 bg-white px-6"
      style={{ paddingTop: insets.top + 24, paddingBottom: insets.bottom + 16 }}
    >
      <Text className="text-2xl font-bold text-slate-900">
        {outlet?.name ?? "Outlet"}
      </Text>
      <Text className="mb-6 mt-1 text-slate-500">
        {user?.full_name} ({user?.role})
      </Text>

      <Text className="mb-2 font-semibold text-slate-700">
        Contoh produk (uji koneksi)
      </Text>

      {products.isLoading ? (
        <Text className="text-slate-500">Memuat produk...</Text>
      ) : products.isError ? (
        <View>
          <Text className="mb-3 text-red-600">
            {products.error instanceof Error
              ? products.error.message
              : "Gagal memuat produk"}
          </Text>
          <Button title="Coba lagi" onPress={() => products.refetch()} />
        </View>
      ) : products.data && products.data.length > 0 ? (
        products.data.map((p) => (
          <View
            key={p.id}
            className="flex-row justify-between border-b border-slate-100 py-3"
          >
            <View className="flex-1 pr-3">
              <Text className="text-base text-slate-900">{p.name}</Text>
              <Text className="text-sm text-slate-500">Stok: {p.stock}</Text>
            </View>
            <Text className="text-base font-semibold text-slate-900">
              {formatRupiah(p.price)}
            </Text>
          </View>
        ))
      ) : (
        <Text className="text-slate-500">Belum ada produk di outlet ini.</Text>
      )}

      <View className="flex-1" />

      {outlets.length > 1 ? (
        <View className="mb-3">
          <Button
            title="Ganti outlet"
            variant="outline"
            onPress={() => router.push("/outlet")}
          />
        </View>
      ) : null}
      <Button title="Keluar" variant="outline" onPress={logout} />
    </View>
  );
}

export default function KasirScreen() {
  return (
    <RequireAuth>
      <Home />
    </RequireAuth>
  );
}