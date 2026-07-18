"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  formatBudget,
  LeadListItem,
  PRIORITIES,
  priorityColor,
  scoreColor,
  statusColor,
} from "@/lib/api";

type View = "table" | "kanban";

export default function LeadsPage() {
  const [view, setView] = useState<View>("table");
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [columns, setColumns] = useState<Record<string, LeadListItem[]>>({});
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (view === "kanban") {
        const body = await api<{ statuses: string[]; columns: Record<string, LeadListItem[]> }>(
          "/api/leads/pipeline", {}, true
        );
        setStatuses(body.statuses);
        setColumns(body.columns);
      } else {
        const params = new URLSearchParams();
        if (status) params.set("status", status);
        if (priority) params.set("priority", priority);
        if (search) params.set("search", search);
        setLeads(await api<LeadListItem[]>(`/api/leads?${params}`, {}, true));
        const pipeline = await api<{ statuses: string[] }>("/api/leads/pipeline", {}, true);
        setStatuses(pipeline.statuses);
      }
    } catch {
      /* auth redirect handled by api() */
    } finally {
      setLoading(false);
    }
  }, [view, status, priority, search]);

  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  async function moveLead(leadId: number, newStatus: string) {
    // Optimistic column move, server sync after.
    setColumns((prev) => {
      const next: Record<string, LeadListItem[]> = {};
      let moved: LeadListItem | undefined;
      for (const [key, list] of Object.entries(prev)) {
        next[key] = list.filter((lead) => {
          if (lead.id === leadId) {
            moved = lead;
            return false;
          }
          return true;
        });
      }
      if (moved) next[newStatus] = [{ ...moved, status: newStatus }, ...(next[newStatus] || [])];
      return next;
    });
    try {
      await api(`/api/leads/${leadId}`, { method: "PATCH", body: JSON.stringify({ status: newStatus }) }, true);
    } catch {
      load(); // revert to server truth on failure
    }
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Leads</h1>
          <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs">
            {(["table", "kanban"] as View[]).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1.5 font-medium capitalize transition ${
                  view === v ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {v === "table" ? "☰ Table" : "▦ Kanban"}
              </button>
            ))}
          </div>
        </div>
        {view === "table" && (
          <div className="flex items-center gap-2">
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm"
            >
              <option value="">All priorities</option>
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, project, summary…"
              className="w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400"
            />
          </div>
        )}
      </div>

      {view === "table" && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {["", ...statuses].map((s) => (
              <button
                key={s || "all"}
                onClick={() => setStatus(s)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
                  status === s
                    ? "bg-slate-900 text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
                }`}
              >
                {s || "All"}
              </button>
            ))}
          </div>
          <LeadsTable leads={leads} loading={loading} />
        </>
      )}

      {view === "kanban" && (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {statuses.map((columnStatus) => (
            <div
              key={columnStatus}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                const leadId = Number(e.dataTransfer.getData("lead-id"));
                if (leadId) moveLead(leadId, columnStatus);
              }}
              className="flex w-64 shrink-0 flex-col rounded-xl bg-slate-100/70 p-2"
            >
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor(columnStatus)}`}>
                  {columnStatus}
                </span>
                <span className="text-xs text-slate-400">{(columns[columnStatus] || []).length}</span>
              </div>
              <div className="min-h-24 space-y-2">
                {(columns[columnStatus] || []).map((lead) => (
                  <div
                    key={lead.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("lead-id", String(lead.id))}
                    className="cursor-grab rounded-lg border border-slate-200 bg-white p-3 shadow-sm transition hover:shadow active:cursor-grabbing"
                  >
                    <Link href={`/admin/leads/${lead.id}`} className="text-sm font-medium text-indigo-700 hover:underline">
                      {lead.project_name || `Lead #${lead.id}`}
                    </Link>
                    <div className="mt-1 text-xs text-slate-500">
                      {lead.client_name || "Anonymous"} · {formatBudget(lead.budget)}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs">
                      <span className={`font-semibold ${priorityColor(lead.priority)}`}>{lead.priority}</span>
                      <span className={`font-semibold ${scoreColor(lead.score)}`}>{lead.score}</span>
                    </div>
                    {lead.tags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {lead.tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                    {lead.follow_up_at && (
                      <div className="mt-1.5 text-[10px] text-amber-600">
                        ⏰ {new Date(lead.follow_up_at).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LeadsTable({ leads, loading }: { leads: LeadListItem[]; loading: boolean }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Project</th>
            <th className="px-4 py-3">Client</th>
            <th className="px-4 py-3">Budget</th>
            <th className="px-4 py-3">Priority</th>
            <th className="px-4 py-3">Tags</th>
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Follow-up</th>
            <th className="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400">Loading…</td></tr>
          ) : leads.length === 0 ? (
            <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400">
              No leads match. Try the chat widget on the landing page!
            </td></tr>
          ) : (
            leads.map((lead) => (
              <tr key={lead.id} className="border-b border-slate-50 transition hover:bg-indigo-50/40">
                <td className="px-4 py-3">
                  <Link href={`/admin/leads/${lead.id}`} className="font-medium text-indigo-700 hover:underline">
                    {lead.project_name || `Lead #${lead.id}`}
                  </Link>
                </td>
                <td className="px-4 py-3">{lead.client_name || <span className="text-slate-400">Anonymous</span>}</td>
                <td className="px-4 py-3">{formatBudget(lead.budget)}</td>
                <td className={`px-4 py-3 font-medium ${priorityColor(lead.priority)}`}>{lead.priority}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {lead.tags.slice(0, 2).map((tag) => (
                      <span key={tag} className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">{tag}</span>
                    ))}
                  </div>
                </td>
                <td className={`px-4 py-3 font-semibold ${scoreColor(lead.score)}`}>{lead.score}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusColor(lead.status)}`}>
                    {lead.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-amber-700">
                  {lead.follow_up_at ? new Date(lead.follow_up_at).toLocaleDateString() : ""}
                </td>
                <td className="px-4 py-3 text-slate-500">{new Date(lead.created_at).toLocaleDateString()}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
