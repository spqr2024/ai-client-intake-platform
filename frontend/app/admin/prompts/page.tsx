"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, PromptOut } from "@/lib/api";
import { PageHeader, Toast } from "@/components/ui";

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<PromptOut[]>([]);
  const [selectedName, setSelectedName] = useState<string>("");
  const [name, setName] = useState("system");
  const [kind, setKind] = useState("system");
  const [content, setContent] = useState("");
  const [sample, setSample] = useState("Hi, I need a website for my bakery");
  const [testOutput, setTestOutput] = useState("");
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setPrompts(await api<PromptOut[]>("/api/prompts", {}, true));
    } catch {
      /* handled by api() */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const groups = useMemo(() => {
    const map = new Map<string, PromptOut[]>();
    for (const prompt of prompts) {
      map.set(prompt.name, [...(map.get(prompt.name) || []), prompt]);
    }
    return map;
  }, [prompts]);

  const versions = selectedName ? groups.get(selectedName) || [] : [];

  function selectGroup(groupName: string) {
    setSelectedName(groupName);
    const active = (groups.get(groupName) || []).find((p) => p.is_active);
    const latest = (groups.get(groupName) || [])[0];
    const source = active || latest;
    if (source) {
      setName(source.name);
      setKind(source.kind);
      setContent(source.content);
    }
    setMessage(null);
    setTestOutput("");
  }

  async function saveVersion() {
    try {
      await api("/api/prompts", {
        method: "POST",
        body: JSON.stringify({ name, kind, content, activate: true }),
      }, true);
      setMessage({ kind: "ok", text: "New version saved and activated." });
      await load();
      setSelectedName(name);
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Save failed" });
    }
  }

  async function activate(promptId: number) {
    await api(`/api/prompts/${promptId}/activate`, { method: "POST" }, true);
    setMessage({ kind: "ok", text: "Version activated (rollback complete)." });
    load();
  }

  async function deactivate(promptId: number) {
    await api(`/api/prompts/${promptId}/deactivate`, { method: "POST" }, true);
    load();
  }

  async function runTest() {
    setTestOutput("Running…");
    try {
      const body = await api<{ provider: string; output: string }>("/api/prompts/test", {
        method: "POST",
        body: JSON.stringify({ content, sample_input: sample }),
      }, true);
      setTestOutput(`[${body.provider}] ${body.output}`);
    } catch (e) {
      setTestOutput(e instanceof Error ? `Error: ${e.message}` : "Test failed");
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Prompt management"
        description={
          "Versioned prompts with activation and rollback. Assign a prompt to a workflow by name " +
          "on the Workflows page; “system” and “summary” are used by default."
        }
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <div className="space-y-2 lg:col-span-1">
          {[...groups.keys()].map((groupName) => {
            const groupVersions = groups.get(groupName) || [];
            const active = groupVersions.find((p) => p.is_active);
            return (
              <button
                key={groupName}
                onClick={() => selectGroup(groupName)}
                className={`w-full rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  selectedName === groupName
                    ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="font-medium">{groupName}</div>
                <div className="text-xs text-slate-400">
                  {groupVersions.length} version{groupVersions.length === 1 ? "" : "s"}
                  {active ? ` · v${active.version} active` : " · none active"}
                </div>
              </button>
            );
          })}
          <button
            onClick={() => {
              setSelectedName("");
              setName("new-prompt");
              setKind("custom");
              setContent("");
              setTestOutput("");
            }}
            className="w-full rounded-lg border border-dashed border-slate-300 px-3 py-2.5 text-sm text-slate-500 hover:border-indigo-300 hover:text-indigo-600"
          >
            + New prompt
          </button>
        </div>

        <div className="space-y-4 lg:col-span-3">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-3 flex flex-wrap gap-3">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Prompt name"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium outline-none focus:border-indigo-400"
              />
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <option value="system">system</option>
                <option value="summary">summary</option>
                <option value="custom">custom</option>
              </select>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              placeholder="Prompt content…"
              className="h-48 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none focus:border-indigo-400"
            />
            {message && (
              <div className="mt-3">
                <Toast kind={message.kind} message={message.text} onDismiss={() => setMessage(null)} />
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={saveVersion}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
              >
                Save as new version
              </button>
              <div className="ml-auto flex items-center gap-2">
                <input
                  value={sample}
                  onChange={(e) => setSample(e.target.value)}
                  placeholder="Sample client message"
                  className="w-64 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                />
                <button
                  onClick={runTest}
                  className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100"
                >
                  🧪 Test
                </button>
              </div>
            </div>
            {testOutput && (
              <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                {testOutput}
              </pre>
            )}
          </div>

          {versions.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="mb-3 text-sm font-semibold">Version history — {selectedName}</h2>
              <ul className="divide-y divide-slate-100">
                {versions.map((version) => (
                  <li key={version.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <div className="min-w-0">
                      <span className="font-medium">v{version.version}</span>
                      {version.is_active ? (
                        <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
                          active
                        </span>
                      ) : null}
                      <div className="truncate text-xs text-slate-400">
                        {version.created_by} · {new Date(version.created_at).toLocaleString()} ·{" "}
                        {version.content.slice(0, 80)}…
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => setContent(version.content)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100"
                      >
                        Load
                      </button>
                      {version.is_active ? (
                        <button
                          onClick={() => deactivate(version.id)}
                          className="rounded-lg border border-amber-200 px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-50"
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          onClick={() => activate(version.id)}
                          className="rounded-lg border border-emerald-200 px-2.5 py-1 text-xs text-emerald-700 hover:bg-emerald-50"
                        >
                          Activate
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
