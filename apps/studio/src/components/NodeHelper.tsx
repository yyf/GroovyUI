import { useCallback, useEffect, useMemo, useState } from "react";
import {
  analyzeAbCompare,
  fetchAudioFileMeta,
  fetchCacheMeta,
  fetchCacheMetrics,
  fetchCompareModels,
  fetchModelCard,
  fetchNodeSchema,
  fetchWaveform,
  type AbCompareResult,
  type CacheSignalMetrics,
} from "../api";
import type { JobOutput, ModelCard, NodeSchema, Workflow, WorkflowNode } from "../types";
import type { CompareHop } from "../workflow";
import { joinSaveAudioPath, wiredInputsForNode } from "../workflow";
import { hasMinimalPatch } from "../nodeMinimalPatches";
import AudioFormatPanel from "./AudioFormatPanel";
import SocketTypeBadge from "./SocketTypeBadge";
import WaveformCompare from "./WaveformCompare";
import WaveformMini from "./WaveformMini";

type Tab = "config" | "inputs" | "outputs" | "provenance";

type CompareEntry = {
  node: WorkflowNode;
  output: JobOutput;
};

type Props = {
  node: WorkflowNode | null;
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
};

export default function NodeHelper({
  node,
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
}: Props) {
  const [tab, setTab] = useState<Tab>("config");
  const [schema, setSchema] = useState<NodeSchema | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [signalMetrics, setSignalMetrics] = useState<CacheSignalMetrics | null>(null);
  const [provenance, setProvenance] = useState<Record<string, unknown> | null>(null);
  const [waveform, setWaveform] = useState<number[]>([]);
  const [fileMeta, setFileMeta] = useState<Record<string, unknown> | null>(null);
  const [compareWaveforms, setCompareWaveforms] = useState<[number[], number[]]>([[], []]);
  const [modelCard, setModelCard] = useState<ModelCard | null>(null);

  const selectedModelId = useMemo(() => {
    if (!node) return null;
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
    if (!output?.cache_id) {
      setMeta(null);
      setSignalMetrics(null);
      setProvenance(null);
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
    fetch(`${import.meta.env.VITE_GROOVY_API ?? "http://127.0.0.1:8188"}/api/cache/${output.cache_id}/provenance`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setProvenance)
      .catch(() => setProvenance(null));
  }, [output?.cache_id]);

  useEffect(() => {
    if (!node || node.type !== "LoadAudio") {
      setFileMeta(null);
      return;
    }
    const path = typeof node.widgets.path === "string" ? node.widgets.path.trim() : "";
    if (!path) {
      setFileMeta(null);
      return;
    }
    fetchAudioFileMeta(path)
      .then(setFileMeta)
      .catch(() => setFileMeta(null));
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

  if (!node) {
    return (
      <aside className="node-helper node-helper--compare-only">
        <div className="node-helper__scroll">
          {showCompare ? (
            <ComparePanel
              comparePair={comparePair}
              compareNote={compareNote}
              compareMissingRender={compareMissingRender}
              chainHops={chainHops}
              waveforms={compareWaveforms}
              onCompareAudition={onCompareAudition}
              onSelectCompareHop={onSelectCompareHop}
            />
          ) : (
            <p className="node-helper__empty-hint">Select a node to edit parameters.</p>
          )}
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
      <div className="node-helper__scroll">
        {showCompare ? (
          <ComparePanel
            comparePair={comparePair}
            compareNote={compareNote}
            compareMissingRender={compareMissingRender}
            chainHops={chainHops}
            waveforms={compareWaveforms}
            onCompareAudition={onCompareAudition}
            onSelectCompareHop={onSelectCompareHop}
          />
        ) : null}
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
          disabled={!output?.cache_id}
        >
          Provenance
        </button>
      </nav>
      <div className="node-helper__body">
        {tab === "config" && schema ? (
          <div className="node-helper__widgets">
            {modelCard ? (
              <section className="node-helper__model-panel">
                <h4 className="node-helper__compare-subtitle">Selected model</h4>
                <p className="node-helper__model-name">{modelCard.name}</p>
                <p className="node-helper__hint">{modelCard.description}</p>
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
            {schema.widgets.map((widget) => (
              <label key={widget.name} className="node-helper__field">
                <span>{widgetLabel(widget.name, node.type)}</span>
                {widget.description ? <small className="node-helper__hint">{widget.description}</small> : null}
                <WidgetInput
                  spec={widget}
                  value={node.widgets[widget.name] ?? widget.default ?? ""}
                  onChange={(value) => onWidgetChange(node.id, widget.name, value)}
                  onBrowse={
                    widget.type === "MODEL_REF"
                      ? () => onBrowseModel?.(node.id, widget.name)
                      : undefined
                  }
                />
              </label>
            ))}
            {node.type === "SaveAudio" ? (
              <p className="node-helper__hint">
                Writes to <code>{joinSaveAudioPath(node.widgets.path, node.widgets.filename)}</code> under the
                project folder.
              </p>
            ) : null}
            {schema.widgets.length === 0 && node.type !== "SaveAudio" ? (
              <p className="node-helper__hint">No configurable parameters.</p>
            ) : null}
            {node.type === "LoadAudio" ? (
              <AudioFormatPanel meta={fileMeta} title="Source file format" />
            ) : null}
            {node.type === "LoadAudio" && !fileMeta && node.widgets.path ? (
              <p className="node-helper__hint">Could not read format metadata for this path.</p>
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
              {schema.outputs.map((socket, index) => (
                <li key={socket.name} className="node-helper__socket-detail">
                  <div className="node-helper__socket-detail-head">
                    <SocketTypeBadge type={socket.type} />
                    <strong className="node-helper__socket-name">{socket.name}</strong>
                  </div>
                  {socket.description ? <p className="node-helper__hint">{socket.description}</p> : null}
                  {output && (index === 0 || output.type === socket.type) ? (
                    <OutputSnapshot
                      output={output}
                      socketType={socket.type}
                      meta={meta}
                      signalMetrics={signalMetrics}
                      waveform={waveform}
                    />
                  ) : (
                    <p className="node-helper__hint">Render to populate this output.</p>
                  )}
                </li>
              ))}
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
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AbCompareResult | null>(null);

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
        <h3 className="node-helper__compare-title">A/B compare</h3>
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

  return (
    <section className="node-helper__compare">
      <h3 className="node-helper__compare-title">A/B compare</h3>
      {compareNote ? <p className="node-helper__compare-info">{compareNote}</p> : null}
      <p className="node-helper__hint">
        Comparing rendered audio between two nodes. Shift- or ⌘/Ctrl-click to change selection.
      </p>
      {sameCache && !compareNote ? (
        <p className="node-helper__compare-warning">
          A and B share the same cached audio ({a.output.cache_id?.slice(0, 8)}…).
        </p>
      ) : null}
      <WaveformCompare
        peaksA={peaksA}
        peaksB={peaksB}
        labelA={legendA}
        labelB={legendB}
        titleA={labelA}
        titleB={labelB}
      />
      <div className="node-helper__compare-actions">
        <button type="button" className="node-helper__audition" onClick={() => onCompareAudition?.(a.node.id)}>
          ▶ A
        </button>
        <button type="button" className="node-helper__audition" onClick={() => onCompareAudition?.(b.node.id)}>
          ▶ B
        </button>
      </div>
      {chainHops.length > 1 ? (
        <div className="node-helper__compare-hops">
          <span className="node-helper__compare-subtitle">Other hops</span>
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
        <h4 className="node-helper__compare-subtitle">Ask about differences</h4>
        <label className="node-helper__field">
          <span>Analysis model</span>
          <select value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={analyzing}>
            {models.length === 0 ? <option value={modelId}>{modelId}</option> : null}
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
        {selectedModel?.description ? (
          <p className="node-helper__hint">{selectedModel.description}</p>
        ) : null}
        <label className="node-helper__field">
          <span>Your question</span>
          <textarea
            rows={3}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What are the differences between A and B?"
            disabled={analyzing}
          />
        </label>
        <button
          type="button"
          className="node-helper__compare-analyze"
          onClick={() => void runAnalysis()}
          disabled={analyzing || !a.output.cache_id || !b.output.cache_id}
        >
          {analyzing ? "Analyzing…" : "Analyze differences"}
        </button>
        {error ? <p className="node-helper__compare-error">{error}</p> : null}
        {result ? (
          <div className="node-helper__compare-result">
            <p className={`node-helper__compare-verdict node-helper__compare-verdict--${result.verdict}`}>
              {result.verdict_summary}
            </p>
            {result.differences.length > 0 ? (
              <ul className="node-helper__list node-helper__compare-diff-list">
                {result.differences.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
            <div className="node-helper__compare-result-scroll">
              <p className="node-helper__compare-result-text">{formatNarrative(result.narrative)}</p>
              {result.mode === "transcript" ? (
                <details className="node-helper__compare-details">
                  <summary>Transcripts</summary>
                  <p className="node-helper__compare-transcript">
                    <strong>A:</strong> {result.transcript_a}
                  </p>
                  <p className="node-helper__compare-transcript">
                    <strong>B:</strong> {result.transcript_b}
                  </p>
                </details>
              ) : null}
              <details className="node-helper__compare-details">
                <summary>Signal metrics ({result.facts.length})</summary>
                <ul className="node-helper__list node-helper__compare-facts">
                  {result.facts.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </details>
            </div>
          </div>
        ) : null}
      </div>
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
  meta,
  signalMetrics,
  waveform,
}: {
  output: JobOutput;
  socketType: string;
  meta: Record<string, unknown> | null;
  signalMetrics: CacheSignalMetrics | null;
  waveform: number[];
}) {
  if (output.type !== socketType && socketType !== "AUDIO") {
    if (socketType === "STRING" && (output.type === "STRING" || output.type === "TEXT")) {
      // SaveAudio path output (STRING) or legacy TEXT path payloads
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
      {output.type === "TEXT" && output.text ? <p className="node-helper__text">{output.text}</p> : null}
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

function formatNarrative(narrative: string): string {
  return narrative.replace(/\*\*(.*?)\*\*/g, "$1").replace(/\*(.*?)\*/g, "$1");
}

function widgetLabel(name: string, nodeType: string): string {
  if (nodeType === "SaveAudio") {
    if (name === "path") return "Output folder";
    if (name === "filename") return "File name";
    if (name === "format") return "Format";
    if (name === "bit_depth") return "Bit depth";
  }
  return name;
}

type WidgetInputProps = {
  spec: { name: string; type: string; default?: unknown; description?: string };
  value: unknown;
  onChange: (value: unknown) => void;
  onBrowse?: () => void;
};

function WidgetInput({ spec, value, onChange, onBrowse }: WidgetInputProps) {
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
  if (spec.type === "FLOAT" || spec.type === "INT") {
    return (
      <input
        type="number"
        step={spec.type === "FLOAT" ? "any" : "1"}
        value={typeof value === "number" ? value : Number(value)}
        onChange={(e) => onChange(spec.type === "INT" ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
      />
    );
  }
  return (
    <input
      type="text"
      value={typeof value === "string" ? value : String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
