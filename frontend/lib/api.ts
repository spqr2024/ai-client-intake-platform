export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "intake_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
  auth = false
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const resp = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    if (resp.status === 401 && auth && typeof window !== "undefined") {
      setToken(null);
      window.location.href = "/admin/login";
    }
    throw new ApiError(resp.status, body.detail || resp.statusText);
  }
  return body as T;
}

// ── Shared types ──────────────────────────────────────────────────────────
export interface LeadListItem {
  id: number;
  project_name: string;
  client_name: string;
  service: string;
  budget: number | null;
  timeline: string;
  status: string;
  score: number;
  created_at: string;
}

export interface MessageOut {
  id: number;
  sender: "user" | "bot";
  text: string;
  created_at: string;
}

export interface ActivityOut {
  id: number;
  actor: string;
  action: string;
  detail: string;
  created_at: string;
}

export interface AttachmentOut {
  id: number;
  filename: string;
  size: number;
  content_type: string;
  created_at: string;
}

export interface UserOut {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface LeadDetail extends LeadListItem {
  client_email: string;
  client_phone: string;
  summary: string;
  language: string;
  updated_at: string;
  assigned_to: UserOut | null;
  messages: MessageOut[];
  attachments: AttachmentOut[];
  activities: ActivityOut[];
}

export interface WorkflowOut {
  id: number;
  name: string;
  is_default: number;
  definition: Record<string, unknown>;
  updated_at: string;
}

export interface KBArticle {
  id: number;
  title: string;
  content: string;
  language: string;
  updated_at: string;
}

export interface AnalyticsSummary {
  total_conversations: number;
  total_leads: number;
  completion_rate: number;
  conversion_rate: number;
  average_budget: number;
  average_score: number;
  leads_by_status: Record<string, number>;
  leads_by_service: Record<string, number>;
  leads_per_day: { date: string; count: number }[];
}

export const LEAD_STATUSES = [
  "New",
  "Qualified",
  "In Progress",
  "Converted",
  "Rejected",
  "Closed",
  "Incomplete",
] as const;

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    New: "bg-sky-100 text-sky-800",
    Qualified: "bg-emerald-100 text-emerald-800",
    "In Progress": "bg-amber-100 text-amber-800",
    Converted: "bg-violet-100 text-violet-800",
    Rejected: "bg-rose-100 text-rose-800",
    Closed: "bg-slate-200 text-slate-700",
    Incomplete: "bg-slate-100 text-slate-500",
  };
  return map[status] || "bg-slate-100 text-slate-700";
}

export function scoreColor(score: number): string {
  if (score >= 70) return "text-emerald-600";
  if (score >= 40) return "text-amber-600";
  return "text-rose-600";
}

export function formatBudget(budget: number | null): string {
  if (budget == null) return "—";
  return `$${budget.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}
