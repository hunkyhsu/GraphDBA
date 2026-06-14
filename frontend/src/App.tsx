import { useMemo, useState } from "react";
import { Radio } from "lucide-react";

import { AppShell, type AppView } from "./components/AppShell";
import { AlertsPage } from "./features/alerts/AlertsPage";
import { LoginPage } from "./features/auth/LoginPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { RunPage } from "./features/runs/RunPage";
import { TicketPage } from "./features/tickets/TicketPage";
import { TicketsPage } from "./features/tickets/TicketsPage";
import type { LoginResponse } from "./lib/api";
import { clearSession, readSession } from "./lib/authStorage";
import { shortId } from "./lib/format";

export function App() {
  const existingSession = useMemo(() => readSession(), []);
  const [session, setSession] = useState<LoginResponse | null>(existingSession);
  const [view, setView] = useState<AppView>("dashboard");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [isEditingTicket, setIsEditingTicket] = useState(false);

  function handleSignOut() {
    clearSession();
    setSession(null);
  }

  function navigate(nextView: AppView) {
    setView(nextView);
    if (nextView !== "runs") setSelectedRunId(null);
    if (nextView !== "tickets") {
      setSelectedTicketId(null);
      setIsEditingTicket(false);
    }
  }

  if (session) {
    const title = selectedTicketId
      ? isEditingTicket
        ? "Modify Execution Plan"
        : `Ticket ${shortId(selectedTicketId)}`
      : selectedRunId
        ? `Run ${shortId(selectedRunId)}`
        : view === "tickets"
          ? "Tickets"
          : view === "alerts"
            ? "Alerts"
          : view === "runs" || view === "agent"
            ? "Agent Runs"
            : "Dashboard";

    const subtitle = selectedTicketId ? (
      <span>Tickets / {shortId(selectedTicketId)}{isEditingTicket ? " / Edit Plan" : ""}</span>
    ) : selectedRunId ? (
      <span>Runs / {shortId(selectedRunId)}</span>
    ) : null;

    return (
      <AppShell
        session={session}
        active={view}
        title={title}
        subtitle={subtitle}
        actions={selectedRunId ? (
          <button type="button" className="hidden h-11 items-center gap-2 rounded-md border border-indigo-500 px-4 text-sm font-semibold text-indigo-600 hover:bg-indigo-50 sm:inline-flex">
            <Radio size={17} /> Live Events
          </button>
        ) : null}
        onNavigate={navigate}
        onSignOut={handleSignOut}
      >
        {view === "dashboard" ? (
          <DashboardPage
            session={session}
            onOpenAlert={() => navigate("alerts")}
            onOpenRun={(runId) => {
              setSelectedRunId(runId);
              setView("runs");
            }}
            onOpenTicket={(ticketId) => {
              setSelectedTicketId(ticketId);
              setIsEditingTicket(false);
              setView("tickets");
            }}
            onShowTickets={() => navigate("tickets")}
            onShowAlerts={() => navigate("alerts")}
          />
        ) : view === "alerts" ? (
          <AlertsPage session={session} />
        ) : view === "tickets" && selectedTicketId ? (
          <TicketPage
            session={session}
            ticketId={selectedTicketId}
            mode={isEditingTicket ? "edit" : "detail"}
            onEdit={() => setIsEditingTicket(true)}
            onSaved={() => setIsEditingTicket(false)}
            onOpenRun={(runId) => {
              setSelectedRunId(runId);
              setSelectedTicketId(null);
              setIsEditingTicket(false);
              setView("runs");
            }}
          />
        ) : view === "tickets" ? (
          <TicketsPage
            session={session}
            onOpenTicket={(ticketId) => {
              setSelectedTicketId(ticketId);
              setIsEditingTicket(false);
            }}
          />
        ) : selectedRunId ? (
          <RunPage
            session={session}
            runId={selectedRunId}
          />
        ) : (
          <div className="px-5 pb-8 sm:px-8">
            <section className="rounded-lg border border-slate-200 bg-white p-8 text-sm text-slate-600 shadow-sm">
              Select a run from the dashboard or ticket queue to inspect its agent timeline.
            </section>
          </div>
        )}
      </AppShell>
    );
  }

  return <LoginPage onAuthenticated={setSession} />;
}
