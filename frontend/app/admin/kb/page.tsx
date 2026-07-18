"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_URL, getToken, KBArticle, KBStats, KBVersion } from "@/lib/api";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  focusRing,
  LoadingState,
  PageHeader,
  Toast,
} from "@/components/ui";

const STATUS_STYLE: Record<string, string> = {
  indexed: "bg-emerald-100 text-emerald-800",
  indexing: "bg-sky-100 text-sky-800",
  pending: "bg-slate-100 text-slate-600",
  stale: "bg-amber-100 text-amber-800",
  failed: "bg-rose-100 text-rose-800",
};

const SOURCE_ICON: Record<string, string> = {
  manual: "✍️", pdf: "📕", docx: "📘", md: "📝", txt: "📄",
};

export default function KnowledgeBasePage() {
  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [formats, setFormats] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<KBArticle | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [versionsFor, setVersionsFor] = useState<number | null>(null);
  const [versions, setVersions] = useState<KBVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, statistics, formatInfo] = await Promise.all([
        api<KBArticle[]>("/api/kb", {}, true),
        api<KBStats>("/api/kb/stats", {}, true),
        api<{ formats: Record<string, boolean> }>("/api/kb/formats", {}, true),
      ]);
      setArticles(list);
      setStats(statistics);
      setFormats(formatInfo.formats);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load the knowledge base");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function startEdit(article: KBArticle | null) {
    setEditing(article);
    setCreating(article === null);
    setTitle(article?.title ?? "");
    setContent(article?.content ?? "");
    setMessage(null);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = JSON.stringify({ title, content, language: "en" });
      if (editing) await api(`/api/kb/${editing.id}`, { method: "PUT", body }, true);
      else await api("/api/kb", { method: "POST", body }, true);
      setEditing(null);
      setCreating(false);
      setMessage({ kind: "ok", text: "Saved and re-indexed." });
      load();
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(file: File) {
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(`${API_URL}/api/kb/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        body: form,
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.detail || "Upload failed");
      setMessage({
        kind: "ok",
        text: `Imported “${body.title}” — ${body.chunk_count} passage(s) indexed.`,
      });
      load();
    } catch (err) {
      setMessage({ kind: "err", text: err instanceof Error ? err.message : "Upload failed" });
    } finally {
      setBusy(false);
    }
  }

  async function reindexAll() {
    setBusy(true);
    try {
      const body = await api<{ indexed: number }>("/api/kb/reindex", { method: "POST" }, true);
      setMessage({ kind: "ok", text: `Re-indexed ${body.indexed} document(s).` });
      load();
    } finally {
      setBusy(false);
    }
  }

  async function reindexOne(id: number) {
    await api(`/api/kb/${id}/reindex`, { method: "POST" }, true);
    load();
  }

  async function remove(id: number) {
    await api(`/api/kb/${id}`, { method: "DELETE" }, true);
    if (editing?.id === id) setEditing(null);
    load();
  }

  async function showVersions(id: number) {
    if (versionsFor === id) {
      setVersionsFor(null);
      return;
    }
    const list = await api<KBVersion[]>(`/api/kb/${id}/versions`, {}, true);
    setVersions(list);
    setVersionsFor(id);
  }

  async function restore(articleId: number, version: number) {
    await api(`/api/kb/${articleId}/versions/${version}/restore`, { method: "POST" }, true);
    setMessage({ kind: "ok", text: `Restored version ${version}.` });
    setVersionsFor(null);
    load();
  }

  const acceptedExtensions = Object.entries(formats)
    .filter(([, enabled]) => enabled)
    .map(([extension]) => extension)
    .join(",");
  const unavailable = Object.entries(formats).filter(([, enabled]) => !enabled).map(([e]) => e);

  if (loading) return <LoadingState label="Loading knowledge base" rows={5} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Knowledge base"
        description="The chat bot answers off-script visitor questions from these documents."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              hidden
              accept={acceptedExtensions}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) uploadDocument(file);
                e.target.value = "";
              }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              className={`rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 ${focusRing}`}
            >
              📎 Upload document
            </button>
            <button
              onClick={reindexAll}
              disabled={busy}
              className={`rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 ${focusRing}`}
            >
              ♻ Re-index all
            </button>
            <button
              onClick={() => startEdit(null)}
              className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 ${focusRing}`}
            >
              + New article
            </button>
          </>
        }
      />

      {message && (
        <div className="mb-4">
          <Toast kind={message.kind} message={message.text} onDismiss={() => setMessage(null)} />
        </div>
      )}

      {stats && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Documents", value: String(articles.length) },
            { label: "Indexed passages", value: String(stats.indexed_chunks) },
            { label: "Searches", value: String(stats.total_searches) },
            { label: "Answer rate", value: `${Math.round(stats.hit_rate * 100)}%` },
          ].map((tile) => (
            <div key={tile.label} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
                {tile.label}
              </div>
              <div className="mt-1 text-2xl font-bold text-slate-900">{tile.value}</div>
            </div>
          ))}
        </div>
      )}

      {unavailable.length > 0 && (
        <p className="mb-4 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600">
          Upload formats <b>{unavailable.join(", ")}</b> need optional packages
          (<code>pypdf</code>, <code>python-docx</code>). Everything else works; install them to
          enable those formats.
        </p>
      )}

      {(creating || editing) && (
        <form onSubmit={save} className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/50 p-5">
          <label className="sr-only" htmlFor="kb-title">Article title</label>
          <input
            id="kb-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Article title (phrase it as the question clients ask)"
            required
            className={`mb-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium ${focusRing}`}
          />
          <label className="sr-only" htmlFor="kb-content">Article content</label>
          <textarea
            id="kb-content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Answer content…"
            required
            className={`h-40 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm ${focusRing}`}
          />
          <div className="mt-3 flex gap-2">
            <button
              disabled={busy}
              className={`rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 ${focusRing}`}
            >
              {editing ? "Update & re-index" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setCreating(false);
              }}
              className={`rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 ${focusRing}`}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="space-y-3">
        {articles.length === 0 && (
          <EmptyState
            icon="📚"
            title="No documents yet"
            description="Add FAQs manually or upload a PDF, DOCX, Markdown or text file. The bot answers visitor questions from whatever you index here."
          />
        )}
        {articles.map((article) => (
          <Card key={article.id}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span aria-hidden="true">{SOURCE_ICON[article.source_type] ?? "📄"}</span>
                  <h3 className="font-semibold text-slate-900">{article.title}</h3>
                  <Badge className={STATUS_STYLE[article.index_status] ?? "bg-slate-100"}>
                    {article.index_status}
                  </Badge>
                  <span className="text-xs text-slate-400">
                    v{article.version} · {article.chunk_count} passage(s) · {article.hit_count} hit(s)
                  </span>
                </div>
                {article.index_error && (
                  <p role="alert" className="mt-1 text-xs text-rose-600">
                    Indexing error: {article.index_error}
                  </p>
                )}
                <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                  {article.content}
                </p>
                {article.source_filename && (
                  <p className="mt-1 text-xs text-slate-400">Source: {article.source_filename}</p>
                )}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <button
                  onClick={() => showVersions(article.id)}
                  className={`rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 ${focusRing}`}
                >
                  History
                </button>
                <button
                  onClick={() => reindexOne(article.id)}
                  className={`rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 ${focusRing}`}
                >
                  Re-index
                </button>
                <button
                  onClick={() => startEdit(article)}
                  className={`rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 ${focusRing}`}
                >
                  Edit
                </button>
                <button
                  onClick={() => remove(article.id)}
                  className={`rounded-lg border border-rose-200 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50 ${focusRing}`}
                >
                  Delete
                </button>
              </div>
            </div>

            {versionsFor === article.id && (
              <div className="mt-4 rounded-lg bg-slate-50 p-3">
                <p className="mb-2 text-xs font-medium text-slate-600">Version history</p>
                {versions.length === 0 ? (
                  <p className="text-xs text-slate-400">
                    No previous versions — edits create history from now on.
                  </p>
                ) : (
                  <ul className="divide-y divide-slate-200 text-xs">
                    {versions.map((version) => (
                      <li key={version.id} className="flex items-center justify-between gap-3 py-2">
                        <div className="min-w-0">
                          <span className="font-medium">v{version.version}</span>{" "}
                          <span className="text-slate-400">
                            {version.created_by} · {new Date(version.created_at).toLocaleString()}
                          </span>
                          <div className="truncate text-slate-500">{version.title}</div>
                        </div>
                        <button
                          onClick={() => restore(article.id, version.version)}
                          className={`shrink-0 rounded-lg border border-emerald-200 px-2.5 py-1 text-emerald-700 hover:bg-emerald-50 ${focusRing}`}
                        >
                          Restore
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>

      {stats && (stats.top_articles.length > 0 || stats.unanswered_queries.length > 0) && (
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <Card title="Most useful documents">
            {stats.top_articles.length === 0 ? (
              <p className="text-sm text-slate-400">No retrievals recorded yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {stats.top_articles.map((item) => (
                  <li key={item.id} className="flex items-center justify-between gap-3">
                    <span className="truncate text-slate-700">{item.title}</span>
                    <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                      ×{item.hits}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Questions the KB could not answer">
            {stats.unanswered_queries.length === 0 ? (
              <p className="text-sm text-slate-400">
                Nothing unanswered — every search found a document. 🎉
              </p>
            ) : (
              <>
                <p className="mb-2 text-xs text-slate-500">
                  Each of these is a candidate for a new article.
                </p>
                <ul className="space-y-2 text-sm">
                  {stats.unanswered_queries.map((item) => (
                    <li key={item.query} className="flex items-start justify-between gap-3">
                      <span className="text-slate-700">{item.query}</span>
                      <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
                        ×{item.count}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
