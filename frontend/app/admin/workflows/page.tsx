"use client";

import { useCallback, useEffect, useState } from "react";
import { api, WorkflowOut } from "@/lib/api";
import {
  Card,
  EmptyState,
  ErrorState,
  focusRing,
  LoadingState,
  PageHeader,
  Toast,
} from "@/components/ui";

/**
 * Visual workflow builder.
 *
 * Administrators compose flows from step cards — question text per language,
 * answer type, quick replies, branching rules and the next step — with live
 * structural validation and a simulator. The raw JSON editor remains under an
 * "Advanced" toggle for power users, but is never required.
 */

type LocalizedText = Record<string, string> | string;

interface Branch {
  if_contains: string[];
  goto: string;
}

interface WorkflowNode {
  field?: string;
  type?: string;
  prompt?: LocalizedText;
  options?: Record<string, string[]> | string[];
  branches?: Branch[];
  next?: string;
  skip_if_known?: boolean;
}

interface Definition {
  start: string;
  nodes: Record<string, WorkflowNode>;
}

interface Analysis {
  reachable: string[];
  unreachable: string[];
  terminal_nodes: string[];
  has_cycle: boolean;
  warnings: string[];
}

interface NodeBlueprint {
  key: string;
  label: string;
  field: string;
  type: string;
  prompt: Record<string, string>;
  options?: Record<string, string[]>;
  skip_if_known?: boolean;
}

interface Template {
  key: string;
  name: string;
  description: string;
  definition: Definition;
}

const FIELD_TYPE_HELP: Record<string, string> = {
  text: "Any free-text answer.",
  choice: "Offers quick-reply buttons; the typed answer is still accepted.",
  number: "Extracts a number (understands “$2k”, “2,000”).",
  email: "Validates an email address and re-asks if malformed.",
  phone: "Validates a phone number and re-asks if malformed.",
};

function localized(value: LocalizedText | undefined, lang: string): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value[lang] ?? "";
}

function localizedOptions(node: WorkflowNode, lang: string): string[] {
  const options = node.options;
  if (!options) return [];
  if (Array.isArray(options)) return options;
  return options[lang] ?? [];
}

function slugify(label: string, existing: string[]): string {
  const base = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "step";
  let candidate = base;
  let counter = 2;
  while (existing.includes(candidate)) candidate = `${base}_${counter++}`;
  return candidate;
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowOut[]>([]);
  const [selected, setSelected] = useState<WorkflowOut | null>(null);
  const [name, setName] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [definition, setDefinition] = useState<Definition>({ start: "", nodes: {} });
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [library, setLibrary] = useState<NodeBlueprint[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [fieldTypes, setFieldTypes] = useState<string[]>([]);
  const [lang, setLang] = useState("en");
  const [advanced, setAdvanced] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("");
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [simulator, setSimulator] = useState<{ open: boolean; answers: string; result: unknown }>({
    open: false, answers: "", result: null,
  });

  const nodeIds = Object.keys(definition.nodes);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [list, meta] = await Promise.all([
        api<WorkflowOut[]>("/api/workflows", {}, true),
        api<{ templates: Template[]; node_library: NodeBlueprint[]; field_types: string[] }>(
          "/api/workflows/templates", {}, true
        ),
      ]);
      setWorkflows(list);
      setTemplates(meta.templates);
      setLibrary(meta.node_library);
      setFieldTypes(meta.field_types);
      if (list.length) select(list[0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
     
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Live structural validation as the flow changes.
  useEffect(() => {
    if (!nodeIds.length) {
      setAnalysis(null);
      return;
    }
    const timer = setTimeout(() => {
      api<Analysis>("/api/workflows/analyze",
        { method: "POST", body: JSON.stringify({ definition }) }, true)
        .then(setAnalysis)
        .catch(() => setAnalysis(null));
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definition]);

  function select(workflow: WorkflowOut) {
    setSelected(workflow);
    setName(workflow.name);
    setIsDefault(Boolean(workflow.is_default));
    setDefinition(workflow.definition as unknown as Definition);
    setJsonDraft(JSON.stringify(workflow.definition, null, 2));
    setMessage(null);
  }

  function startFromTemplate(template: Template) {
    setSelected(null);
    setName(template.name);
    setIsDefault(false);
    setDefinition(structuredClone(template.definition));
    setJsonDraft(JSON.stringify(template.definition, null, 2));
    setMessage({ kind: "ok", text: `Started from “${template.name}”. Save to publish it.` });
  }

  function updateNode(nodeId: string, patch: Partial<WorkflowNode>) {
    setDefinition((prev) => ({
      ...prev,
      nodes: { ...prev.nodes, [nodeId]: { ...prev.nodes[nodeId], ...patch } },
    }));
  }

  function setPrompt(nodeId: string, text: string) {
    const current = definition.nodes[nodeId].prompt;
    const asObject = typeof current === "object" && current !== null ? current : {};
    updateNode(nodeId, { prompt: { ...asObject, [lang]: text } });
  }

  function setOptions(nodeId: string, raw: string) {
    const values = raw.split(",").map((v) => v.trim()).filter(Boolean);
    const current = definition.nodes[nodeId].options;
    const asObject = current && !Array.isArray(current) ? current : {};
    updateNode(nodeId, { options: { ...asObject, [lang]: values } });
  }

  function addNode(blueprint?: NodeBlueprint) {
    const label = blueprint?.label ?? "New step";
    const id = slugify(blueprint?.key ?? label, nodeIds);
    const newNode: WorkflowNode = blueprint
      ? {
          field: blueprint.field, type: blueprint.type, prompt: blueprint.prompt,
          options: blueprint.options, skip_if_known: blueprint.skip_if_known, next: "",
        }
      : { field: id, type: "text", prompt: { en: "" }, next: "" };

    setDefinition((prev) => {
      const nodes = { ...prev.nodes, [id]: newNode };
      const ids = Object.keys(prev.nodes);
      // Append to the end of the chain: the previous terminal step now points here.
      const terminal = ids.find((n) => !prev.nodes[n].next && !prev.nodes[n].branches?.length);
      if (terminal) nodes[terminal] = { ...nodes[terminal], next: id };
      return { start: prev.start || id, nodes };
    });
  }

  function removeNode(nodeId: string) {
    setDefinition((prev) => {
      const nodes: Record<string, WorkflowNode> = {};
      for (const [id, node] of Object.entries(prev.nodes)) {
        if (id === nodeId) continue;
        nodes[id] = {
          ...node,
          next: node.next === nodeId ? "" : node.next,
          branches: (node.branches ?? []).filter((b) => b.goto !== nodeId),
        };
      }
      const remaining = Object.keys(nodes);
      return {
        start: prev.start === nodeId ? (remaining[0] ?? "") : prev.start,
        nodes,
      };
    });
  }

  function moveNode(nodeId: string, direction: -1 | 1) {
    // Reorders the visual list; the flow is defined by `next`, so re-link the
    // chain after reordering to keep the visible order and the actual order in sync.
    const ids = [...nodeIds];
    const index = ids.indexOf(nodeId);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];

    setDefinition((prev) => {
      const nodes: Record<string, WorkflowNode> = {};
      ids.forEach((id, position) => {
        nodes[id] = { ...prev.nodes[id], next: ids[position + 1] ?? "" };
      });
      return { start: ids[0], nodes };
    });
  }

  function addBranch(nodeId: string) {
    const branches = [...(definition.nodes[nodeId].branches ?? []),
                      { if_contains: [], goto: "" }];
    updateNode(nodeId, { branches });
  }

  function updateBranch(nodeId: string, index: number, patch: Partial<Branch>) {
    const branches = [...(definition.nodes[nodeId].branches ?? [])];
    branches[index] = { ...branches[index], ...patch };
    updateNode(nodeId, { branches });
  }

  function removeBranch(nodeId: string, index: number) {
    const branches = (definition.nodes[nodeId].branches ?? []).filter((_, i) => i !== index);
    updateNode(nodeId, { branches });
  }

  async function save() {
    let payload = definition;
    if (advanced) {
      try {
        payload = JSON.parse(jsonDraft);
      } catch {
        setMessage({ kind: "err", text: "Invalid JSON — fix the syntax before saving." });
        return;
      }
    }
    try {
      const body = JSON.stringify({
        name, definition: payload, is_default: isDefault,
        prompt_name: selected?.prompt_name ?? "",
      });
      const saved = selected
        ? await api<WorkflowOut>(`/api/workflows/${selected.id}`, { method: "PUT", body }, true)
        : await api<WorkflowOut>("/api/workflows", { method: "POST", body }, true);
      setMessage({ kind: "ok", text: "Saved — new conversations use this flow immediately." });
      const list = await api<WorkflowOut[]>("/api/workflows", {}, true);
      setWorkflows(list);
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
      setDefinition({ start: "", nodes: {} });
      const list = await api<WorkflowOut[]>("/api/workflows", {}, true);
      setWorkflows(list);
      if (list.length) select(list[0]);
      setMessage({ kind: "ok", text: "Workflow deleted." });
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Delete failed" });
    }
  }

  async function runSimulation() {
    const answers = simulator.answers.split("\n").map((a) => a.trim()).filter(Boolean);
    try {
      const result = await api("/api/workflows/simulate",
        { method: "POST", body: JSON.stringify({ definition, answers, language: lang }) }, true);
      setSimulator((s) => ({ ...s, result }));
    } catch (e) {
      setMessage({ kind: "err", text: e instanceof Error ? e.message : "Simulation failed" });
    }
  }

  if (loading) return <LoadingState label="Loading workflows" rows={6} />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Conversation workflows"
        description="Build intake flows visually — no JSON required. Changes apply to new conversations immediately."
        actions={
          <>
            <label className="sr-only" htmlFor="builder-lang">Editing language</label>
            <select
              id="builder-lang"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className={`rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
            >
              <option value="en">🇬🇧 English</option>
              <option value="uk">🇺🇦 Українська</option>
            </select>
            <button
              onClick={() => setSimulator((s) => ({ ...s, open: !s.open }))}
              className={`rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100 ${focusRing}`}
            >
              ▶ Test flow
            </button>
          </>
        }
      />

      {message && (
        <div className="mb-4">
          <Toast kind={message.kind} message={message.text} onDismiss={() => setMessage(null)} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-4">
        {/* Sidebar: existing flows + templates */}
        <div className="space-y-4 lg:col-span-1">
          <div className="space-y-2">
            {workflows.map((workflow) => (
              <button
                key={workflow.id}
                onClick={() => select(workflow)}
                aria-current={selected?.id === workflow.id ? "true" : undefined}
                className={`w-full rounded-lg border px-3 py-2.5 text-left text-sm transition ${focusRing} ${
                  selected?.id === workflow.id
                    ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="font-medium">{workflow.name}</div>
                <div className="text-xs text-slate-400">
                  {Object.keys((workflow.definition as unknown as Definition).nodes ?? {}).length} steps
                  {workflow.is_default ? " · default" : ""}
                </div>
              </button>
            ))}
          </div>

          <Card title="Start from a template">
            <ul className="space-y-2">
              {templates.map((template) => (
                <li key={template.key}>
                  <button
                    onClick={() => startFromTemplate(template)}
                    className={`w-full rounded-lg border border-dashed border-slate-300 px-3 py-2 text-left text-sm text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50/50 ${focusRing}`}
                  >
                    <span className="font-medium">{template.name}</span>
                    <span className="mt-0.5 block text-xs text-slate-400">
                      {template.description}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        {/* Builder */}
        <div className="space-y-4 lg:col-span-3">
          <Card>
            <div className="flex flex-wrap items-center gap-3">
              <label className="sr-only" htmlFor="workflow-name">Workflow name</label>
              <input
                id="workflow-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Workflow name"
                className={`flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium ${focusRing}`}
              />
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="rounded"
                />
                Default flow
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-500">
                <input
                  type="checkbox"
                  checked={advanced}
                  onChange={(e) => {
                    setAdvanced(e.target.checked);
                    if (e.target.checked) setJsonDraft(JSON.stringify(definition, null, 2));
                    else {
                      try {
                        setDefinition(JSON.parse(jsonDraft));
                      } catch {
                        /* keep the visual model when the draft is invalid */
                      }
                    }
                  }}
                  className="rounded"
                />
                Advanced (JSON)
              </label>
            </div>
          </Card>

          {analysis && analysis.warnings.length > 0 && (
            <div
              role="status"
              className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
            >
              <p className="font-medium">Flow check</p>
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-amber-800">
                {analysis.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {simulator.open && (
            <Card title="Test this flow">
              <p className="mb-2 text-xs text-slate-500">
                Enter one answer per line; the simulator replays the flow exactly as the
                engine would, without touching the database or the AI provider.
              </p>
              <textarea
                value={simulator.answers}
                onChange={(e) => setSimulator((s) => ({ ...s, answers: e.target.value }))}
                placeholder={"Alice\nOnline store\n$5000"}
                className={`h-24 w-full rounded-lg border border-slate-200 p-3 font-mono text-xs ${focusRing}`}
              />
              <button
                onClick={runSimulation}
                className={`mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700 ${focusRing}`}
              >
                Run simulation
              </button>
              {simulator.result != null && (
                <pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                  {JSON.stringify(simulator.result, null, 2)}
                </pre>
              )}
            </Card>
          )}

          {advanced ? (
            <Card title="Raw definition">
              <textarea
                value={jsonDraft}
                onChange={(e) => setJsonDraft(e.target.value)}
                spellCheck={false}
                aria-label="Workflow JSON definition"
                className={`h-96 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs ${focusRing}`}
              />
            </Card>
          ) : nodeIds.length === 0 ? (
            <EmptyState
              icon="🔀"
              title="This flow has no steps yet"
              description="Add a step from the library below, or start from a template."
            />
          ) : (
            <ol className="space-y-3">
              {nodeIds.map((nodeId, index) => {
                const node = definition.nodes[nodeId];
                const isStart = definition.start === nodeId;
                const isEnd = !node.next && !node.branches?.length;
                return (
                  <li key={nodeId}>
                    <Card className={isStart ? "border-indigo-300" : ""}>
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                            {index + 1}
                          </span>
                          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                            {nodeId}
                          </code>
                          {isStart && (
                            <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                              START
                            </span>
                          )}
                          {isEnd && (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                              ENDS FLOW → creates lead
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => moveNode(nodeId, -1)}
                            disabled={index === 0}
                            aria-label={`Move step ${index + 1} up`}
                            className={`rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30 ${focusRing}`}
                          >
                            ↑
                          </button>
                          <button
                            onClick={() => moveNode(nodeId, 1)}
                            disabled={index === nodeIds.length - 1}
                            aria-label={`Move step ${index + 1} down`}
                            className={`rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30 ${focusRing}`}
                          >
                            ↓
                          </button>
                          <button
                            onClick={() => setDefinition((p) => ({ ...p, start: nodeId }))}
                            disabled={isStart}
                            className={`rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 ${focusRing}`}
                          >
                            Set as start
                          </button>
                          <button
                            onClick={() => removeNode(nodeId)}
                            aria-label={`Delete step ${nodeId}`}
                            className={`rounded p-1 text-rose-500 hover:bg-rose-50 ${focusRing}`}
                          >
                            🗑
                          </button>
                        </div>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="sm:col-span-2">
                          <label
                            className="mb-1 block text-xs font-medium text-slate-500"
                            htmlFor={`prompt-${nodeId}`}
                          >
                            Question the bot asks ({lang.toUpperCase()})
                          </label>
                          <textarea
                            id={`prompt-${nodeId}`}
                            value={localized(node.prompt, lang)}
                            onChange={(e) => setPrompt(nodeId, e.target.value)}
                            className={`h-16 w-full rounded-lg border border-slate-200 p-2.5 text-sm ${focusRing}`}
                          />
                        </div>

                        <div>
                          <label
                            className="mb-1 block text-xs font-medium text-slate-500"
                            htmlFor={`field-${nodeId}`}
                          >
                            Save answer as
                          </label>
                          <input
                            id={`field-${nodeId}`}
                            value={node.field ?? ""}
                            onChange={(e) => updateNode(nodeId, { field: e.target.value })}
                            placeholder="e.g. budget"
                            className={`w-full rounded-lg border border-slate-200 px-3 py-2 text-sm ${focusRing}`}
                          />
                        </div>

                        <div>
                          <label
                            className="mb-1 block text-xs font-medium text-slate-500"
                            htmlFor={`type-${nodeId}`}
                          >
                            Answer type
                          </label>
                          <select
                            id={`type-${nodeId}`}
                            value={node.type ?? "text"}
                            onChange={(e) => updateNode(nodeId, { type: e.target.value })}
                            className={`w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
                          >
                            {(fieldTypes.length ? fieldTypes : ["text"]).map((type) => (
                              <option key={type} value={type}>{type}</option>
                            ))}
                          </select>
                          <p className="mt-1 text-[11px] text-slate-400">
                            {FIELD_TYPE_HELP[node.type ?? "text"]}
                          </p>
                        </div>

                        <div className="sm:col-span-2">
                          <label
                            className="mb-1 block text-xs font-medium text-slate-500"
                            htmlFor={`options-${nodeId}`}
                          >
                            Quick replies (comma-separated, optional)
                          </label>
                          <input
                            id={`options-${nodeId}`}
                            value={localizedOptions(node, lang).join(", ")}
                            onChange={(e) => setOptions(nodeId, e.target.value)}
                            placeholder="Website, Online store, Mobile app"
                            className={`w-full rounded-lg border border-slate-200 px-3 py-2 text-sm ${focusRing}`}
                          />
                        </div>

                        <div>
                          <label
                            className="mb-1 block text-xs font-medium text-slate-500"
                            htmlFor={`next-${nodeId}`}
                          >
                            Next step
                          </label>
                          <select
                            id={`next-${nodeId}`}
                            value={node.next ?? ""}
                            onChange={(e) => updateNode(nodeId, { next: e.target.value })}
                            className={`w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ${focusRing}`}
                          >
                            <option value="">— End the conversation —</option>
                            {nodeIds.filter((id) => id !== nodeId).map((id) => (
                              <option key={id} value={id}>{id}</option>
                            ))}
                          </select>
                        </div>

                        <div className="flex items-end">
                          <label className="flex items-center gap-2 text-sm text-slate-600">
                            <input
                              type="checkbox"
                              checked={Boolean(node.skip_if_known)}
                              onChange={(e) => updateNode(nodeId, { skip_if_known: e.target.checked })}
                              className="rounded"
                            />
                            Skip if already known
                          </label>
                        </div>
                      </div>

                      {/* Branching */}
                      <div className="mt-3 rounded-lg bg-slate-50 p-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-600">
                            Branching rules ({(node.branches ?? []).length})
                          </span>
                          <button
                            onClick={() => addBranch(nodeId)}
                            className={`rounded px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 ${focusRing}`}
                          >
                            + Add rule
                          </button>
                        </div>
                        {(node.branches ?? []).map((branch, branchIndex) => (
                          <div
                            key={branchIndex}
                            className="mt-2 flex flex-wrap items-center gap-2 text-xs"
                          >
                            <span className="text-slate-500">If answer contains</span>
                            <input
                              value={branch.if_contains.join(", ")}
                              onChange={(e) =>
                                updateBranch(nodeId, branchIndex, {
                                  if_contains: e.target.value.split(",").map((v) => v.trim()).filter(Boolean),
                                })
                              }
                              aria-label="Keywords"
                              placeholder="store, shop"
                              className={`min-w-32 flex-1 rounded border border-slate-200 px-2 py-1 ${focusRing}`}
                            />
                            <span className="text-slate-500">go to</span>
                            <select
                              value={branch.goto}
                              onChange={(e) => updateBranch(nodeId, branchIndex, { goto: e.target.value })}
                              aria-label="Target step"
                              className={`rounded border border-slate-200 bg-white px-2 py-1 ${focusRing}`}
                            >
                              <option value="">— select —</option>
                              {nodeIds.map((id) => (
                                <option key={id} value={id}>{id}</option>
                              ))}
                            </select>
                            <button
                              onClick={() => removeBranch(nodeId, branchIndex)}
                              aria-label="Remove branching rule"
                              className={`rounded p-1 text-rose-500 hover:bg-rose-50 ${focusRing}`}
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ol>
          )}

          {!advanced && (
            <Card title="Add a step">
              <div className="flex flex-wrap gap-2">
                {library.map((blueprint) => (
                  <button
                    key={blueprint.key}
                    onClick={() => addNode(blueprint)}
                    className={`rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 ${focusRing}`}
                  >
                    + {blueprint.label}
                  </button>
                ))}
                <button
                  onClick={() => addNode()}
                  className={`rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-500 hover:border-indigo-300 hover:text-indigo-600 ${focusRing}`}
                >
                  + Blank step
                </button>
              </div>
            </Card>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              onClick={save}
              className={`rounded-lg bg-slate-900 px-5 py-2 text-sm font-medium text-white hover:bg-slate-700 ${focusRing}`}
            >
              Save workflow
            </button>
            {selected && !selected.is_default && (
              <button
                onClick={remove}
                className={`rounded-lg border border-rose-200 px-4 py-2 text-sm text-rose-600 hover:bg-rose-50 ${focusRing}`}
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
