"use client";

import { useEffect, useState } from "react";
import { api, UserOut } from "@/lib/api";

const FIELDS: { key: string; label: string; kind: "text" | "textarea" | "toggle" | "select"; options?: string[]; hint?: string }[] = [
  { key: "ai_provider", label: "AI provider", kind: "select", options: ["", "mock", "openai", "anthropic", "gemini", "openrouter"], hint: "Empty = use .env value. 'mock' runs fully offline." },
  { key: "ai_model", label: "AI model", kind: "text", hint: "Empty = provider default (e.g. gpt-4o-mini, claude-sonnet-5)." },
  { key: "ai_temperature", label: "Temperature", kind: "text" },
  { key: "ai_max_tokens", label: "Max tokens", kind: "text" },
  { key: "system_prompt", label: "System prompt", kind: "textarea" },
  { key: "summary_prompt", label: "Summary prompt", kind: "textarea" },
  { key: "qualified_score_threshold", label: "Qualified score threshold", kind: "text", hint: "Leads scoring at or above become 'Qualified'." },
  { key: "telegram_enabled", label: "Telegram notifications", kind: "toggle" },
  { key: "email_enabled", label: "Email notifications", kind: "toggle" },
  { key: "client_email_subject", label: "Client email subject", kind: "text" },
  { key: "client_email_body", label: "Client email body", kind: "textarea", hint: "Placeholders: {client_name} {summary} {project_name} {budget} {timeline}" },
  { key: "staff_notification_email", label: "Staff notification email", kind: "text" },
  { key: "staff_email_subject", label: "Staff email subject", kind: "text" },
  { key: "staff_email_body", label: "Staff email body", kind: "textarea" },
];

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<UserOut[]>([]);
  const [newUser, setNewUser] = useState({ name: "", email: "", password: "", role: "manager" });
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    api<{ values: Record<string, string> }>("/api/settings", {}, true)
      .then((body) => setValues(body.values))
      .catch(() => {});
    loadUsers();
  }, []);

  function loadUsers() {
    api<UserOut[]>("/api/users", {}, true).then(setUsers).catch(() => {});
  }

  async function save() {
    try {
      const body = await api<{ values: Record<string, string> }>(
        "/api/settings",
        { method: "PUT", body: JSON.stringify({ values }) },
        true
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

  async function deleteUser(id: number) {
    try {
      await api(`/api/users/${id}`, { method: "DELETE" }, true);
      loadUsers();
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Failed to delete user" });
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-2xl font-bold">Settings</h1>

      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 font-semibold">🤖 Bot & notifications</h2>
        <div className="space-y-4">
          {FIELDS.map((field) => (
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
                    <option key={option} value={option}>
                      {option || "(from .env)"}
                    </option>
                  ))}
                </select>
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
        {message && (
          <div
            className={`mt-4 rounded-lg px-3 py-2 text-sm ${
              message.kind === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
            }`}
          >
            {message.text}
          </div>
        )}
        <button
          onClick={save}
          className="mt-4 rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Save settings
        </button>
      </section>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 font-semibold">👥 Team members</h2>
        <ul className="mb-4 divide-y divide-slate-100">
          {users.map((user) => (
            <li key={user.id} className="flex items-center justify-between py-2.5 text-sm">
              <div>
                <span className="font-medium text-slate-800">{user.name}</span>{" "}
                <span className="text-slate-400">· {user.email}</span>
                <span
                  className={`ml-2 rounded-full px-2 py-0.5 text-xs ${
                    user.role === "admin" ? "bg-violet-100 text-violet-700" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {user.role}
                </span>
              </div>
              <button
                onClick={() => deleteUser(user.id)}
                className="text-xs text-rose-500 hover:underline"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        <form onSubmit={addUser} className="grid gap-2 sm:grid-cols-5">
          <input
            placeholder="Name"
            required
            value={newUser.name}
            onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
          <input
            placeholder="Email"
            type="email"
            required
            value={newUser.email}
            onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
          <input
            placeholder="Password"
            type="password"
            required
            minLength={6}
            value={newUser.password}
            onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
          <select
            value={newUser.role}
            onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400"
          >
            <option value="manager">manager</option>
            <option value="admin">admin</option>
          </select>
          <button className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500">
            Add user
          </button>
        </form>
      </section>
    </div>
  );
}
