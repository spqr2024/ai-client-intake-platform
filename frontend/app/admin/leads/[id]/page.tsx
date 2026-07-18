"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  API_URL,
  formatBudget,
  getToken,
  LeadDetail,
  PRIORITIES,
  priorityColor,
  ReplayEvent,
  scoreColor,
  statusColor,
  UserOut,
} from "@/lib/api";

/** Attachments are staff-only, so they are fetched with the auth header and
 *  handed to the browser as an object URL rather than linked directly. */
async function downloadAttachment(id: number, filename: string) {
  const resp = await fetch(`${API_URL}/api/chat/attachments/${id}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!resp.ok) return;
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function Markdownish({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <p key={i} className="min-h-[1em]">
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={j}>{part.slice(2, -2)}</strong>
            ) : (
              <span key={j}>{part}</span>
            )
          )}
        </p>
      ))}
    </>
  );
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [users, setUsers] = useState<UserOut[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [noteKind, setNoteKind] = useState<"note" | "comment">("comment");
  const [tagsInput, setTagsInput] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"overview" | "replay">("overview");

  const load = useCallback(async () => {
    try {
      const detail = await api<LeadDetail>(`/api/leads/${id}`, {}, true);
      setLead(detail);
      setTagsInput(detail.tags.join(", "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load lead");
    }
  }, [id]);

  useEffect(() => {
    load();
    api<UserOut[]>("/api/users", {}, true).then(setUsers).catch(() => {});
    api<{ statuses: string[] }>("/api/leads/pipeline", {}, true)
      .then((body) => setStatuses(body.statuses))
      .catch(() => {});
  }, [load]);

  async function update(patch: Record<string, unknown>) {
    try {
      const updated = await api<LeadDetail>(
        `/api/leads/${id}`, { method: "PATCH", body: JSON.stringify(patch) }, true
      );
      setLead(updated);
      setTagsInput(updated.tags.join(", "));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function addNote(e: React.FormEvent) {
    e.preventDefault();
    if (!note.trim()) return;
    await api(`/api/leads/${id}/notes`,
              { method: "POST", body: JSON.stringify({ text: note, kind: noteKind }) }, true);
    setNote("");
    load();
  }

  if (error && !lead) return <div className="rounded-lg bg-rose-50 p-4 text-rose-700">{error}</div>;
  if (!lead) return <div className="text-slate-400">Loading…</div>;

  return (
    <div className="mx-auto max-w-5xl">
      <Link href="/admin" className="text-sm text-indigo-600 hover:underline">← Back to leads</Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{lead.project_name || `Lead #${lead.id}`}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-slate-500">
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(lead.status)}`}>
              {lead.status}
            </span>
            <span className={`text-xs font-semibold ${priorityColor(lead.priority)}`}>
              ▲ {lead.priority}
            </span>
            <span>Score: <b className={scoreColor(lead.score)}>{lead.score}/100</b></span>
            <span>Created {new Date(lead.created_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={lead.status}
            onChange={(e) => update({ status: e.target.value })}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            {(statuses.length ? statuses : [lead.status]).map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            value={lead.priority}
            onChange={(e) => update({ priority: e.target.value })}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            {PRIORITIES.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
          <select
            value={lead.assigned_to?.id ?? ""}
            onChange={(e) => e.target.value && update({ assigned_to_id: Number(e.target.value) })}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
          >
            <option value="">Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="mt-4 flex gap-1 rounded-lg border border-slate-200 bg-white p-1 text-sm w-fit">
        {(["overview", "replay"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-4 py-1.5 font-medium capitalize transition ${
              tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t === "overview" ? "Overview" : "▶ Conversation replay"}
          </button>
        ))}
      </div>

      {tab === "replay" ? (
        <ReplayView leadId={lead.id} />
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-3">
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 font-semibold">🧾 AI summary</h2>
              <div className="text-sm leading-relaxed text-slate-700">
                <Markdownish text={lead.summary || "No summary generated."} />
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 font-semibold">💬 Chat transcript</h2>
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {lead.messages.length === 0 && <p className="text-sm text-slate-400">No transcript.</p>}
                {lead.messages.map((m) => (
                  <div key={m.id} className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[80%] whitespace-pre-wrap rounded-xl px-3 py-1.5 text-sm ${
                      m.sender === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                    }`}>
                      {m.text}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {lead.attachments.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-white p-5">
                <h2 className="mb-3 font-semibold">📎 Attachments</h2>
                <ul className="space-y-1 text-sm">
                  {lead.attachments.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-3">
                      <button
                        onClick={() => downloadAttachment(a.id, a.filename)}
                        className="truncate text-left text-indigo-700 hover:underline"
                      >
                        {a.filename}
                      </button>
                      <span className="shrink-0 text-slate-400">
                        {(a.size / 1024).toFixed(1)} KB
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          <div className="space-y-6 lg:col-span-2">
            <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
              <h2 className="mb-3 font-semibold">👤 Client</h2>
              <dl className="space-y-2">
                <Row label="Name" value={lead.client_name || "Anonymous"} />
                <Row label="Email" value={lead.client_email || "—"} />
                <Row label="Phone" value={lead.client_phone || "—"} />
                <Row label="Service" value={lead.service || "—"} />
                <Row label="Budget" value={formatBudget(lead.budget)} />
                <Row label="Timeline" value={lead.timeline || "—"} />
                <Row label="Language" value={lead.language.toUpperCase()} />
              </dl>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
              <h2 className="mb-3 font-semibold">🏷️ Tags & follow-up</h2>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                Tags (comma-separated)
              </label>
              <div className="flex gap-2">
                <input
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="vip, design, referral"
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-indigo-400"
                />
                <button
                  onClick={() => update({ tags: tagsInput.split(",").map((t) => t.trim()).filter(Boolean) })}
                  className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-700"
                >
                  Save
                </button>
              </div>
              <label className="mb-1 mt-4 block text-xs font-medium text-slate-500">
                Follow-up reminder
              </label>
              <div className="flex gap-2">
                <input
                  type="datetime-local"
                  value={lead.follow_up_at ? lead.follow_up_at.slice(0, 16) : ""}
                  onChange={(e) =>
                    e.target.value
                      ? update({ follow_up_at: new Date(e.target.value).toISOString() })
                      : update({ clear_follow_up: true })
                  }
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-indigo-400"
                />
                {lead.follow_up_at && (
                  <button
                    onClick={() => update({ clear_follow_up: true })}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100"
                  >
                    Clear
                  </button>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 font-semibold">🕓 Activity & comments</h2>
              <form onSubmit={addNote} className="mb-3 flex gap-2">
                <select
                  value={noteKind}
                  onChange={(e) => setNoteKind(e.target.value as "note" | "comment")}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
                >
                  <option value="comment">💬</option>
                  <option value="note">📝</option>
                </select>
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder={noteKind === "comment" ? "Internal comment…" : "Note…"}
                  className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-indigo-400"
                />
                <button className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
                  Add
                </button>
              </form>
              <ul className="max-h-72 space-y-3 overflow-y-auto text-sm">
                {lead.activities.slice().reverse().map((a) => (
                  <li key={a.id} className="border-l-2 border-indigo-200 pl-3">
                    <div className="text-slate-700">
                      {a.action === "comment" ? "💬 " : a.action === "note" ? "📝 " : ""}
                      {a.detail}
                    </div>
                    <div className="text-xs text-slate-400">
                      {a.actor} · {a.action} · {new Date(a.created_at).toLocaleString()}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

function ReplayView({ leadId }: { leadId: number }) {
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [visible, setVisible] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api<{ events: ReplayEvent[] }>(`/api/leads/${leadId}/replay`, {}, true)
      .then((body) => {
        setEvents(body.events);
        setVisible(body.events.length);
      })
      .catch(() => {});
  }, [leadId]);

  useEffect(() => {
    if (playing) {
      timerRef.current = setInterval(() => {
        setVisible((v) => {
          if (v >= events.length) {
            setPlaying(false);
            return v;
          }
          return v + 1;
        });
      }, 700);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [playing, events.length]);

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex items-center gap-2">
        <button
          onClick={() => {
            setVisible(0);
            setPlaying(true);
          }}
          className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
        >
          ▶ Replay
        </button>
        <button
          onClick={() => setPlaying(false)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          ⏸
        </button>
        <button
          onClick={() => {
            setPlaying(false);
            setVisible(events.length);
          }}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          ⏭ Show all
        </button>
        <span className="ml-2 text-xs text-slate-400">
          {Math.min(visible, events.length)} / {events.length} events
        </span>
      </div>
      <div className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
        {events.slice(0, visible).map((event, i) => (
          <div key={i}>
            {event.type === "message" ? (
              <div className={`flex ${event.sender === "user" ? "justify-end" : "justify-start"}`}>
                <div className="max-w-[75%]">
                  <div className={`whitespace-pre-wrap rounded-xl px-3 py-1.5 text-sm ${
                    event.sender === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                  }`}>
                    {event.text}
                  </div>
                  <div className={`mt-0.5 text-[10px] text-slate-400 ${event.sender === "user" ? "text-right" : ""}`}>
                    {new Date(event.at).toLocaleTimeString()}
                    {typeof event.meta.node === "string" && event.meta.node && ` · node: ${event.meta.node}`}
                    {typeof event.meta.event === "string" && event.meta.event && ` · ${event.meta.event}`}
                    {typeof event.meta.kb_score === "number" && ` · KB match ${event.meta.kb_score}`}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex justify-center">
                <span className="rounded-full bg-slate-50 px-3 py-1 text-[11px] text-slate-500">
                  {event.type === "attachment" ? "📎" : "⚙️"} {event.text} —{" "}
                  {new Date(event.at).toLocaleTimeString()}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right font-medium text-slate-700">{value}</dd>
    </div>
  );
}
