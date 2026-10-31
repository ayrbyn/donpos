import type { Outlet, User } from "../store/auth";
import { api } from "./client";

export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export function login(username: string, password: string) {
  return api<LoginResponse>("/auth/login", {
    method: "POST",
    form: { username: username.trim().toLowerCase(), password },
    auth: false,
    outlet: false,
  });
}

export function fetchMe() {
  return api<User>("/auth/me", { outlet: false });
}

export function fetchOutlets() {
  return api<Outlet[]>("/outlets", { outlet: false });
}