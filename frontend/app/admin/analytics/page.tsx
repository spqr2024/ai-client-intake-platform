"use client";

import { useEffect, useState } from "react";
import { AnalyticsSummary, api } from "@/lib/api";

// Status hues validated for CVD safety (dataviz six-checks, light surface).
// Closed/Incomplete intentionally render neutral gray: inactive states,
// identity carried by direct labels, never color alone.
const STATUS_HEX: Record<string, string> = {
  New: "#0284c7",
  Qualified: "#059669",
  "In Progress": "#d97706",
  Converted: "#7c3aed",
  Rejected: "#e11d48",
  Closed: "#94a3b8",
  Incomplete: "#94a3b8",
};
const SERIES_HUE = "#4f46e5"; // single-series magnitude → one hue

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api<AnalyticsSummary>(`/api/analytics/summary?days=${days}`, {}, true)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [days]);

  if (error) return <div className="rounded-lg bg-rose-50 p-4 text-rose-700">{error}</div>;
  if (!data) return <div className="text-slate-400">Loading…</div>;

  const tiles = [
    { label: "Conversations", value: data.total_conversations.toLocaleString() },
    { label: "Leads", value: data.total_leads.toLocaleString() },
    { label: "Completion rate", value: `${Math.round(data.completion_rate * 100)}%` },
    { label: "Conversion rate", value: `${Math.round(data.conversion_rate * 100)}%` },
    { label: "Avg. budget", value: `$${Math.round(data.average_budget).toLocaleString()}` },
    { label: "Avg. score", value: `${data.average_score}/100` },
  ];

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 text-xs">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-md px-3 py-1.5 font-medium transition ${
                days === d ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{tile.label}</div>
            <div className="mt-1 text-2xl font-bold text-slate-900">{tile.value}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="mb-4 font-semibold">Leads per day (last {days} days)</h2>
          <LineChart points={data.leads_per_day} />
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="mb-4 font-semibold">Leads by status</h2>
          <HBarChart
            rows={Object.entries(data.leads_by_status).map(([label, value]) => ({
              label,
              value,
              color: STATUS_HEX[label] || "#94a3b8",
            }))}
          />
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 lg:col-span-2">
          <h2 className="mb-4 font-semibold">Top services</h2>
          <HBarChart
            rows={Object.entries(data.leads_by_service).map(([label, value]) => ({
              label,
              value,
              color: SERIES_HUE,
            }))}
          />
        </section>
      </div>
    </div>
  );
}

function LineChart({ points }: { points: { date: string; count: number }[] }) {
  const width = 460;
  const height = 180;
  const pad = { left: 30, right: 10, top: 10, bottom: 24 };

  if (points.length === 0)
    return <p className="py-8 text-center text-sm text-slate-400">No data in this period yet.</p>;

  const max = Math.max(...points.map((p) => p.count), 1);
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => pad.top + innerH - (v / max) * innerH;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.count).toFixed(1)}`).join(" ");
  const area = `${path} L${x(points.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Leads per day">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line
            x1={pad.left} x2={width - pad.right}
            y1={y(max * f)} y2={y(max * f)}
            stroke="#e2e8f0" strokeWidth="1"
          />
          <text x={pad.left - 6} y={y(max * f) + 3} textAnchor="end" fontSize="9" fill="#94a3b8">
            {Math.round(max * f)}
          </text>
        </g>
      ))}
      <path d={area} fill={SERIES_HUE} opacity="0.08" />
      <path d={path} fill="none" stroke={SERIES_HUE} strokeWidth="2" strokeLinejoin="round" />
      {points.map((p, i) => (
        <g key={p.date} className="group">
          <circle cx={x(i)} cy={y(p.count)} r="8" fill="transparent" />
          <circle cx={x(i)} cy={y(p.count)} r="3" fill={SERIES_HUE}>
            <title>{`${p.date}: ${p.count} lead${p.count === 1 ? "" : "s"}`}</title>
          </circle>
        </g>
      ))}
      <text x={x(0)} y={height - 6} fontSize="9" fill="#64748b" textAnchor="start">
        {points[0].date}
      </text>
      {points.length > 1 && (
        <text x={x(points.length - 1)} y={height - 6} fontSize="9" fill="#64748b" textAnchor="end">
          {points[points.length - 1].date}
        </text>
      )}
    </svg>
  );
}

function HBarChart({ rows }: { rows: { label: string; value: number; color: string }[] }) {
  if (rows.length === 0)
    return <p className="py-8 text-center text-sm text-slate-400">No data yet.</p>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-2.5">
      {rows
        .slice()
        .sort((a, b) => b.value - a.value)
        .map((row) => (
          <div key={row.label} className="flex items-center gap-3 text-sm" title={`${row.label}: ${row.value}`}>
            <div className="w-28 shrink-0 truncate text-slate-600">{row.label}</div>
            <div className="h-4 flex-1 overflow-hidden rounded-r bg-slate-100">
              <div
                className="h-full rounded-r transition-all"
                style={{ width: `${(row.value / max) * 100}%`, backgroundColor: row.color }}
              />
            </div>
            <div className="w-8 text-right font-semibold text-slate-700">{row.value}</div>
          </div>
        ))}
    </div>
  );
}
