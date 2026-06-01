export type LoginRequest = {
  employee_id: string;
  password: string;
};

export type LoginRole = {
  id: number;
  name: string;
  type: string;
};

export type LoginUser = {
  id: number;
  employee_id: string;
  name: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  user: LoginUser;
  roles: LoginRole[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Login failed. Please try again.");
  }

  return response.json() as Promise<LoginResponse>;
}

export type AlertStatus =
  | "RECEIVED"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "SOLVED"
  | "RESOLVED"
  | "ESCALATED"
  | "FAILED";

export type AlertListItem = {
  alert_id: string;
  alertname: string;
  severity: string;
  status: AlertStatus | string;
  instance: string | null;
  cluster_name: string | null;
  database_name: string | null;
  database_role: string | null;
  started_at: string | null;
  updated_at: string;
};

export type AlertListResponse = {
  items: AlertListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type AlertStatsResponse = {
  active: number;
  critical: number;
  pending_review: number;
  resolved_24h: number;
};

export type AlertDetailResponse = AlertListItem & {
  fingerprint: string;
  host: string | null;
  port: number | null;
  environment: string | null;
  region: string | null;
  alert_summary: string;
  description: string | null;
  labels: Record<string, unknown>;
  annotations: Record<string, unknown>;
  raw_payload: Record<string, unknown>;
  generator_url: string | null;
  ends_at: string | null;
  received_at: string;
  last_seen_at: string | null;
  resolved_at: string | null;
  occurrence_count: number;
  thread_id: string | null;
  escalation_reason: string | null;
  failure_reason: string | null;
};

type AlertListParams = {
  token?: string;
  search?: string;
  severity?: string;
  status?: string;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortDir?: "asc" | "desc";
};

export async function listAlerts({
  token,
  search,
  severity,
  status,
  page = 1,
  pageSize = 20,
  sortBy = "updated_at",
  sortDir = "desc",
}: AlertListParams): Promise<AlertListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: sortBy,
    sort_dir: sortDir,
  });
  if (search) params.set("search", search);
  if (severity && severity !== "All") params.set("severity", severity);
  if (status && status !== "All") params.set("status", status);

  const response = await fetch(`${API_BASE_URL}/api/v1/alerts?${params}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load alerts.");
  }
  return response.json() as Promise<AlertListResponse>;
}

export async function getAlertStats(token?: string): Promise<AlertStatsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/alerts/stats`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load alert stats.");
  }
  return response.json() as Promise<AlertStatsResponse>;
}

export async function getAlertDetail(
  alertId: string,
  token?: string,
): Promise<AlertDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/alerts/${alertId}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load alert detail.");
  }
  return response.json() as Promise<AlertDetailResponse>;
}
