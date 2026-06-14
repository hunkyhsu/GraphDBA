import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Eye,
  Filter,
  MoreVertical,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";

import {
  DEFAULT_ALERT_PAGE_SIZE,
  getAlertDetail,
  getAlertStats,
  listAlerts,
  type AlertDetailResponse,
  type AlertListItem,
  type AlertStatsResponse,
  type LoginResponse,
} from "../../lib/api";

type AlertsPageProps = {
  session: LoginResponse;
};

const severities = ["All", "Critical", "Warning", "Info"];
const statuses = ["All", "Active", "Pending", "Resolved"];
const pageSizes = [10, 20, 50];

function displayStatus(status: string): "Active" | "Pending" | "Resolved" | "Failed" | "Escalated" {
  if (status === "WAITING_APPROVAL") return "Pending";
  if (status === "SOLVED" || status === "RESOLVED") return "Resolved";
  if (status === "FAILED") return "Failed";
  if (status === "ESCALATED") return "Escalated";
  return "Active";
}

function statusClass(status: string) {
  const display = displayStatus(status);
  if (display === "Resolved") return "bg-emerald-50 text-emerald-700 ring-emerald-100";
  if (display === "Pending") return "bg-amber-50 text-amber-700 ring-amber-100";
  if (display === "Failed") return "bg-rose-50 text-rose-700 ring-rose-100";
  if (display === "Escalated") return "bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-100";
  return "bg-blue-50 text-blue-700 ring-blue-100";
}

function severityClass(severity: string) {
  const key = severity.toLowerCase();
  if (key === "critical") return "bg-red-50 text-red-700 ring-red-100";
  if (key === "warning") return "bg-amber-50 text-amber-700 ring-amber-100";
  return "bg-slate-50 text-slate-600 ring-slate-200";
}

function formatRelative(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) return "now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function formatDateTime(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function databaseContext(alert: AlertListItem) {
  const parts = [alert.cluster_name, alert.database_name, alert.database_role].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : alert.instance ?? "-";
}

function titleCase(value: string) {
  return value.toLowerCase().replace(/(^|\s|_)\w/g, (match) => match.toUpperCase());
}

function StatCard({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: number;
  tone: "red" | "blue" | "green";
  icon: ReactNode;
}) {
  const tones = {
    red: "bg-red-50 text-red-600 ring-red-100",
    blue: "bg-blue-50 text-blue-600 ring-blue-100",
    green: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={`grid h-14 w-14 place-items-center rounded-full ring-1 ${tones[tone]}`}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{value}</p>
        </div>
      </div>
    </section>
  );
}

function SegmentedFilter({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="mr-1 text-sm font-medium text-slate-600">{label}:</span>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          className={`h-9 rounded-md px-4 text-sm font-medium ring-1 transition ${
            value === option
              ? "bg-white text-indigo-600 ring-indigo-500"
              : option === "Critical"
                ? "bg-red-50 text-red-600 ring-red-100 hover:bg-red-100"
                : option === "Warning" || option === "Pending"
                  ? "bg-amber-50 text-amber-700 ring-amber-100 hover:bg-amber-100"
                  : option === "Resolved"
                    ? "bg-emerald-50 text-emerald-700 ring-emerald-100 hover:bg-emerald-100"
                    : "bg-slate-50 text-slate-600 ring-slate-200 hover:bg-slate-100"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function DetailDrawer({
  alert,
  isLoading,
  error,
  onClose,
}: {
  alert: AlertDetailResponse | null;
  isLoading: boolean;
  error: string;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/30 backdrop-blur-sm">
      <aside className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-5">
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-500">Alert Detail</p>
            <h2 className="mt-1 truncate text-xl font-semibold text-slate-950">
              {alert?.alertname ?? "Loading"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            aria-label="Close detail"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-6 px-6 py-5">
          {isLoading ? (
            <div className="h-32 rounded-lg border border-slate-200 bg-slate-50" />
          ) : error ? (
            <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          ) : alert ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["Severity", titleCase(alert.severity)],
                  ["Status", displayStatus(alert.status)],
                  ["Cluster", alert.cluster_name ?? "-"],
                  ["Database", alert.database_name ?? "-"],
                  ["Role", alert.database_role ?? "-"],
                  ["Environment", alert.environment ?? "-"],
                  ["Region", alert.region ?? "-"],
                  ["Host / Port", `${alert.host ?? "-"}${alert.port ? `:${alert.port}` : ""}`],
                  ["First Fired", formatDateTime(alert.started_at)],
                  ["Last Update", formatDateTime(alert.updated_at)],
                ].map(([key, value]) => (
                  <div key={key} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-xs font-medium uppercase tracking-normal text-slate-500">{key}</p>
                    <p className="mt-1 break-words text-sm font-semibold text-slate-900">{value}</p>
                  </div>
                ))}
              </div>

              <section>
                <h3 className="text-sm font-semibold text-slate-950">Summary</h3>
                <p className="mt-2 rounded-md border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-700">
                  {alert.alert_summary}
                </p>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-slate-950">Description</h3>
                <p className="mt-2 rounded-md border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-700">
                  {alert.description ?? "-"}
                </p>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-slate-950">Payload</h3>
                <pre className="mt-2 max-h-80 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-4 text-xs leading-5 text-slate-100">
                  {JSON.stringify(alert.raw_payload, null, 2)}
                </pre>
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

export function AlertsPage({ session }: AlertsPageProps) {
  const [stats, setStats] = useState<AlertStatsResponse>({
    active: 0,
    critical: 0,
    pending_review: 0,
    resolved_24h: 0,
  });
  const [alerts, setAlerts] = useState<AlertListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All");
  const [status, setStatus] = useState("All");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_ALERT_PAGE_SIZE);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AlertDetailResponse | null>(null);
  const [detailError, setDetailError] = useState("");
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  const token = session.access_token;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setError("");
    Promise.all([
      listAlerts({ token, search, severity, status, page, pageSize }),
      getAlertStats(token),
    ])
      .then(([alertResponse, statsResponse]) => {
        if (!isActive) return;
        setAlerts(alertResponse.items);
        setTotal(alertResponse.total);
        setStats(statsResponse);
      })
      .catch((loadError) => {
        if (!isActive) return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load alerts.");
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });
    return () => {
      isActive = false;
    };
  }, [token, search, severity, status, page, pageSize]);

  useEffect(() => {
    if (!selectedId) return;
    let isActive = true;
    setDetail(null);
    setDetailError("");
    setIsDetailLoading(true);
    getAlertDetail(selectedId, token)
      .then((response) => {
        if (isActive) setDetail(response);
      })
      .catch((detailLoadError) => {
        if (!isActive) return;
        setDetailError(detailLoadError instanceof Error ? detailLoadError.message : "Failed to load alert detail.");
      })
      .finally(() => {
        if (isActive) setIsDetailLoading(false);
      });
    return () => {
      isActive = false;
    };
  }, [selectedId, token]);

  const pageNumbers = useMemo(() => {
    const current = Math.min(page, totalPages);
    const first = Math.max(1, current - 1);
    return Array.from({ length: Math.min(3, totalPages) }, (_, index) => first + index).filter(
      (value) => value <= totalPages,
    );
  }, [page, totalPages]);

  function updateSeverity(value: string) {
    setSeverity(value);
    setPage(1);
  }

  function updateStatus(value: string) {
    setStatus(value);
    setPage(1);
  }

  return (
    <>
      <div className="space-y-6 px-5 pb-8 sm:px-8">
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Active Alerts" value={stats.active} tone="red" icon={<Bell size={26} />} />
              <StatCard label="Critical" value={stats.critical} tone="red" icon={<ShieldAlert size={26} />} />
              <StatCard label="Pending Review" value={stats.pending_review} tone="blue" icon={<CheckCircle2 size={26} />} />
              <StatCard label="Resolved (24h)" value={stats.resolved_24h} tone="green" icon={<CheckCircle2 size={26} />} />
            </div>

            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <label className="relative block w-full xl:max-w-md">
                  <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                  <input
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setPage(1);
                    }}
                    placeholder="Search alert name, instance, or label..."
                    className="h-11 w-full rounded-md border border-slate-300 bg-white pl-11 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                  />
                </label>
                <div className="flex flex-wrap items-center gap-4">
                  <SegmentedFilter label="Severity" options={severities} value={severity} onChange={updateSeverity} />
                  <SegmentedFilter label="Status" options={statuses} value={status} onChange={updateStatus} />
                  <button
                    type="button"
                    className="flex h-11 items-center gap-2 rounded-md border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Filter size={17} />
                    Filters
                  </button>
                </div>
              </div>

              <div className="mt-6 overflow-hidden rounded-lg border border-slate-200">
                <div className="overflow-x-auto">
                  <table className="min-w-[940px] w-full border-collapse text-left">
                    <thead className="bg-slate-50 text-sm font-semibold text-slate-500">
                      <tr>
                        <th className="px-5 py-4">Alert Name</th>
                        <th className="px-5 py-4">Instance</th>
                        <th className="px-5 py-4">Severity</th>
                        <th className="px-5 py-4">Status</th>
                        <th className="px-5 py-4">First Fired</th>
                        <th className="px-5 py-4">Last Update</th>
                        <th className="px-5 py-4">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white text-sm">
                      {isLoading ? (
                        Array.from({ length: 5 }).map((_, index) => (
                          <tr key={index}>
                            <td className="px-5 py-5" colSpan={7}>
                              <div className="h-4 w-full rounded bg-slate-100" />
                            </td>
                          </tr>
                        ))
                      ) : error ? (
                        <tr>
                          <td className="px-5 py-8 text-center text-sm text-red-600" colSpan={7}>
                            {error}
                          </td>
                        </tr>
                      ) : alerts.length === 0 ? (
                        <tr>
                          <td className="px-5 py-10 text-center text-sm text-slate-500" colSpan={7}>
                            No alerts found.
                          </td>
                        </tr>
                      ) : (
                        alerts.map((alert) => (
                          <tr key={alert.alert_id} className="hover:bg-slate-50">
                            <td className="px-5 py-4">
                              <button
                                type="button"
                                onClick={() => setSelectedId(alert.alert_id)}
                                className="font-semibold text-slate-950 hover:text-indigo-600"
                              >
                                {alert.alertname}
                              </button>
                            </td>
                            <td className="px-5 py-4 text-slate-600">{databaseContext(alert)}</td>
                            <td className="px-5 py-4">
                              <span className={`inline-flex h-8 items-center rounded-md px-3 text-sm font-medium ring-1 ${severityClass(alert.severity)}`}>
                                {titleCase(alert.severity)}
                              </span>
                            </td>
                            <td className="px-5 py-4">
                              <span className={`inline-flex h-8 items-center rounded-md px-3 text-sm font-medium ring-1 ${statusClass(alert.status)}`}>
                                {displayStatus(alert.status)}
                              </span>
                            </td>
                            <td className="px-5 py-4 text-slate-600">{formatRelative(alert.started_at)}</td>
                            <td className="px-5 py-4 text-slate-600">{formatRelative(alert.updated_at)}</td>
                            <td className="px-5 py-4">
                              <div className="flex items-center gap-2 text-slate-600">
                                <button
                                  type="button"
                                  onClick={() => setSelectedId(alert.alert_id)}
                                  className="grid h-8 w-8 place-items-center rounded-md hover:bg-slate-100 hover:text-slate-950"
                                  aria-label="View alert"
                                >
                                  <Eye size={17} />
                                </button>
                                <button
                                  type="button"
                                  className="grid h-8 w-8 place-items-center rounded-md hover:bg-slate-100 hover:text-slate-950"
                                  aria-label="More actions"
                                >
                                  <MoreVertical size={17} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-500">
                  {total === 0 ? "0 alerts" : `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} of ${total}`}
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={page <= 1}
                      onClick={() => setPage((value) => Math.max(1, value - 1))}
                      className="grid h-10 w-10 place-items-center rounded-md border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      aria-label="Previous page"
                    >
                      <ChevronLeft size={17} />
                    </button>
                    {pageNumbers.map((pageNumber) => (
                      <button
                        key={pageNumber}
                        type="button"
                        onClick={() => setPage(pageNumber)}
                        className={`h-10 min-w-10 rounded-md border px-3 text-sm font-semibold ${
                          page === pageNumber
                            ? "border-indigo-500 text-indigo-600"
                            : "border-slate-300 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {pageNumber}
                      </button>
                    ))}
                    <button
                      type="button"
                      disabled={page >= totalPages}
                      onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                      className="grid h-10 w-10 place-items-center rounded-md border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      aria-label="Next page"
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                  <label className="relative">
                    <select
                      value={pageSize}
                      onChange={(event) => {
                        setPageSize(Number(event.target.value));
                        setPage(1);
                      }}
                      className="h-10 appearance-none rounded-md border border-slate-300 bg-white pl-4 pr-10 text-sm font-medium text-slate-700 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    >
                      {pageSizes.map((size) => (
                        <option key={size} value={size}>
                          {size} / page
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  </label>
                </div>
              </div>
            </section>
      </div>

      {selectedId ? (
        <DetailDrawer
          alert={detail}
          isLoading={isDetailLoading}
          error={detailError}
          onClose={() => {
            setSelectedId(null);
            setDetail(null);
            setDetailError("");
          }}
        />
      ) : null}
    </>
  );
}
