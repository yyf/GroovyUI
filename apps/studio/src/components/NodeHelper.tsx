import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeAbCompare,
  fetchAudioFileMeta,
  fetchCacheMeta,
  fetchCacheMetrics,
  fetchCompareModels,
  fetchModelCard,
  fetchNodeSchema,
  fetchWaveform,
  uploadProjectAudio,
  type AbCompareResult,
  type CacheSignalMetrics,
} from "../api";
import type { JobOutput, ModelCard, NodeSchema, Workflow, WorkflowNode } from "../types";
import type { CompareHop } from "../workflow";
import { joinSaveAudioPath, jobOutputAtSlot, wiredInputSupersedesWidget, wiredInputsForNode, wiredPromptPreview } from "../workflow";
import { hasMinimalPatch } from "../nodeMinimalPatches";
import { inferenceParamsForModel } from "../modelInferenceParams";
import AudioFormatPanel from "./AudioFormatPanel";
import CompareMetricsViz from "./CompareMetricsViz";
import { ParamFader, ParamPot, ParamStepped, ParamSwitch } from "./ParamControls";
import SocketTypeBadge from "./SocketTypeBadge";
import WaveformCompare from "./WaveformCompare";
import WaveformMini from "./WaveformMini";
import { resolveWidgetControl } from "../widgetControls";

type Tab = "config" | "inputs" | "outputs" | "provenance";

type CompareEntry = {
  node: WorkflowNode;
  output: JobOutput;
};

type Props = {
  node: WorkflowNode | null;
  selectedNodes?: WorkflowNode[];
  selectionOutputs?: Record<string, JobOutput> | null;
  workflow: Workflow;
  output?: JobOutput;
  previewUrl?: string | null;
  comparePair?: CompareEntry[] | null;
  compareNote?: string | null;
  compareMissingRender?: boolean;
  chainHops?: CompareHop[];
  onSelectCompareHop?: (nodeIdA: string, nodeIdB: string) => void;
  showCompare?: boolean;
  onWidgetChange: (nodeId: string, name: string, value: unknown) => void;
  onBrowseModel?: (nodeId: string, widgetName: string) => void;
  onAudition?: () => void;
  onCompareAudition?: (nodeId: string) => void;
  renderIssue?: string | null;
  renderIssueDetail?: string | null;
};

export default function NodeHelper({
  node,
  selectedNodes = [],
  selectionOutputs = null,
  workflow,
  output,
  previewUrl,
  comparePair,
  compareNote,
  compareMissingRender = false,
  chainHops = [],
  onSelectCompareHop,
  showCompare = false,
  onWidgetChange,
  onBrowseModel,
  onAudition,
  onCompareAudition,
  renderIssue,
  renderIssueDetail,
}: Props) {
  const [tab, setTab] = useState<Tab>("config");
  const [schema, setSchema] = useState<NodeSchema | null>(null);
  const [provenance, setProvenance] = useState<Record<string, unknown> | null>(null);
  const [fileMeta, setFileMeta] = useState<Record<string, unknown> | null>(null);
  const [fileMetaError, setFileMetaError] = useState<string | null>(null);
  const [compareWaveforms, setCompareWaveforms] = useState<[number[], number[]]>([[], []]);
  const [modelCard, setModelCard] = useState<ModelCard | null>(null);

  const selectedModelId = useMemo(() => {
    if (!node) return null;
    const direct = node.widgets.model;
    if (typeof direct === "string" && direct.trim()) return direct.trim();
    for (const widget of schema?.widgets ?? []) {
      if (widget.type !== "MODEL_REF") continue;
      const value = node.widgets[widget.name];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return null;
  }, [node, schema?.widgets]);

  useEffect(() => {
    setTab("config");
  }, [node?.id]);

  useEffect(() => {
    if (!node) {
      setSchema(null);
      return;
    }
    fetchNodeSchema(node.type)
      .then(setSchema)
      .catch(() => setSchema(null));
  }, [node?.id, node?.type]);

  useEffect(() => {
    const primary = jobOutputAtSlot(output, 0);
    if (!primary?.cache_id) {
      setProvenance(null);
      return;
    }
    fetch(`${import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188"}/api/cache/${primary.cache_id}/provenance`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setProvenance)
      .catch(() => setProvenance(null));
  }, [output]);

  useEffect(() => {
    if (!node || node.type !== "LoadAudio") {
      setFileMeta(null);
      setFileMetaError(null);
      return;
    }
    const path = typeof node.widgets.path === "string" ? node.widgets.path.trim() : "";
    if (!path) {
      setFileMeta(null);
      setFileMetaError("No audio path set — choose a file under assets/samples/ or upload audio.");
      return;
    }
    fetchAudioFileMeta(path)
      .then(({ meta, error }) => {
        setFileMeta(meta);
        setFileMetaError(error);
      })
      .catch(() => {
        setFileMeta(null);
        setFileMetaError(`Could not read metadata for ${path}`);
      });
  }, [node?.id, node?.type, node?.widgets.path]);

  useEffect(() => {
    if (!selectedModelId) {
      setModelCard(null);
      return;
    }
    fetchModelCard(selectedModelId)
      .then(setModelCard)
      .catch(() => setModelCard(null));
  }, [selectedModelId]);

  useEffect(() => {
    if (!comparePair) {
      setCompareWaveforms([[], []]);
      return;
    }
    const [a, b] = comparePair;
    let cancelled = false;
    Promise.all([fetchWaveform(a.output.cache_id!), fetchWaveform(b.output.cache_id!)])
      .then(([dataA, dataB]) => {
        if (!cancelled) setCompareWaveforms([dataA.peaks, dataB.peaks]);
      })
      .catch(() => {
        if (!cancelled) setCompareWaveforms([[], []]);
      });
    return () => {
      cancelled = true;
    };
  }, [comparePair?.[0]?.output.cache_id, comparePair?.[1]?.output.cache_id]);

  const inputRows = useMemo(
    () => (schema && node ? wiredInputsForNode(workflow, node.id, schema.inputs) : []),
    [schema, node, workflow],
  );

  const modelParamRows = useMemo(() => {
    if (!selectedModelId || !schema) return [];
    const params = modelCard?.inference_params?.length
      ? modelCard.inference_params
      : inferenceParamsForModel(selectedModelId);
    const widgetNames = new Set(schema.widgets.map((widget) => widget.name));
    return params.filter((param) => !widgetNames.has(param.name));
  }, [modelCard, schema, selectedModelId]);

  if (showCompare) {
    return (
      <aside className="node-helper node-helper--compare-only">
        <div className="node-helper__scroll">
          <ComparePanel
            comparePair={comparePair}
            compareNote={compareNote}
            compareMissingRender={compareMissingRender}
            chainHops={chainHops}
            waveforms={compareWaveforms}
            onCompareAudition={onCompareAudition}
            onSelectCompareHop={onSelectCompareHop}
          />
        </div>
      </aside>
    );
  }

  if (selectedNodes.length > 2) {
    return (
      <aside className="node-helper node-helper--selection-only">
        <div className="node-helper__scroll">
          <MultiSelectSummary nodes={selectedNodes} workflow={workflow} outputs={selectionOutputs} />
        </div>
      </aside>
    );
  }

  if (!node) {
    return (
      <aside className="node-helper node-helper--compare-only">
        <div className="node-helper__scroll">
          <p className="node-helper__empty-hint">Select a node to edit parameters.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="node-helper">
      <header className="node-helper__header">
        <h2>{node.type}</h2>
        <span className="node-helper__id">{node.id}</span>
      </header>
      {renderIssue ? (
        <div className="node-helper__render-error" role="alert">
          <strong>Render failed</strong>
          <p>{renderIssue}</p>
          {renderIssueDetail && renderIssueDetail !== renderIssue ? (
            <details className="node-helper__render-error-details">
              <summary>Full error</summary>
              <pre>{renderIssueDetail}</pre>
            </details>
          ) : null}
        </div>
      ) : null}
      <div className="node-helper__scroll">
        {schema?.description ? <p className="node-helper__desc">{schema.description}</p> : null}
        {hasMinimalPatch(node.type) ? (
          <p className="node-helper__hint">Press <kbd>Tab</kbd> to wire missing example inputs and outputs for this node.</p>
        ) : null}
        <nav className="node-helper__tabs">
        <button type="button" className={tab === "config" ? "active" : ""} onClick={() => setTab("config")}>
          Config
        </button>
        <button type="button" className={tab === "inputs" ? "active" : ""} onClick={() => setTab("inputs")} disabled={!schema}>
          Inputs
        </button>
        <button
          type="button"
          className={tab === "outputs" ? "active" : ""}
          onClick={() => setTab("outputs")}
          disabled={!schema}
        >
          Outputs
        </button>
        <button
          type="button"
          className={tab === "provenance" ? "active" : ""}
          onClick={() => setTab("provenance")}
          disabled={!jobOutputAtSlot(output, 0)?.cache_id && !output?.cache_id}
        >
          Provenance
        </button>
      </nav>
      <div className="node-helper__body">
        {tab === "config" && schema ? (
          <div className="node-helper__widgets">
            {modelCard || selectedModelId ? (
              <section className="node-helper__model-panel">
                <h4 className="node-helper__compare-subtitle">Selected model</h4>
                <p className="node-helper__model-name">{modelCard?.name ?? selectedModelId}</p>
                {modelCard?.description ? <p className="node-helper__hint">{modelCard.description}</p> : null}
                {modelCard ? (
                  <>
                    <div className="node-helper__model-tags">
                      {modelCard.task_types.map((task) => (
                        <span key={task} className="node-helper__model-tag">
                          {task}
                        </span>
                      ))}
                    </div>
                    <p className="node-helper__hint">
                      Install: {modelCard.install_status}
                      {modelCard.license?.spdx ? ` · ${modelCard.license.spdx}` : ""}
                    </p>
                  </>
                ) : null}
              </section>
            ) : null}
            {schema.inputs.length > 0 ? (
              <section className="node-helper__socket-summary">
                <h4 className="node-helper__compare-subtitle">Input sockets</h4>
                <ul className="node-helper__socket-list">
                  {inputRows.map((row) => (
                    <li key={row.name} className="node-helper__socket-row">
                      <SocketTypeBadge type={row.type} />
                      <span className="node-helper__socket-name">{row.name}</span>
                      {row.optional ? <span className="node-helper__socket-opt">optional</span> : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {schema.outputs.length > 0 ? (
              <section className="node-helper__socket-summary">
                <h4 className="node-helper__compare-subtitle">Output sockets</h4>
                <ul className="node-helper__socket-list">
                  {schema.outputs.map((socket) => (
                    <li key={socket.name} className="node-helper__socket-row">
                      <SocketTypeBadge type={socket.type} />
                      <span className="node-helper__socket-name">{socket.name}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {schema.widgets.map((widget) => {
              const supersededBy = wiredInputSupersedesWidget(node.type, widget.name, inputRows);
              const wiredPreview = supersededBy ? wiredPromptPreview(supersededBy.sourceNode) : null;
              return (
              <label
                key={widget.name}
                className={[
                  "node-helper__field",
                  supersededBy ? "node-helper__field--superseded" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span>{widgetLabel(widget.name, node.type)}</span>
                {widget.description ? <small className="node-helper__hint">{widget.description}</small> : null}
                {supersededBy ? (
                  <small className="node-helper__hint node-helper__hint--wired">
                    Wired from {supersededBy.sourceNode?.type ?? "upstream"}
                    {supersededBy.sourceNode?.id ? (
                      <>
                        {" "}
                        <span className="node-helper__mono">({supersededBy.sourceNode.id})</span>
                      </>
                    ) : null}
                    — edit on the source node.
                  </small>
                ) : null}
                {wiredPreview ? (
                  <p className="node-helper__wired-preview" title="Resolved prompt at render">
                    {wiredPreview}
                  </p>
                ) : null}
                <WidgetInput
                  spec={widget}
                  value={node.widgets[widget.name] ?? widget.default ?? ""}
                  onChange={(value) => onWidgetChange(node.id, widget.name, value)}
                  disabled={Boolean(supersededBy)}
                  nodeType={node.type}
                  nodeWidgets={node.widgets}
                  onMultiWidgetChange={(name, value) => onWidgetChange(node.id, name, value)}
                  onBrowse={
                    widget.type === "MODEL_REF"
                      ? () => onBrowseModel?.(node.id, widget.name)
                      : undefined
                  }
                />
              </label>
            );
            })}
            {modelParamRows.length > 0 ? (
              <section className="node-helper__model-params">
                <h4 className="node-helper__compare-subtitle">Model parameters</h4>
                {modelParamRows.map((param) => (
                  <label key={param.name} className="node-helper__field">
                    <span>{widgetLabel(param.name, node.type)}</span>
                    {param.description ? <small className="node-helper__hint">{param.description}</small> : null}
                    <WidgetInput
                      spec={param}
                      value={node.widgets[param.name] ?? param.default ?? ""}
                      onChange={(value) => onWidgetChange(node.id, param.name, value)}
                    />
                  </label>
                ))}
              </section>
            ) : null}
            {node.type === "SaveAudio" ? (
              <p className="node-helper__hint">
                Output path: <code>{joinSaveAudioPath(node.widgets.path, node.widgets.filename)}</code> (relative to
                project folder). Use Choose file… on the file name field to pick a name and folder.
              </p>
            ) : null}
            {node.type === "LoadAudio" ? (
              <p className="node-helper__hint">
                Choose a file to upload into the project, or enter a project-relative path (e.g.{" "}
                <code>assets/samples/male-1.wav</code>). You can also drop audio onto the canvas.
              </p>
            ) : null}
            {schema.widgets.length === 0 && modelParamRows.length === 0 && node.type !== "SaveAudio" ? (
              <p className="node-helper__hint">No configurable parameters.</p>
            ) : null}
            {output?.text ? (
              <div className="node-helper__transcript-panel">
                <p className="node-helper__socket-wire">
                  <SocketTypeBadge type="TEXT" /> transcript
                </p>
                <p className="node-helper__text">{output.text}</p>
              </div>
            ) : null}
            {node.type === "LoadAudio" ? (
              <AudioFormatPanel meta={fileMeta} title="Source file format" />
            ) : null}
            {node.type === "LoadAudio" && fileMetaError ? (
              <pre className="node-helper__render-error-inline node-helper__path-error">{fileMetaError}</pre>
            ) : null}
          </div>
        ) : null}
        {tab === "inputs" && schema ? (
          <ul className="node-helper__socket-detail-list">
            {inputRows.length === 0 ? (
              <li className="node-helper__hint">This node has no wired input sockets.</li>
            ) : (
              inputRows.map((row) => (
                <li key={row.name} className="node-helper__socket-detail">
                  <div className="node-helper__socket-detail-head">
                    <SocketTypeBadge type={row.type} />
                    <strong className="node-helper__socket-name">{row.name}</strong>
                    {row.optional ? <span className="node-helper__socket-opt">optional</span> : null}
                  </div>
                  {row.description ? <p className="node-helper__hint">{row.description}</p> : null}
                  {row.connected && row.sourceNode ? (
                    <p className="node-helper__socket-wire">
                      ← {row.sourceNode.type}
                      <span className="node-helper__mono"> ({row.sourceNode.id})</span>
                    </p>
                  ) : (
                    <p className="node-helper__socket-wire node-helper__socket-wire--open">unconnected</p>
                  )}
                </li>
              ))
            )}
          </ul>
        ) : null}
        {tab === "outputs" && schema ? (
          <div className="node-helper__outputs">
            <ul className="node-helper__socket-detail-list">
              {schema.outputs.map((socket, index) => {
                const slotOutput = jobOutputAtSlot(output, index);
                return (
                <li key={socket.name} className="node-helper__socket-detail">
                  <div className="node-helper__socket-detail-head">
                    <SocketTypeBadge type={socket.type} />
                    <strong className="node-helper__socket-name">{socket.name}</strong>
                  </div>
                  {socket.description ? <p className="node-helper__hint">{socket.description}</p> : null}
                  {slotOutput ? (
                    <OutputSnapshot
                      output={slotOutput}
                      socketType={socket.type}
                    />
                  ) : (
                    <p className="node-helper__hint">Render to populate this output.</p>
                  )}
                </li>
              )})}
            </ul>
            {previewUrl ? (
              <button type="button" className="node-helper__audition" onClick={onAudition}>
                ▶ Audition node
              </button>
            ) : null}
          </div>
        ) : null}
        {tab === "provenance" && provenance ? (
          <div className="node-helper__provenance">
            <p>
              <span className={`pill pill--${String((provenance.contribution as { class?: string })?.class ?? "unknown")}`}>
                {String((provenance.contribution as { class?: string })?.class ?? "unknown")}
              </span>
            </p>
            <p>{String((provenance.contribution as { disclosure_label?: string })?.disclosure_label ?? "")}</p>
            <ul className="node-helper__list">
              {((provenance.parents as Array<{ node_type?: string; cache_id?: string }>) ?? []).map((parent) => (
                <li key={parent.cache_id}>
                  ↑ {parent.node_type ?? "parent"} ({parent.cache_id?.slice(0, 8)}…)
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {tab === "provenance" && !provenance ? (
          <p className="node-helper__hint">Render to populate provenance.</p>
        ) : null}
      </div>
      </div>
    </aside>
  );
}

function MultiSelectSummary({
  nodes,
  workflow,
  outputs,
}: {
  nodes: WorkflowNode[];
  workflow: Workflow;
  outputs?: Record<string, JobOutput> | null;
}) {
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of nodes) {
      counts.set(node.type, (counts.get(node.type) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [nodes]);

  const selectedIds = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);

  const internalLinks = useMemo(
    () =>
      workflow.links.filter(
        (link) => selectedIds.has(String(link.from[0])) && selectedIds.has(String(link.to[0])),
      ).length,
    [workflow.links, selectedIds],
  );

  const externalLinks = useMemo(
    () =>
      workflow.links.filter((link) => {
        const src = selectedIds.has(String(link.from[0]));
        const dst = selectedIds.has(String(link.to[0]));
        return src !== dst;
      }).length,
    [workflow.links, selectedIds],
  );

  const renderedCount = useMemo(() => {
    if (!outputs) return 0;
    return nodes.filter((node) => {
      const out = outputs[node.id];
      return Boolean(out?.cache_id || out?.midi_id || out?.text || out?.stems);
    }).length;
  }, [nodes, outputs]);

  const groupCount = useMemo(() => {
    const groupIds = new Set<string>();
    for (const group of workflow.groups) {
      if (group.node_ids.some((id) => selectedIds.has(id))) groupIds.add(group.id);
    }
    return groupIds.size;
  }, [workflow.groups, selectedIds]);

  return (
    <section className="node-helper__selection">
      <header className="node-helper__compare-header">
        <h3 className="node-helper__compare-title">Selection</h3>
        <span className="node-helper__selection-count">{nodes.length} nodes</span>
      </header>

      <dl className="node-helper__compare-meta">
        <div className="node-helper__compare-meta-row">
          <dt>Selected</dt>
          <dd>{nodes.length}</dd>
        </div>
        <div className="node-helper__compare-meta-row">
          <dt>Types</dt>
          <dd>{typeCounts.length}</dd>
        </div>
        <div className="node-helper__compare-meta-row">
          <dt>Rendered</dt>
          <dd>
            {renderedCount}/{nodes.length}
          </dd>
        </div>
        <div className="node-helper__compare-meta-row">
          <dt>Links</dt>
          <dd>
            {internalLinks} internal · {externalLinks} boundary
          </dd>
        </div>
        {groupCount > 0 ? (
          <div className="node-helper__compare-meta-row">
            <dt>Groups</dt>
            <dd>{groupCount}</dd>
          </div>
        ) : null}
      </dl>

      <div className="node-helper__compare-section">
        <h4 className="node-helper__compare-section-title">By type</h4>
        <ul className="node-helper__selection-types">
          {typeCounts.map(([type, count]) => (
            <li key={type}>
              <span className="node-helper__selection-type">{type}</span>
              <span className="node-helper__selection-type-count">×{count}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="node-helper__compare-section">
        <h4 className="node-helper__compare-section-title">Nodes</h4>
        <ul className="node-helper__selection-nodes">
          {nodes.map((node) => {
            const out = outputs?.[node.id];
            const hasRender = Boolean(out?.cache_id || out?.midi_id || out?.text || out?.stems);
            return (
              <li key={node.id}>
                <span className="node-helper__selection-id">{node.id}</span>
                <span className="node-helper__selection-node-type">{node.type}</span>
                <span
                  className={`node-helper__selection-status${hasRender ? " node-helper__selection-status--ready" : ""}`}
                >
                  {hasRender ? "rendered" : "—"}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <p className="node-helper__hint">Select one node to edit, or exactly two for A/B compare.</p>
    </section>
  );
}

function ComparePanel({
  comparePair,
  compareNote,
  compareMissingRender = false,
  chainHops = [],
  waveforms,
  onCompareAudition,
  onSelectCompareHop,
}: {
  comparePair?: CompareEntry[] | null;
  compareNote?: string | null;
  compareMissingRender?: boolean;
  chainHops?: CompareHop[];
  waveforms: [number[], number[]];
  onCompareAudition?: (nodeId: string) => void;
  onSelectCompareHop?: (nodeIdA: string, nodeIdB: string) => void;
}) {
  const a = comparePair?.[0];
  const b = comparePair?.[1];
  const [models, setModels] = useState<ModelCard[]>([]);
  const [modelId, setModelId] = useState("groovy-signal-diff");
  const [question, setQuestion] = useState("What are the differences between A and B?");
  const [askOpen, setAskOpen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AbCompareResult | null>(null);
  const [resultTab, setResultTab] = useState<"summary" | "metrics">("summary");

  const labelA = a ? `${a.node.type} · ${a.node.id}` : "A";
  const labelB = b ? `${b.node.type} · ${b.node.id}` : "B";
  const legendA = a ? a.node.type : "A";
  const legendB = b ? b.node.type : "B";

  useEffect(() => {
    fetchCompareModels()
      .then((list) => {
        setModels(list);
        if (list.some((model) => model.id === "groovy-signal-diff")) {
          setModelId("groovy-signal-diff");
        } else if (list[0]) {
          setModelId(list[0].id);
        }
      })
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    setResult(null);
    setError(null);
    setResultTab("summary");
  }, [a?.output.cache_id, b?.output.cache_id, modelId]);

  const runAnalysis = useCallback(async () => {
    if (!a?.output.cache_id || !b?.output.cache_id) return;
    setAnalyzing(true);
    setError(null);
    try {
      await Promise.all([fetchCacheMeta(a.output.cache_id), fetchCacheMeta(b.output.cache_id)]);
      const analysis = await analyzeAbCompare({
        cache_id_a: a.output.cache_id,
        cache_id_b: b.output.cache_id,
        model_id: modelId,
        label_a: labelA,
        label_b: labelB,
        question: question.trim() || undefined,
      });
      setResult(analysis);
      setResultTab("summary");
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }, [a, b, labelA, labelB, modelId, question]);

  if (!a || !b) {
    return (
      <section className="node-helper__compare">
        <header className="node-helper__compare-header">
          <h3 className="node-helper__compare-title">A/B compare</h3>
        </header>
        {compareMissingRender ? (
          <p className="node-helper__compare-warning">{compareNote}</p>
        ) : compareNote ? (
          <p className="node-helper__compare-warning">{compareNote}</p>
        ) : (
          <p className="node-helper__hint">Select two rendered nodes to compare.</p>
        )}
        {chainHops.length > 0 ? (
          <div className="node-helper__compare-hops">
            <span className="node-helper__compare-subtitle">Chain hops</span>
            {chainHops.map((hop) => (
              <button
                key={`${hop.a}-${hop.b}`}
                type="button"
                className="node-helper__compare-hop"
                onClick={() => onSelectCompareHop?.(hop.a, hop.b)}
              >
                {hop.label}
              </button>
            ))}
          </div>
        ) : null}
      </section>
    );
  }

  const [peaksA, peaksB] = waveforms;
  const selectedModel = models.find((model) => model.id === modelId);
  const sameCache = a.output.cache_id === b.output.cache_id;
  const notice = compareNote || (sameCache ? `Same cache ${a.output.cache_id?.slice(0, 8)}…` : null);

  return (
    <section className="node-helper__compare">
      <header className="node-helper__compare-header">
        <h3 className="node-helper__compare-title">A/B compare</h3>
        <div className="node-helper__compare-actions">
          <button type="button" className="node-helper__audition" onClick={() => onCompareAudition?.(a.node.id)}>
            ▶ A
          </button>
          <button type="button" className="node-helper__audition" onClick={() => onCompareAudition?.(b.node.id)}>
            ▶ B
          </button>
        </div>
      </header>

      {notice ? <p className="node-helper__compare-info">{notice}</p> : null}

      <div className="node-helper__compare-signal">
        <WaveformCompare
          peaksA={peaksA}
          peaksB={peaksB}
          labelA={legendA}
          labelB={legendB}
          titleA={labelA}
          titleB={labelB}
        />
      </div>

      {chainHops.length > 1 ? (
        <div className="node-helper__compare-hops">
          <span className="node-helper__compare-subtitle">Hops</span>
          {chainHops
            .filter((hop) => !(hop.a === a.node.id && hop.b === b.node.id))
            .map((hop) => (
              <button
                key={`${hop.a}-${hop.b}`}
                type="button"
                className="node-helper__compare-hop"
                onClick={() => onSelectCompareHop?.(hop.a, hop.b)}
              >
                {hop.label}
              </button>
            ))}
        </div>
      ) : null}

      <div className="node-helper__compare-ask">
        <div className="node-helper__compare-ask-row">
          <label className="node-helper__field node-helper__field--inline">
            <span>Model</span>
            <select value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={analyzing}>
              {models.length === 0 ? <option value={modelId}>{modelId}</option> : null}
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="node-helper__compare-analyze"
            onClick={() => void runAnalysis()}
            disabled={analyzing || !a.output.cache_id || !b.output.cache_id}
          >
            {analyzing ? "…" : "Analyze"}
          </button>
        </div>
        <button
          type="button"
          className="node-helper__compare-ask-toggle"
          onClick={() => setAskOpen((open) => !open)}
          aria-expanded={askOpen}
        >
          {askOpen ? "Hide question" : "Ask a question"}
        </button>
        {askOpen ? (
          <label className="node-helper__field">
            <span>Question</span>
            <textarea
              rows={2}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What are the differences between A and B?"
              disabled={analyzing}
            />
          </label>
        ) : null}
        {selectedModel?.description && askOpen ? (
          <p className="node-helper__hint">{selectedModel.description}</p>
        ) : null}
        {error ? <p className="node-helper__compare-error">{error}</p> : null}
      </div>

      {result ? (
        <div className="node-helper__compare-result">
          <div className="node-helper__compare-tabs" role="tablist" aria-label="Compare result">
            <button
              type="button"
              role="tab"
              aria-selected={resultTab === "summary"}
              className={`node-helper__compare-tab${resultTab === "summary" ? " node-helper__compare-tab--active" : ""}`}
              onClick={() => setResultTab("summary")}
            >
              Summary
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={resultTab === "metrics"}
              className={`node-helper__compare-tab${resultTab === "metrics" ? " node-helper__compare-tab--active" : ""}`}
              onClick={() => setResultTab("metrics")}
            >
              Metrics
            </button>
          </div>

          {resultTab === "summary" ? (
            <div className="node-helper__compare-summary" role="tabpanel">
              <p className={`node-helper__compare-verdict node-helper__compare-verdict--${result.verdict}`}>
                <span className="node-helper__compare-verdict-tag">{result.verdict.replaceAll("_", " ")}</span>
                {result.verdict_summary}
              </p>

              <dl className="node-helper__compare-meta">
                <div className="node-helper__compare-meta-row">
                  <dt>Model</dt>
                  <dd>{models.find((model) => model.id === result.model_id)?.name ?? result.model_id}</dd>
                </div>
                <div className="node-helper__compare-meta-row">
                  <dt>Clips</dt>
                  <dd>
                    {legendA} (A) vs {legendB} (B)
                  </dd>
                </div>
              </dl>

              {result.differences.length > 0 ? (
                <div className="node-helper__compare-section">
                  <h4 className="node-helper__compare-section-title">Detected differences</h4>
                  <ul className="node-helper__list node-helper__compare-diff-list">
                    {result.differences.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {measurementFacts(result.facts).length > 0 ? (
                <div className="node-helper__compare-section">
                  <h4 className="node-helper__compare-section-title">Measurements</h4>
                  <dl className="node-helper__compare-fact-grid">
                    {measurementFacts(result.facts).map((fact) => {
                      const { label, value } = splitFact(fact);
                      return (
                        <div key={fact} className="node-helper__compare-fact-row">
                          <dt>{label}</dt>
                          <dd>{value}</dd>
                        </div>
                      );
                    })}
                  </dl>
                </div>
              ) : null}

              {result.mode === "transcript" ? (
                <div className="node-helper__compare-transcripts">
                  <h4 className="node-helper__compare-section-title">Transcripts</h4>
                  <p className="node-helper__compare-transcript">
                    <strong>A</strong> {result.transcript_a}
                  </p>
                  <p className="node-helper__compare-transcript">
                    <strong>B</strong> {result.transcript_b}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="node-helper__compare-metrics-panel" role="tabpanel">
              <CompareMetricsViz
                clipA={result.clip_a}
                clipB={result.clip_b}
                comparison={result.comparison}
                labelA={legendA}
                labelB={legendB}
              />
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

function formatPeakDb(peak: number): string {
  if (peak <= 0) return "−∞ dBFS";
  return `${(20 * Math.log10(peak)).toFixed(1)} dBFS`;
}

function OutputSnapshot({
  output,
  socketType,
}: {
  output: JobOutput;
  socketType: string;
}) {
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [signalMetrics, setSignalMetrics] = useState<CacheSignalMetrics | null>(null);
  const [waveform, setWaveform] = useState<number[]>([]);

  useEffect(() => {
    if (!output.cache_id) {
      setMeta(null);
      setSignalMetrics(null);
      setWaveform([]);
      return;
    }
    fetchCacheMeta(output.cache_id)
      .then(setMeta)
      .catch(() => setMeta(null));
    fetchCacheMetrics(output.cache_id)
      .then(setSignalMetrics)
      .catch(() => setSignalMetrics(null));
    fetchWaveform(output.cache_id)
      .then((data) => setWaveform(data.peaks))
      .catch(() => setWaveform([]));
  }, [output.cache_id]);
  if (output.type !== socketType && socketType !== "AUDIO") {
    if (socketType === "STRING" && (output.type === "STRING" || output.type === "TEXT")) {
      // SaveAudio path output (STRING) or legacy TEXT path payloads
    } else if (socketType === "MIDI" && output.type === "MIDI") {
      // AudioToMIDI and other MIDI outputs
    } else if (socketType === "TEXT" && output.type === "TEXT") {
      // Prompt node text output
    } else {
      return <p className="node-helper__hint">No render for this socket yet.</p>;
    }
  }

  return (
    <div className="node-helper__output-snapshot">
      <p className="node-helper__socket-wire">
        <SocketTypeBadge type={socketType} /> {output.type === "STRING" ? "written" : "cached"}
      </p>
      {output.type === "STRING" && output.path ? (
        <p className="node-helper__text">
          <code>{output.path}</code>
        </p>
      ) : null}
      {output.type === "MIDI" && output.midi_id ? (
        <p className="node-helper__text">
          MIDI cache <code>{output.midi_id.slice(0, 8)}…</code>
        </p>
      ) : null}
      {output.type === "TEXT" && output.text ? <p className="node-helper__text">{output.text}</p> : null}
      {output.type === "AUDIO" && output.text ? (
        <p className="node-helper__text node-helper__text--transcript">{output.text}</p>
      ) : null}
      {output.type === "STEMS" && output.stems ? (
        <ul className="node-helper__list">
          {Object.keys(output.stems).map((stem) => (
            <li key={stem}>{stem}</li>
          ))}
        </ul>
      ) : null}
      {meta && output.type === "AUDIO" ? (
        <>
          {waveform.length > 0 ? <WaveformMini peaks={waveform} /> : null}
          <AudioFormatPanel meta={meta} title="Output format" />
          {signalMetrics ? (
            <dl className="node-helper__meta-grid">
              <div className="node-helper__meta-row">
                <dt>Peak</dt>
                <dd>{formatPeakDb(signalMetrics.peak)}</dd>
              </div>
              <div className="node-helper__meta-row">
                <dt>LUFS</dt>
                <dd>{signalMetrics.lufs != null ? `${signalMetrics.lufs.toFixed(1)} LUFS` : "—"}</dd>
              </div>
              <div className="node-helper__meta-row">
                <dt>Sample rate</dt>
                <dd>{signalMetrics.sample_rate} Hz</dd>
              </div>
              <div className="node-helper__meta-row">
                <dt>Layout</dt>
                <dd>{signalMetrics.channel_layout}</dd>
              </div>
            </dl>
          ) : null}
          <p className="node-helper__hint">
            {String(meta.frame_count)} frames @ {String(meta.sample_rate)} Hz
          </p>
          {output.cache_id ? <p className="node-helper__mono">{output.cache_id}</p> : null}
        </>
      ) : null}
      {!meta && output.type === "AUDIO" ? (
        <p className="node-helper__hint">Render to populate output metadata.</p>
      ) : null}
    </div>
  );
}

function measurementFacts(facts: string[]): string[] {
  return facts.filter((fact) => {
    const trimmed = fact.trim();
    if (!trimmed) return false;
    if (trimmed === "Detected differences:") return false;
    if (trimmed.startsWith("•") || trimmed.startsWith("- ")) return false;
    // Keep "Label: value" measurement / transcript rows.
    return /^[A-Za-z][^:]{0,40}:\s/.test(trimmed);
  });
}

function splitFact(fact: string): { label: string; value: string } {
  const idx = fact.indexOf(":");
  if (idx <= 0) return { label: "Note", value: fact };
  return {
    label: fact.slice(0, idx).trim(),
    value: fact.slice(idx + 1).trim(),
  };
}

function widgetLabel(name: string, nodeType: string): string {
  if (nodeType === "SaveAudio") {
    if (name === "path") return "Output folder";
    if (name === "filename") return "File name";
    if (name === "format") return "Format";
    if (name === "bit_depth") return "Bit depth";
  }
  if (nodeType === "Resample") {
    if (name === "target_sample_rate") return "Target sample rate (Hz)";
    if (name === "quality") return "Quality";
  }
  return name;
}

type WidgetInputProps = {
  spec: {
    name: string;
    type: string;
    default?: unknown;
    description?: string;
    min?: number;
    max?: number;
    step?: number;
  };
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  onBrowse?: () => void;
  nodeType?: string;
  nodeWidgets?: Record<string, unknown>;
  onMultiWidgetChange?: (name: string, value: unknown) => void;
};

function splitProjectRelativePath(fullPath: string): { folder: string; filename: string } {
  const normalized = fullPath.trim().replace(/^\/+/, "").replace(/\\/g, "/");
  if (!normalized) return { folder: "", filename: "" };
  const slash = normalized.lastIndexOf("/");
  if (slash < 0) return { folder: "", filename: normalized };
  return { folder: normalized.slice(0, slash), filename: normalized.slice(slash + 1) };
}

/** File System Access API types — not in default DOM lib used by CI `tsc`. */
type FilePickerAcceptType = {
  description?: string;
  accept: Record<string, string[]>;
};

type SaveFilePickerOptions = {
  suggestedName?: string;
  types?: FilePickerAcceptType[];
};

function savePickerTypes(format: unknown): FilePickerAcceptType[] {
  const fmt = typeof format === "string" ? format.toLowerCase() : "wav";
  if (fmt === "flac") {
    return [{ description: "FLAC audio", accept: { "audio/flac": [".flac"] } }];
  }
  return [{ description: "WAV audio", accept: { "audio/wav": [".wav"] } }];
}

function LoadAudioPathInput({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const textValue = typeof value === "string" ? value : String(value ?? "");

  const handleFile = async (file: File | null | undefined) => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const path = await uploadProjectAudio(file);
      onChange(path);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="node-helper__file-picker">
      <input
        type="text"
        value={textValue}
        placeholder="assets/uploads/recording.wav"
        onChange={(e) => onChange(e.target.value)}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*,.wav,.flac,.aiff,.aif,.mp3,.ogg,.opus"
        className="node-helper__file-input-hidden"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />
      <button type="button" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
        {uploading ? "Uploading…" : "Choose file…"}
      </button>
      {uploadError ? <p className="node-helper__path-error">{uploadError}</p> : null}
    </div>
  );
}

function SaveAudioFilenameInput({
  value,
  onChange,
  nodeWidgets,
  onMultiWidgetChange,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  nodeWidgets?: Record<string, unknown>;
  onMultiWidgetChange?: (name: string, value: unknown) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textValue = typeof value === "string" ? value : String(value ?? "");
  const format = nodeWidgets?.format;

  const applyPickedName = (picked: string) => {
    const { folder, filename } = splitProjectRelativePath(picked);
    if (filename) onChange(filename);
    if (folder && onMultiWidgetChange) onMultiWidgetChange("path", folder);
  };

  const openSavePicker = async () => {
    const suggested =
      textValue.trim() ||
      (typeof format === "string" && format.toLowerCase() === "flac" ? "output.flac" : "output.wav");
    if ("showSaveFilePicker" in window) {
      try {
        const handle = await (
          window as Window & {
            showSaveFilePicker: (options?: SaveFilePickerOptions) => Promise<FileSystemFileHandle>;
          }
        ).showSaveFilePicker({
          suggestedName: suggested,
          types: savePickerTypes(format),
        });
        applyPickedName(handle.name);
        return;
      } catch {
        return;
      }
    }
    fileInputRef.current?.click();
  };

  return (
    <div className="node-helper__file-picker">
      <input
        type="text"
        value={textValue}
        placeholder="output.wav"
        onChange={(e) => onChange(e.target.value)}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*,.wav,.flac,.aiff,.aif,.mp3,.ogg,.opus"
        className="node-helper__file-input-hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) applyPickedName(file.name);
          if (fileInputRef.current) fileInputRef.current.value = "";
        }}
      />
      <button type="button" onClick={() => void openSavePicker()}>
        Choose file…
      </button>
    </div>
  );
}

function WidgetInput({
  spec,
  value,
  onChange,
  disabled = false,
  onBrowse,
  nodeType,
  nodeWidgets,
  onMultiWidgetChange,
}: WidgetInputProps) {
  if (nodeType === "LoadAudio" && spec.name === "path") {
    return <LoadAudioPathInput value={value} onChange={onChange} />;
  }
  if (nodeType === "SaveAudio" && spec.name === "filename") {
    return (
      <SaveAudioFilenameInput
        value={value}
        onChange={onChange}
        nodeWidgets={nodeWidgets}
        onMultiWidgetChange={onMultiWidgetChange}
      />
    );
  }
  if (spec.type === "MODEL_REF") {
    return (
      <div className="node-helper__model-ref">
        <input type="text" readOnly value={typeof value === "string" ? value : String(value ?? "")} />
        <button type="button" onClick={onBrowse}>
          Browse…
        </button>
      </div>
    );
  }

  const control = resolveWidgetControl(spec);

  if (control.kind === "switch") {
    return (
      <ParamSwitch
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(next) => onChange(next)}
      />
    );
  }

  if (control.kind === "stepped" && control.options?.length) {
    const str =
      typeof value === "string" || typeof value === "number" ? String(value) : String(value ?? control.options[0]);
    return (
      <ParamStepped
        value={str}
        options={control.options}
        disabled={disabled}
        onChange={(next) => {
          if (spec.type === "INT") {
            const parsed = parseInt(next, 10);
            if (Number.isFinite(parsed)) onChange(parsed);
            return;
          }
          onChange(next);
        }}
      />
    );
  }

  if (control.kind === "pot" || control.kind === "fader") {
    const isInt = spec.type === "INT";
    const numeric =
      typeof value === "number"
        ? value
        : Number(value ?? spec.default ?? control.min);
    const safe = Number.isFinite(numeric) ? numeric : control.min;
    const Control = control.kind === "fader" ? ParamFader : ParamPot;
    return (
      <Control
        value={safe}
        min={control.min}
        max={control.max}
        step={control.step}
        isInt={isInt}
        disabled={disabled}
        onChange={(next) => onChange(isInt ? Math.round(next) : next)}
      />
    );
  }

  return (
    <input
      type="text"
      value={typeof value === "string" ? value : String(value ?? "")}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
