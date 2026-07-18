"use client";

import { useCallback, useEffect, useState } from "react";
import { api, WorkflowOut } from "@/lib/api";

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowOut[]>([]);
  const [selected, setSelected] = useState<WorkflowOut | null>(null);
  const [name, setName] = useState("");
  const [json, setJson] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api<WorkflowOut[]>("/api/workflows", {}, true);
      setWorkflows(list);
      if (!selected && list.length) select(list[0]);
    } catch {
      /* handled by api() */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function select(workflow: WorkflowOut | null) {
    setSelected(workflow);
    setName(workflow?.name ?? "");
    setJson(workflow ? JSON.stringify(workflow.definition, null, 2) : "");
    setIsDefault(Boolean(workflow?.is_default));
    setMessage(null);
  }

  function newWorkflow() {
    select(null);
    setName("New workflow");
    setJson(JSON.stringify({ start: "q1", nodes: { q1: { field: "goals", type: "text", prompt: { en: "Tell us about your project" }, next: "" } } }, null, 2));
  }

  async function save() {
    let definition: Record<string, unknown>;
    try {
      definition = JSON.parse(json);
    } catch {
      setMessage({ kind: "err", text: "Invalid JSON — fix syntax before saving." });
      return;
    }
    try {
      const body = JSON.stringify({ name, definition, is_default: isDefault });
      const saved = selected
        ? await api<WorkflowOut>(`/api/workflows/${selected.id}`, { method: "PUT", body }, true)
        : await api<WorkflowOut>("/api/workflows", { method: "POST", body }, true);
      setMessage({ kind: "ok", text: "Saved. Changes apply to new conversations immediately." });
      await load();
      select(saved);
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Save failed" });
    }
  }

  async function remove() {
    if (!selected) return;
    try {
      await api(`/api/workflows/${selected.id}`, { method: "DELETE" }, true);
      setSelected(null);
      await load();
      select(null);
      setMessage({ kind: "ok", text: "Workflow deleted." });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Delete failed" });
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversation workflows</h1>
        <button
          onClick={newWorkflow}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + New workflow
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-4">
        <div className="space-y-2 lg:col-span-1">
          {workflows.map((workflow) => (
            <button
              key={workflow.id}
              onClick={() => select(workflow)}
              className={`w-full rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                selected?.id === workflow.id
                  ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <div className="font-medium">{workflow.name}</div>
              {Boolean(workflow.is_default) && <div className="text-xs text-indigo-500">default</div>}
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 lg:col-span-3">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium outline-none focus:border-indigo-400"
              placeholder="Workflow name"
            />
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
              Default
            </label>
          </div>
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            spellCheck={false}
            className="h-96 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs outline-none focus:border-indigo-400"
          />
          <p className="mt-2 text-xs text-slate-400">
            Nodes support <code>type</code> (text · choice · number · email · phone), per-language{" "}
            <code>prompt</code>/<code>options</code>, <code>branches</code> with <code>if_contains</code> keywords,
            and <code>next</code>. An empty <code>next</code> ends the flow and creates the lead.
          </p>
          {message && (
            <div
              className={`mt-3 rounded-lg px-3 py-2 text-sm ${
                message.kind === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
              }`}
            >
              {message.text}
            </div>
          )}
          <div className="mt-4 flex gap-2">
            <button
              onClick={save}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Save
            </button>
            {selected && !selected.is_default && (
              <button
                onClick={remove}
                className="rounded-lg border border-rose-200 px-4 py-2 text-sm text-rose-600 hover:bg-rose-50"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
