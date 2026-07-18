"use client";

import { useEffect, useState } from "react";
import { api, NotificationOut, UserOut } from "@/lib/api";

type FieldDef = {
  key: string;
  label: string;
  kind: "text" | "textarea" | "toggle" | "select" | "color";
  options?: string[];
  hint?: string;
};

const TABS: { id: string; label: string; icon: string; fields: FieldDef[] }[] = [
  {
    id: "branding",
    label: "Branding",
    icon: "🎨",
    fields: [
      { key: "brand_company_name", label: "Company name", kind: "text" },
      { key: "brand_bot_name", label: "Chatbot name", kind: "text" },
      { key: "brand_primary_color", label: "Primary color", kind: "color" },
      { key: "brand_logo_url", label: "Logo URL", kind: "text", hint: "Shown in emails and the chat widget." },
      { key: "brand_domain", label: "Custom domain", kind: "text", hint: "e.g. intake.yourcompany.com (configure DNS separately)." },
      { key: "landing_hero_title", label: "Landing hero title", kind: "text", hint: "Empty = default text." },
      { key: "landing_hero_subtitle", label: "Landing hero subtitle", kind: "textarea" },
    ],
  },
  {
    id: "ai",
    label: "AI Providers",
    icon: "🤖",
    fields: [
      { key: "ai_provider", label: "AI provider", kind: "select", options: ["", "mock", "openai", "anthropic", "gemini", "openrouter"], hint: "Empty = .env value. API keys live in .env / secret manager — never in the database." },
      { key: "ai_model", label: "Model", kind: "text", hint: "Empty = provider default." },
      { key: "ai_temperature", label: "Temperature", kind: "text" },
      { key: "ai_max_tokens", label: "Max tokens", kind: "text" },
      { key: "system_prompt", label: "Default system prompt (legacy — prefer Prompts page)", kind: "textarea" },
      { key: "summary_prompt", label: "Default summary prompt (legacy — prefer Prompts page)", kind: "textarea" },
    ],
  },
  {
    id: "pipeline",
    label: "Pipeline",
    icon: "📋",
    fields: [
      { key: "pipeline_statuses", label: "Pipeline stages (comma-separated)", kind: "text", hint: "Defines kanban columns and allowed lead statuses." },
      { key: "qualified_score_threshold", label: "Qualified score threshold", kind: "text", hint: "Leads scoring at or above become 'Qualified' automatically." },
    ],
  },
  {
    id: "notifications",
    label: "Notifications",
    icon: "🔔",
    fields: [
      { key: "telegram_enabled", label: "Telegram notifications", kind: "toggle" },
      { key: "telegram_chat_id", label: "Telegram chat ID", kind: "text", hint: "Workspace override; bot token stays in .env." },
      { key: "email_enabled", label: "Email notifications", kind: "toggle" },
      { key: "staff_notification_email", label: "Staff notification email", kind: "text" },
      { key: "client_email_subject", label: "Client email subject", kind: "text" },
      { key: "client_email_body", label: "Client email body", kind: "textarea", hint: "Placeholders: {client_name} {summary} {project_name} {budget} {timeline} {company_name}" },
      { key: "staff_email_subject", label: "Staff email subject", kind: "text" },
      { key: "staff_email_body", label: "Staff email body", kind: "textarea" },
    ],
  },
];

export default function SettingsPage() {
  const [tab, setTab] = useState("branding");
  const [values, setValues] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<UserOut[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationOut[]>([]);
  const [newUser, setNewUser] = useState({ name: "", email: "", password: "", role: "manager" });
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    api<{ values: Record<string, string> }>("/api/settings", {}, true)
      .then((body) => setValues(body.values))
      .catch(() => {});
    loadUsers();
  }, []);

  useEffect(() => {
    if (tab === "integrations") {
      api<NotificationOut[]>("/api/notifications/deliveries?limit=30", {}, true)
        .then(setDeliveries)
        .catch(() => {});
    }
  }, [tab]);

  function loadUsers() {
    api<UserOut[]>("/api/users", {}, true).then(setUsers).catch(() => {});
  }

  async function save() {
    try {
      const body = await api<{ values: Record<string, string> }>(
        "/api/settings", { method: "PUT", body: JSON.stringify({ values }) }, true
      );
      setValues(body.values);
      setMessage({ kind: "ok", text: "Settings saved — applied immediately, no redeploy needed." });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Save failed" });
    }
  }

  async function addUser(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/api/users", { method: "POST", body: JSON.stringify(newUser) }, true);
      setNewUser({ name: "", email: "", password: "", role: "manager" });
      loadUsers();
      setMessage({ kind: "ok", text: "User created." });
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Failed to create user" });
    }
  }

  async function changeRole(userId: number, role: string) {
    try {
      await api(`/api/users/${userId}/role`, { method: "PATCH", body: JSON.stringify({ role }) }, true);
      loadUsers();
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Failed to change role" });
    }
  }

  async function deleteUser(userId: number) {
    try {
      await api(`/api/users/${userId}`, { method: "DELETE" }, true);
      loadUsers();
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Failed to delete user" });
    }
  }

  const currentTab = TABS.find((t) => t.id === tab);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-2xl font-bold">Settings</h1>

      <div className="mb-6 flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-white p-1 text-sm">
        {[...TABS.map((t) => ({ id: t.id, label: t.label, icon: t.icon })),
          { id: "team", label: "Team & Roles", icon: "👥" },
          { id: "integrations", label: "Integrations", icon: "🔌" },
          { id: "billing", label: "Billing", icon: "💳" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-3.5 py-2 font-medium transition ${
              tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {message && (
        <div className={`mb-4 rounded-lg px-3 py-2 text-sm ${
          message.kind === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
        }`}>
          {message.text}
        </div>
      )}

      {currentTab && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="space-y-4">
            {currentTab.fields.map((field) => (
              <div key={field.key}>
                <label className="mb-1 block text-sm font-medium text-slate-700">{field.label}</label>
                {field.kind === "textarea" ? (
                  <textarea
                    value={values[field.key] ?? ""}
                    onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                    className="h-24 w-full rounded-lg border border-slate-200 p-3 text-sm outline-none focus:border-indigo-400"
                  />
                ) : field.kind === "toggle" ? (
                  <button
                    type="button"
                    onClick={() =>
                      setValues({ ...values, [field.key]: values[field.key] === "false" ? "true" : "false" })
                    }
                    className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                      values[field.key] !== "false"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {values[field.key] !== "false" ? "Enabled" : "Disabled"}
                  </button>
                ) : field.kind === "select" ? (
                  <select
                    value={values[field.key] ?? ""}
                    onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400"
                  >
                    {field.options!.map((option) => (
                      <option key={option} value={option}>{option || "(from .env)"}</option>
                    ))}
                  </select>
                ) : field.kind === "color" ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={values[field.key] || "#4f46e5"}
                      onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                      className="h-9 w-14 cursor-pointer rounded border border-slate-200"
                    />
                    <input
                      value={values[field.key] ?? ""}
                      onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                      className="w-32 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                    />
                  </div>
                ) : (
                  <input
                    value={values[field.key] ?? ""}
                    onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                  />
                )}
                {field.hint && <p className="mt-1 text-xs text-slate-400">{field.hint}</p>}
              </div>
            ))}
          </div>
          <button
            onClick={save}
            className="mt-5 rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            Save settings
          </button>
        </section>
      )}

      {tab === "team" && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="mb-4 font-semibold">Team members & roles</h2>
          <ul className="mb-4 divide-y divide-slate-100">
            {users.map((user) => (
              <li key={user.id} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <span className="font-medium text-slate-800">{user.name}</span>{" "}
                  <span className="text-slate-400">· {user.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={user.role}
                    onChange={(e) => changeRole(user.id, e.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                  >
                    <option value="manager">manager</option>
                    <option value="admin">admin</option>
                  </select>
                  <button onClick={() => deleteUser(user.id)} className="text-xs text-rose-500 hover:underline">
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <form onSubmit={addUser} className="grid gap-2 sm:grid-cols-5">
            <input placeholder="Name" required value={newUser.name}
                   onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                   className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400" />
            <input placeholder="Email" type="email" required value={newUser.email}
                   onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                   className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400" />
            <input placeholder="Password" type="password" required minLength={6} value={newUser.password}
                   onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                   className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400" />
            <select value={newUser.role}
                    onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400">
              <option value="manager">manager</option>
              <option value="admin">admin</option>
            </select>
            <button className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500">
              Add user
            </button>
          </form>
        </section>
      )}

      {tab === "integrations" && (
        <section className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm">
            <h2 className="mb-3 font-semibold">Connected channels</h2>
            <ul className="space-y-2 text-slate-600">
              <li>📱 <b>Telegram</b> — configure the bot token in <code>.env</code>, set the chat ID under Notifications, then register the webhook (see README).</li>
              <li>✉️ <b>Email (SMTP)</b> — configure <code>SMTP_*</code> in <code>.env</code>; console fallback is used in development.</li>
              <li>🧠 <b>Embeddings</b> — set <code>EMBEDDING_PROVIDER</code> for semantic KB search; offline hashing fallback otherwise.</li>
              <li className="text-slate-400">💬 Slack &amp; Discord — extension points registered in the notification center (senders pending).</li>
            </ul>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <h2 className="mb-3 text-sm font-semibold">Recent outbound deliveries</h2>
            {deliveries.length === 0 && <p className="text-sm text-slate-400">No deliveries yet.</p>}
            <ul className="divide-y divide-slate-50 text-sm">
              {deliveries.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">
                      {d.channel}
                    </span>
                    <span className="text-slate-700">{d.title}</span>
                    <div className="truncate text-xs text-slate-400">{d.recipient} {d.error && `· ${d.error}`}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                    d.status === "sent" ? "bg-emerald-100 text-emerald-700"
                    : d.status === "failed" ? "bg-rose-100 text-rose-700"
                    : "bg-amber-100 text-amber-700"
                  }`}>
                    {d.status}{d.attempts > 1 ? ` ×${d.attempts}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {tab === "billing" && (
        <section className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <div className="text-4xl">💳</div>
          <h2 className="mt-3 font-semibold">Billing & subscription</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Placeholder for the billing module (Stripe integration planned — see roadmap).
            Workspace plans, usage-based AI billing and invoices will live here.
          </p>
        </section>
      )}
    </div>
  );
}
