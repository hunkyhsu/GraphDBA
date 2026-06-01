import { useMemo, useState } from "react";

import { AlertsPage } from "./features/alerts/AlertsPage";
import { LoginPage } from "./features/auth/LoginPage";
import type { LoginResponse } from "./lib/api";
import { clearSession, readSession } from "./lib/authStorage";

export function App() {
  const existingSession = useMemo(() => readSession(), []);
  const [session, setSession] = useState<LoginResponse | null>(existingSession);

  function handleSignOut() {
    clearSession();
    setSession(null);
  }

  if (session) {
    return <AlertsPage session={session} onSignOut={handleSignOut} />;
  }

  return <LoginPage onAuthenticated={setSession} />;
}
