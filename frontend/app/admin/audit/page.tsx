"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AuditOut } from "@/lib/api";

const ACTION_ICONS: Record<string, string> = {
  login: "🔑",
  login_failed: "🚫",
  logout: "🚪",
  role_change: "👑",
  user_created: "➕",
  user_deleted: "🗑️",
  lead_updated: "📋",
  prompt_edited: "🧠",
  prompt_activated: "✅",
  prompt_deactivated: "⏸️",
  workflow_edited: "🔀",
  kb_updated: "📚",
  settings_updated: "⚙️",
};

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditOut[]>([]);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (action) params.set("action", action);
    if (actor) params.set("actor", actor);
    try {
      setEntries(await api<AuditOut[]>(`/api/audit?${params}`, {}, true));
    } catch {
      /* handled by api() */
    }
  }, [action, actor]);

  useEffect(() => {
    const timer = setTimeout(load, actor ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, actor]);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Audit log</h1>
          <p className="mt-1 text-sm text-slate-500">
            Security and configuration events across the workspace.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="">All actions</option>
            {Object.keys(ACTION_ICONS).map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="Filter by actor…"
            className="w-48 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white">
        {entries.length === 0 && <p className="p-8 text-center text-sm text-slate-400">No entries.</p>}
        <ul className="divide-y divide-slate-50">
          {entries.map((entry) => (
            <li key={entry.id} className="flex items-start gap-3 px-5 py-3 text-sm">
              <span className="mt-0.5">{ACTION_ICONS[entry.action] || "•"}</span>
              <div className="min-w-0 flex-1">
                <div className="text-slate-800">
                  <b>{entry.actor || "system"}</b>{" "}
                  <span className="text-slate-500">{entry.action.replace(/_/g, " ")}</span>
                  {entry.entity && (
                    <span className="text-slate-400"> · {entry.entity} #{entry.entity_id}</span>
                  )}
                </div>
                {entry.detail && (
                  <div className="mt-0.5 truncate text-xs text-slate-500">{entry.detail}</div>
                )}
              </div>
              <div className="shrink-0 text-right text-xs text-slate-400">
                <div>{new Date(entry.created_at).toLocaleString()}</div>
                {entry.ip && <div>{entry.ip}</div>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
