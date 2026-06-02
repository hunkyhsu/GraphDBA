import { useEffect, useState, type ReactNode } from "react";
import { Bell, CheckCircle2, Hourglass, PlayCircle, ArrowRight, type LucideIcon } from "lucide-react";

import {
  getDashboard,
  type DashboardStatsResponse,
  type LoginResponse,
} from "../../lib/api";
import { formatRelative, shortId, titleCase } from "../../lib/format";

type DashboardPageProps = {
  session: LoginResponse;
  onOpenAlert: (alertId: string) => void;
  onOpenRun: (runId: string) => void;
  onOpenTicket: (ticketId: string) => void;
  onShowTickets: () => void;
  onShowAlerts: () => void;
};

function StatCard({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: "red" | "blue" | "amber" | "green";
}) {
  const tones = {
    red: "bg-red-50 text-red-600 ring-red-100",
    blue: "bg-indigo-50 text-indigo-600 ring-indigo-100",
    amber: "bg-amber-50 text-amber-600 ring-amber-100",
    green: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  };
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={`grid h-14 w-14 place-items-center rounded-full ring-1 ${tones[tone]}`}>
          <Icon size={26} />
        </div>
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{value}</p>
        </div>
      </div>
    </section>
  );
}

function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex min-h-16 items-center justify-between gap-4 border-b border-slate-200 px-5">
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

export function DashboardPage({
  session,
  onOpenAlert,
  onOpenRun,
  onOpenTicket,
  onShowTickets,
  onShowAlerts,
}: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardStatsResponse | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setError("");
    getDashboard(session.access_token)
      .then((response) => {
        if (isActive) setDashboard(response);
      })
      .catch((loadError) => {
        if (isActive) setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard.");
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });
    return () => {
      isActive = false;
    };
  }, [session.access_token]);

  if (error) {
    return <div className="px-5 pb-8 sm:px-8"><div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div></div>;
  }

  const distribution = dashboard?.run_status_distribution ?? [];

  return (
    <div className="space-y-6 px-5 pb-8 sm:px-8">
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Active Alerts" value={dashboard?.active_alerts ?? 0} icon={Bell} tone="red" />
        <StatCard label="Active Runs" value={dashboard?.active_runs ?? 0} icon={PlayCircle} tone="blue" />
        <StatCard label="Pending Approval" value={dashboard?.pending_approval ?? 0} icon={Hourglass} tone="amber" />
        <StatCard label="Solved (24h)" value={dashboard?.solved_24h ?? 0} icon={CheckCircle2} tone="green" />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="Recent Alerts"
          action={<button className="text-sm font-semibold text-indigo-600 hover:text-indigo-700" onClick={onShowAlerts}>View all Alerts</button>}
        >
          <div className="divide-y divide-slate-200">
            {isLoading ? <div className="h-48 bg-slate-50" /> : dashboard?.recent_alerts.length ? dashboard.recent_alerts.map((alert) => (
              <button
                key={alert.alert_id}
                type="button"
                onClick={() => onOpenAlert(alert.alert_id)}
                className="grid w-full grid-cols-[1fr_auto] gap-4 px-5 py-4 text-left hover:bg-slate-50"
              >
                <span>
                  <span className="flex items-center gap-3">
                    <span className={`h-3 w-3 rounded-full ${alert.severity.toLowerCase() === "critical" ? "bg-red-500" : "bg-amber-500"}`} />
                    <span className="font-semibold text-slate-950">{alert.alertname}</span>
                  </span>
                  <span className="ml-6 mt-1 block text-sm text-slate-500">{alert.instance ?? "No instance"}</span>
                </span>
                <span className="text-sm text-slate-500">{formatRelative(alert.updated_at)}</span>
              </button>
            )) : <div className="px-5 py-10 text-sm text-slate-500">No recent alerts.</div>}
          </div>
        </Panel>

        <Panel
          title="Pending Approval"
          action={<button className="text-sm font-semibold text-indigo-600 hover:text-indigo-700" onClick={onShowTickets}>View all Tickets</button>}
        >
          <div className="divide-y divide-slate-200">
            {isLoading ? <div className="h-48 bg-slate-50" /> : dashboard?.pending_tickets.length ? dashboard.pending_tickets.map((ticket) => (
              <button
                key={ticket.ticket_id}
                type="button"
                onClick={() => onOpenTicket(ticket.ticket_id)}
                className="grid w-full grid-cols-[1fr_auto] gap-4 px-5 py-4 text-left hover:bg-slate-50"
              >
                <span>
                  <span className="flex items-center gap-3">
                    <span className="h-3 w-3 rounded-full bg-indigo-500" />
                    <span className="font-semibold text-slate-950">{ticket.alertname}</span>
                  </span>
                  <span className="ml-6 mt-1 block text-sm text-slate-500">Run {shortId(ticket.run_id)}</span>
                </span>
                <span className="text-sm text-slate-500">{formatRelative(ticket.updated_at)}</span>
              </button>
            )) : <div className="px-5 py-10 text-sm text-slate-500">No tickets waiting for approval.</div>}
          </div>
        </Panel>
      </div>

      <Panel title="Run Status Distribution">
        <div className="grid gap-4 p-5 md:grid-cols-4 xl:grid-cols-7">
          {distribution.map((item) => (
            <div key={item.key} className="min-w-0">
              <p className="truncate text-center text-sm font-medium text-slate-600">{titleCase(item.label)}</p>
              <p className="mt-2 text-center text-2xl font-semibold text-slate-950">{item.count}</p>
              <div className="mt-3 h-2 rounded-full bg-slate-200">
                <div className="h-full rounded-full bg-indigo-600" style={{ width: `${Math.min(100, item.count * 12 + 12)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <button
        type="button"
        onClick={onShowTickets}
        className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
      >
        Review approval queue <ArrowRight size={16} />
      </button>
    </div>
  );
}
