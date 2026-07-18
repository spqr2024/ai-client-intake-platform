"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  formatBudget,
  LEAD_STATUSES,
  LeadListItem,
  scoreColor,
  statusColor,
} from "@/lib/api";

export default function LeadsPage() {
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    try {
      setLeads(await api<LeadListItem[]>(`/api/leads?${params}`, {}, true));
    } catch {
      /* auth redirect handled by api() */
    } finally {
      setLoading(false);
    }
  }, [status, search]);

  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Leads</h1>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, project, email…"
            className="w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-400"
          />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {["", ...LEAD_STATUSES].map((s) => (
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

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Project</th>
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3">Service</th>
              <th className="px-4 py-3">Budget</th>
              <th className="px-4 py-3">Timeline</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-slate-400">
                  Loading…
                </td>
              </tr>
            ) : leads.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-slate-400">
                  No leads yet. Try the chat widget on the landing page!
                </td>
              </tr>
            ) : (
              leads.map((lead) => (
                <tr key={lead.id} className="border-b border-slate-50 transition hover:bg-indigo-50/40">
                  <td className="px-4 py-3">
                    <Link href={`/admin/leads/${lead.id}`} className="font-medium text-indigo-700 hover:underline">
                      {lead.project_name || `Lead #${lead.id}`}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{lead.client_name || <span className="text-slate-400">Anonymous</span>}</td>
                  <td className="px-4 py-3">{lead.service || "—"}</td>
                  <td className="px-4 py-3">{formatBudget(lead.budget)}</td>
                  <td className="px-4 py-3">{lead.timeline || "—"}</td>
                  <td className={`px-4 py-3 font-semibold ${scoreColor(lead.score)}`}>{lead.score}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusColor(lead.status)}`}>
                      {lead.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(lead.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
