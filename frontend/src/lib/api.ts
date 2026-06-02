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
export const DEFAULT_ALERT_PAGE_SIZE = 10;

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

export type RunStateResponse = {
  run_id: string;
  values: {
    alert: {
      id: string;
      alertname?: string;
      name?: string;
      instance: string;
      severity: string;
      summary: string;
      description: string;
      raw_payload: Record<string, unknown>;
    };
    current_hypotheses: Array<Record<string, unknown>>;
    rejected_hypotheses: Array<Record<string, unknown>>;
    final_plan: FinalPlan | null;
    ticket_id: string | null;
    attempt_count: number;
    workflow_status: string;
    approval_decision: string | null;
    human_feedback: string | null;
    terminal_message: string | null;
  };
  next: string[];
};

export type PlanStep = {
  step_order: number;
  action_sql: string;
  title?: string | null;
  description?: string | null;
};

export type FinalPlan = {
  target_alert_id: string;
  target_hypothesis_id: string;
  change_reason: string;
  risk_level: string;
  execution_steps: PlanStep[];
  rollback_sql: string | null;
  rollback_note: string | null;
};

export type TicketListItem = {
  ticket_id: string;
  alert_id: string;
  run_id: string | null;
  alertname: string;
  instance: string | null;
  status: string;
  risk_level: string;
  change_reason: string;
  created_at: string;
  updated_at: string;
};

export type TicketDetailResponse = {
  ticket_id: string;
  alert_id: string;
  run_id: string | null;
  hypothesis_id: string;
  status: string;
  risk_level: string;
  created_at: string;
  updated_at: string;
  proposed_steps: PlanStep[];
  approved_steps: PlanStep[] | null;
  change_reason: string;
  rollback_sql: string | null;
  rollback_note: string | null;
  approval_comments: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  alert: {
    alert_id: string;
    alertname: string;
    severity: string;
    status: string;
    instance: string | null;
    summary: string;
    started_at: string | null;
    updated_at: string;
    thread_id: string | null;
  };
  hypotheses: Array<{
    hypothesis_id: string;
    root_cause: string;
    status: string;
    confidence_score: number;
    feedback: string | null;
    metric_evidence: Record<string, unknown>;
  }>;
};

export type DashboardStatsResponse = {
  active_alerts: number;
  active_runs: number;
  pending_approval: number;
  solved_24h: number;
  recent_alerts: AlertListItem[];
  pending_tickets: TicketListItem[];
  run_status_distribution: Array<{
    key: string;
    label: string;
    count: number;
  }>;
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
  pageSize = DEFAULT_ALERT_PAGE_SIZE,
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

export async function getDashboard(token?: string): Promise<DashboardStatsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/dashboard`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load dashboard.");
  }
  return response.json() as Promise<DashboardStatsResponse>;
}

export async function getRun(runId: string, token?: string): Promise<RunStateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load run.");
  }
  return response.json() as Promise<RunStateResponse>;
}

export async function listTickets(token?: string): Promise<{ items: TicketListItem[]; total: number }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tickets?page_size=20`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load tickets.");
  }
  return response.json() as Promise<{ items: TicketListItem[]; total: number }>;
}

export async function getTicketDetail(ticketId: string, token?: string): Promise<TicketDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tickets/${ticketId}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to load ticket.");
  }
  return response.json() as Promise<TicketDetailResponse>;
}

export async function updateTicketPlan(
  ticketId: string,
  payload: {
    change_reason: string;
    proposed_steps: PlanStep[];
    rollback_sql: string | null;
    rollback_note: string | null;
    human_notes?: string | null;
    pre_execution_notes?: Array<Record<string, unknown>>;
  },
  token?: string,
): Promise<TicketDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tickets/${ticketId}/plan`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to save ticket plan.");
  }
  return response.json() as Promise<TicketDetailResponse>;
}

export async function approveRun(
  runId: string,
  payload: { decision: "approved" | "rejected"; feedback?: string | null; modified_sql?: string | null },
  token?: string,
): Promise<{ run_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail ?? "Failed to submit approval.");
  }
  return response.json() as Promise<{ run_id: string; status: string }>;
}
