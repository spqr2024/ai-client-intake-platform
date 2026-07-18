"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  API_URL,
  formatBudget,
  getToken,
  LeadListItem,
  PRIORITIES,
  priorityColor,
  scoreColor,
  statusColor,
  api,
} from "@/lib/api";
import {
  Badge,
  EmptyState,
  ErrorState,
  focusRing,
  LoadingState,
  PageHeader,
  Pagination,
} from "@/components/ui";

type View = "table" | "kanban";
const PAGE_SIZE = 25;

export default function LeadsPage() {
  const [view, setView] = useState<View>("table");
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [columns, setColumns] = useState<Record<string, LeadListItem[]>>({});
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (view === "kanban") {
        const body = await api<{ statuses: string[]; columns: Record<string, LeadListItem[]> }>(
          "/api/leads/pipeline", {}, true
        );
        setStatuses(body.statuses);
        setColumns(body.columns);
      } else {
        const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
        if (status) params.set("status", status);
        if (priority) params.set("priority", priority);
        if (search) params.set("search", search);
        // Read X-Total-Count directly — the list body stays a plain array.
        const resp = await fetch(`${API_URL}/api/leads?${params}`, {
          headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText);
        setLeads(await resp.json());
        setTotal(Number(resp.headers.get("X-Total-Count") ?? 0));
        const pipeline = await api<{ statuses: string[] }>("/api/leads/pipeline", {}, true);
        setStatuses(pipeline.statuses);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
  }, [view, status, priority, search, offset]);

  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  // Any filter change returns to the first page.
  useEffect(() => setOffset(0), [status, priority, search, view]);

  async function moveLead(leadId: number, newStatus: string) {
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
      await api(`/api/leads/${leadId}`,
        { method: "PATCH", body: JSON.stringify({ status: newStatus }) }, true);
    } catch {
      load(); // revert to server truth on failure
    }
  }

  return (
    <div>
      <PageHeader
        title="Leads"
        actions={
          <div
            role="group"
            aria-label="View mode"
            className="flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs"
          >
            {(["table", "kanban"] as View[]).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                className={`rounded-md px-3 py-1.5 font-medium transition ${focusRing} ${
                  view === v ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {v === "table" ? "☰ Table" : "▦ Kanban"}
              </button>
            ))}
          </div>
        }
      />

      {view === "table" && (
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
            {["", ...statuses].map((s) => (
              <button
                key={s || "all"}
                onClick={() => setStatus(s)}
                aria-pressed={status === s}
                className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${focusRing} ${
                  status === s
                    ? "bg-slate-900 text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
                }`}
              >
                {s || "All"}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="priority-filter">Filter by priority</label>
            <select
              id="priority-filter"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className={`rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-sm ${focusRing}`}
            >
              <option value="">All priorities</option>
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="lead-search">Search leads</label>
            <input
              id="lead-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, project, summary…"
              className={`w-full sm:w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
            />
          </div>
        </div>
      )}

      {error ? (
        <ErrorState message={error} onRetry={load} />
      ) : loading ? (
        <LoadingState label="Loading leads" rows={6} />
      ) : view === "table" ? (
        leads.length === 0 ? (
          <EmptyState
            icon="🗂️"
            title={search || status || priority ? "No leads match your filters" : "No leads yet"}
            description={
              search || status || priority
                ? "Try clearing the filters or searching for something else."
                : "Leads appear here as soon as a visitor finishes a chat. Open the landing page and try the widget."
            }
            action={
              <Link
                href="/"
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                Open the chat widget
              </Link>
            }
          />
        ) : (
          <>
            <LeadsTable leads={leads} />
            <Pagination total={total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />
          </>
        )
      ) : (
        <KanbanBoard statuses={statuses} columns={columns} onMove={moveLead} />
      )}
    </div>
  );
}

function LeadsTable({ leads }: { leads: LeadListItem[] }) {
  return (
    <>
      {/* Mobile: cards. A 9-column table is unreadable under ~640px. */}
      <ul className="space-y-2 md:hidden">
        {leads.map((lead) => (
          <li key={lead.id} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <Link
                href={`/admin/leads/${lead.id}`}
                className={`font-medium text-indigo-700 hover:underline ${focusRing}`}
              >
                {lead.project_name || `Lead #${lead.id}`}
              </Link>
              <Badge className={statusColor(lead.status)}>{lead.status}</Badge>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {lead.client_name || "Anonymous"} · {formatBudget(lead.budget)}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
              <span className={priorityColor(lead.priority)}>▲ {lead.priority}</span>
              <span className={scoreColor(lead.score)}>Score {lead.score}</span>
              <span className="text-slate-400">
                {new Date(lead.created_at).toLocaleDateString()}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto rounded-xl border border-slate-200 bg-white md:block">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Leads, newest first</caption>
          <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-3">Project</th>
              <th scope="col" className="px-4 py-3">Client</th>
              <th scope="col" className="px-4 py-3">Budget</th>
              <th scope="col" className="px-4 py-3">Priority</th>
              <th scope="col" className="px-4 py-3">Tags</th>
              <th scope="col" className="px-4 py-3">Score</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3">Follow-up</th>
              <th scope="col" className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr key={lead.id} className="border-b border-slate-50 transition hover:bg-indigo-50/40">
                <td className="px-4 py-3">
                  <Link
                    href={`/admin/leads/${lead.id}`}
                    className={`font-medium text-indigo-700 hover:underline ${focusRing}`}
                  >
                    {lead.project_name || `Lead #${lead.id}`}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  {lead.client_name || <span className="text-slate-400">Anonymous</span>}
                </td>
                <td className="px-4 py-3">{formatBudget(lead.budget)}</td>
                <td className={`px-4 py-3 font-medium ${priorityColor(lead.priority)}`}>
                  {lead.priority}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {lead.tags.slice(0, 2).map((tag) => (
                      <span key={tag} className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">
                        {tag}
                      </span>
                    ))}
                  </div>
                </td>
                <td className={`px-4 py-3 font-semibold ${scoreColor(lead.score)}`}>{lead.score}</td>
                <td className="px-4 py-3">
                  <Badge className={statusColor(lead.status)}>{lead.status}</Badge>
                </td>
                <td className="px-4 py-3 text-xs text-amber-700">
                  {lead.follow_up_at ? new Date(lead.follow_up_at).toLocaleDateString() : ""}
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(lead.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function KanbanBoard({
  statuses,
  columns,
  onMove,
}: {
  statuses: string[];
  columns: Record<string, LeadListItem[]>;
  onMove: (leadId: number, status: string) => void;
}) {
  // Keyboard alternative to drag & drop: select a card, then move it.
  const [selected, setSelected] = useState<number | null>(null);

  if (statuses.every((s) => (columns[s] || []).length === 0)) {
    return (
      <EmptyState
        icon="▦"
        title="Your pipeline is empty"
        description="Completed chats appear here as cards you can drag between stages."
      />
    );
  }

  return (
    <div>
      {selected !== null && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-indigo-50 px-3 py-2 text-sm">
          <span className="text-indigo-800">Lead #{selected} selected — move to:</span>
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => {
                onMove(selected, s);
                setSelected(null);
              }}
              className={`rounded-full border border-indigo-200 bg-white px-2.5 py-1 text-xs text-indigo-700 hover:bg-indigo-100 ${focusRing}`}
            >
              {s}
            </button>
          ))}
          <button
            onClick={() => setSelected(null)}
            className={`ml-auto text-xs text-slate-500 hover:underline ${focusRing}`}
          >
            Cancel
          </button>
        </div>
      )}

      <div className="flex gap-4 overflow-x-auto pb-4">
        {statuses.map((columnStatus) => (
          <section
            key={columnStatus}
            aria-label={`${columnStatus} — ${(columns[columnStatus] || []).length} leads`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              const leadId = Number(e.dataTransfer.getData("lead-id"));
              if (leadId) onMove(leadId, columnStatus);
            }}
            className="flex w-64 shrink-0 flex-col rounded-xl bg-slate-100/70 p-2"
          >
            <div className="flex items-center justify-between px-2 py-1.5">
              <Badge className={statusColor(columnStatus)}>{columnStatus}</Badge>
              <span className="text-xs text-slate-400">
                {(columns[columnStatus] || []).length}
              </span>
            </div>
            <ul className="min-h-24 space-y-2">
              {(columns[columnStatus] || []).map((lead) => (
                <li
                  key={lead.id}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("lead-id", String(lead.id))}
                  className={`cursor-grab rounded-lg border bg-white p-3 shadow-sm transition hover:shadow active:cursor-grabbing ${
                    selected === lead.id ? "border-indigo-400 ring-2 ring-indigo-200" : "border-slate-200"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      href={`/admin/leads/${lead.id}`}
                      className={`text-sm font-medium text-indigo-700 hover:underline ${focusRing}`}
                    >
                      {lead.project_name || `Lead #${lead.id}`}
                    </Link>
                    <button
                      onClick={() => setSelected(selected === lead.id ? null : lead.id)}
                      aria-label={`Move lead ${lead.project_name || lead.id} to another stage`}
                      className={`shrink-0 rounded p-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600 ${focusRing}`}
                    >
                      ⇄
                    </button>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {lead.client_name || "Anonymous"} · {formatBudget(lead.budget)}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs">
                    <span className={`font-semibold ${priorityColor(lead.priority)}`}>
                      {lead.priority}
                    </span>
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
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
