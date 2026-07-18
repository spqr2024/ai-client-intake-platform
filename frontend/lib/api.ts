export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "intake_token";
const REFRESH_KEY = "intake_refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string | null, refresh?: string | null) {
  if (typeof window === "undefined") return;
  if (access) localStorage.setItem(TOKEN_KEY, access);
  else localStorage.removeItem(TOKEN_KEY);
  if (refresh !== undefined) {
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    else localStorage.removeItem(REFRESH_KEY);
  }
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const refresh = getRefreshToken();
      if (!refresh) return false;
      try {
        const resp = await fetch(`${API_URL}/api/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!resp.ok) return false;
        const body = await resp.json();
        setTokens(body.access_token, body.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
  auth = false,
  isRetry = false
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
      // Access token expired → try one silent refresh, then replay the call.
      if (!isRetry && (await tryRefresh())) {
        return api<T>(path, options, auth, true);
      }
      setTokens(null, null);
      window.location.href = "/admin/login";
    }
    throw new ApiError(resp.status, body.detail || resp.statusText);
  }
  return body as T;
}

export async function logout() {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await api("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
      }, true);
    } catch {
      /* revocation is best-effort */
    }
  }
  setTokens(null, null);
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
  priority: string;
  tags: string[];
  follow_up_at: string | null;
  score: number;
  created_at: string;
}

export interface MessageOut {
  id: number;
  sender: "user" | "bot";
  text: string;
  meta: Record<string, unknown>;
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
  workspace_id: number;
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
  prompt_name: string;
  updated_at: string;
}

export interface KBArticle {
  id: number;
  title: string;
  content: string;
  language: string;
  source_type: string;
  source_filename: string;
  version: number;
  index_status: string;
  index_error: string;
  indexed_at: string | null;
  chunk_count: number;
  doc_metadata: Record<string, unknown>;
  hit_count: number;
  updated_at: string;
}

export interface KBVersion {
  id: number;
  version: number;
  title: string;
  content: string;
  created_by: string;
  created_at: string;
}

export interface KBStats {
  total_searches: number;
  hit_rate: number;
  articles_by_status: Record<string, number>;
  indexed_chunks: number;
  top_articles: { id: number; title: string; hits: number }[];
  unanswered_queries: { query: string; count: number }[];
}

export interface CRMProvider {
  name: string;
  label: string;
  option_keys: string[];
}

export interface CRMSync {
  id: number;
  lead_id: number;
  provider: string;
  status: string;
  external_id: string;
  external_url: string;
  attempts: number;
  error: string;
  created_at: string;
}

export interface PromptOut {
  id: number;
  name: string;
  kind: string;
  content: string;
  version: number;
  is_active: number;
  created_by: string;
  created_at: string;
}

export interface NotificationOut {
  id: number;
  channel: string;
  event: string;
  title: string;
  body: string;
  link: string;
  recipient: string;
  status: string;
  attempts: number;
  error: string;
  read: number;
  created_at: string;
}

export interface AuditOut {
  id: number;
  actor: string;
  action: string;
  entity: string;
  entity_id: string;
  detail: string;
  ip: string;
  created_at: string;
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

export interface AIAnalytics {
  avg_messages_per_conversation: number;
  avg_conversation_seconds: number;
  abandonment_rate: number;
  dropoff_by_node: Record<string, number>;
  common_questions: { question: string; count: number }[];
  lead_quality: Record<string, number>;
  avg_ai_confidence: number;
  funnel: Record<string, number>;
}

export interface ReplayEvent {
  at: string;
  type: string;
  sender: string;
  text: string;
  meta: Record<string, unknown>;
}

export interface Branding {
  company_name: string;
  bot_name: string;
  logo_url: string;
  primary_color: string;
  hero_title: string;
  hero_subtitle: string;
}

export const PRIORITIES = ["Low", "Medium", "High", "Urgent"] as const;

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
  return map[status] || "bg-indigo-50 text-indigo-700";
}

export function priorityColor(priority: string): string {
  const map: Record<string, string> = {
    Low: "text-slate-400",
    Medium: "text-sky-600",
    High: "text-amber-600",
    Urgent: "text-rose-600",
  };
  return map[priority] || "text-slate-500";
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
