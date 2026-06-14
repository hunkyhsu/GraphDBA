import type { LoginResponse } from "./api";

const STORAGE_KEY = "graphdba.session";

export function saveSession(session: LoginResponse): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  localStorage.removeItem(STORAGE_KEY);
}

export function readSession(): LoginResponse | null {
  const value =
    localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as LoginResponse;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}
