"use client";

import { useCallback, useEffect, useState } from "react";
import { api, KBArticle } from "@/lib/api";

export default function KnowledgeBasePage() {
  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [editing, setEditing] = useState<KBArticle | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setArticles(await api<KBArticle[]>("/api/kb", {}, true));
    } catch {
      /* handled by api() */
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
    setError("");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      const body = JSON.stringify({ title, content, language: "en" });
      if (editing) await api(`/api/kb/${editing.id}`, { method: "PUT", body }, true);
      else await api("/api/kb", { method: "POST", body }, true);
      setEditing(null);
      setCreating(false);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function remove(id: number) {
    await api(`/api/kb/${id}`, { method: "DELETE" }, true);
    if (editing?.id === id) setEditing(null);
    load();
  }

  const showForm = creating || editing;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Knowledge base</h1>
          <p className="mt-1 text-sm text-slate-500">
            The chat bot answers off-script visitor questions from these articles.
          </p>
        </div>
        <button
          onClick={() => startEdit(null)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + New article
        </button>
      </div>

      {showForm && (
        <form onSubmit={save} className="mb-6 rounded-xl border border-indigo-200 bg-indigo-50/50 p-5">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Article title (phrase it as the question clients ask)"
            required
            className="mb-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium outline-none focus:border-indigo-400"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Answer content…"
            required
            className="h-32 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm outline-none focus:border-indigo-400"
          />
          {error && <div className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
          <div className="mt-3 flex gap-2">
            <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
              {editing ? "Update" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setCreating(false);
              }}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="space-y-3">
        {articles.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
            No articles yet. Add FAQs so the bot can answer common questions.
          </p>
        )}
        {articles.map((article) => (
          <div key={article.id} className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-slate-900">{article.title}</h3>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                  {article.content}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => startEdit(article)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                >
                  Edit
                </button>
                <button
                  onClick={() => remove(article.id)}
                  className="rounded-lg border border-rose-200 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
