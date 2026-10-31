import * as SecureStore from "expo-secure-store";
import { create } from "zustand";

import { queryClient } from "../lib/query-client";

const TOKEN_KEY = "donpos_token";
const OUTLET_KEY = "donpos_outlet";

export type Role = "owner" | "admin" | "cashier";

export type User = {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
};

export type Outlet = {
  id: string;
  name: string;
  code: string;
};

type AuthState = {
  hydrated: boolean;
  token: string | null;
  outletId: string | null;
  user: User | null;
  outlets: Outlet[];
  hydrate: () => Promise<void>;
  setToken: (token: string) => Promise<void>;
  setProfile: (user: User, outlets: Outlet[]) => void;
  selectOutlet: (outletId: string) => Promise<void>;
  clearOutlet: () => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  hydrated: false,
  token: null,
  outletId: null,
  user: null,
  outlets: [],

  hydrate: async () => {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    const outletId = await SecureStore.getItemAsync(OUTLET_KEY);
    set({ token, outletId, hydrated: true });
  },

  setToken: async (token) => {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    set({ token });
  },

  setProfile: (user, outlets) => set({ user, outlets }),

  selectOutlet: async (outletId) => {
    await SecureStore.setItemAsync(OUTLET_KEY, outletId);
    queryClient.clear();
    set({ outletId });
  },

  clearOutlet: () => {
    void SecureStore.deleteItemAsync(OUTLET_KEY);
    set({ outletId: null });
  },

  logout: () => {
    void SecureStore.deleteItemAsync(TOKEN_KEY);
    void SecureStore.deleteItemAsync(OUTLET_KEY);
    queryClient.clear();
    set({ token: null, outletId: null, user: null, outlets: [] });
  },
}));