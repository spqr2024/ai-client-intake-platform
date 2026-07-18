"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AuditOut } from "@/lib/api";
import { EmptyState, focusRing, PageHeader } from "@/components/ui";

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
      <PageHeader
        title="Audit log"
        description="Security and configuration events across the workspace."
        actions={
          <>
            <label className="sr-only" htmlFor="audit-action">
              Filter by action
            </label>
            <select
              id="audit-action"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className={`rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
            >
              <option value="">All actions</option>
              {Object.keys(ACTION_ICONS).map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="audit-actor">
              Filter by actor
            </label>
            <input
              id="audit-actor"
              type="search"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="Filter by actor…"
              className={`w-48 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
            />
          </>
        }
      />

      {entries.length === 0 ? (
        <EmptyState
          icon="🛡️"
          title="No audit entries"
          description="Logins, role changes and configuration edits are recorded here as they happen."
        />
      ) : (
      <div className="rounded-xl border border-slate-200 bg-white">
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
      )}
    </div>
  );
}
