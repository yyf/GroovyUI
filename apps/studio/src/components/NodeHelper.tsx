import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API,
  analyzeAbCompare,
  fetchAudioFileMeta,
  fetchAuthenticity,
  fetchCacheMeta,
  fetchCacheMetrics,
  fetchCompareModels,
  fetchMeterEnvelope,
  fetchModelCard,
  fetchNodeSchema,
  fetchSampleCheck,
  fetchWaveform,
  revealProjectPath,
  uploadProjectAudio,
  type AbCompareResult,
  type CacheSignalMetrics,
  type MeterEnvelopePayload,
} from "../api";
import type { JobOutput, ModelCard, NodeSchema, Workflow, WorkflowLink, WorkflowNode } from "../types";
import type { CompareHop } from "../workflow";
import {
  joinSaveAudioPath,
  jobOutputAtSlot,
  meterDisplayText,
  resolveIoChannelLabel,
  wiredInputSupersedesWidget,
  wiredInputsForNode,
  wiredOutputsForNode,
  wiredPromptPreview,
} from "../workflow";
import { hasMinimalPatch } from "../nodeMinimalPatches";
import { EDGE_COLOR_PALETTE, normalizeEdgeColor, socketTypeColor } from "../socketTypes";
import {
  asWidgetSpec,
  mergeSpecWithModelParam,
  modelParamByName,
  paramDefault,
  resolveInferenceParams,
} from "../modelNodeWidgets";
import AudioFormatPanel from "./AudioFormatPanel";
import CompareMetricsViz from "./CompareMetricsViz";
import TrajectoryPanel, { TrajectoryAuthorPad } from "./TrajectoryPanel";
import CompareSampleIntegrity, { SampleCheckFromReport } from "./CompareSampleIntegrity";
import ControlCurvePreview, { syncPointsFromStartEnd } from "./ControlCurvePreview";
import MatrixMixerPanel from "./MatrixMixerPanel";
import ModelSubgraphPanel from "./ModelSubgraphPanel";
import { ParamFader, ParamPot, ParamStepped, ParamSwitch } from "./ParamControls";
import SocketTypeBadge from "./SocketTypeBadge";
import WaveformCompare from "./WaveformCompare";
import WaveformMini from "./WaveformMini";
import { resolveWidgetControl } from "../widgetControls";

const GENERATIVE_NODE_TYPES = new Set(["GenerateAudio", "TTS", "MIDIToAudio", "SingFromMIDI"]);

/** Pin exploration controls (model → prompt-like → seed) above the rest of Config. */
const EXPLORATION_WIDGET_ORDER = ["model", "prompt", "text", "lyrics", "seed"];

type Tab = "config" | "subgraph" | "inputs" | "outputs" | "provenance";

type CompareEntry = {
  node: WorkflowNode;
  output: JobOutput;
};

type Props = {
  node: WorkflowNode | null;
  /** When a wire is selected on the canvas (takes priority over empty node selection). */
  selectedLink?: WorkflowLink | null;
  onLinkColorChange?: (linkId: string, color: string | null) => void;
  selectedNodes?: WorkflowNode[];
  selectionOutputs?: Record<string, JobOutput> | null;
  loadAudioChannels?: Record<string, number>;
  channelLayouts?: Record<string, string>;
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
  /** Disconnect all canvas wires on one input/output slot (Subgraph tab checkboxes). */
  onDisconnectPort?: (nodeId: string, direction: "in" | "out", slot: number) => void;
  /** Remove the currently selected canvas wire. */
  onDeleteLink?: (linkId: string) => void;
  /** Widen Inspector while Subgraph tab is active. */
  onSubgraphActiveChange?: (active: boolean) => void;
  onBrowseModel?: (nodeId: string, widgetName: string) => void;
  onAudition?: () => void;
  onCompareAudition?: (nodeId: string) => void;
  onOpenCompliance?: () => void;
  renderIssue?: string | null;
  renderIssueDetail?: string | null;
};

export default function NodeHelper({
  node,
  selectedLink = null,
  onLinkColorChange,
  selectedNodes = [],
  selectionOutputs = null,
  loadAudioChannels,
  channelLayouts,
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
  onDisconnectPort,
  onDeleteLink,
  onSubgraphActiveChange,
  onBrowseModel,
  onAudition,
  onCompareAudition,
  onOpenCompliance,
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
    // Meter / VerifySamples: jump to Outputs so levels / checks are visible immediately.
    if (node?.type === "Meter" || node?.type === "VerifySamples") {
      setTab("outputs");
    } else {
      setTab("config");
    }
  }, [node?.id, node?.type]);

  const subgraphWide =
    Boolean(node) &&
    !showCompare &&
    !selectedLink &&
    selectedNodes.length <= 1 &&
    tab === "subgraph";

  useEffect(() => {
    onSubgraphActiveChange?.(subgraphWide);
    return () => onSubgraphActiveChange?.(false);
  }, [subgraphWide, onSubgraphActiveChange]);

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
    fetch(`${API}/api/cache/${primary.cache_id}/provenance`)
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

  const outputRows = useMemo(
    () => (schema && node ? wiredOutputsForNode(workflow, node.id, schema.outputs) : []),
    [schema, node, workflow],
  );

  const modelParams = useMemo(
    () => resolveInferenceParams(selectedModelId ?? "", modelCard?.inference_params),
    [modelCard?.inference_params, selectedModelId],
  );
  const modelParamMap = useMemo(() => modelParamByName(modelParams), [modelParams]);

  const modelParamRows = useMemo(() => {
    if (!selectedModelId || !schema) return [];
    const widgetNames = new Set(schema.widgets.map((widget) => widget.name));
    return modelParams.filter((param) => !widgetNames.has(param.name));
  }, [modelParams, schema, selectedModelId]);

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
            workflow={workflow}
            loadAudioChannels={loadAudioChannels}
            channelLayouts={channelLayouts}
            selectionOutputs={selectionOutputs}
          />
        </div>
      </aside>
    );
  }

  if (selectedLink) {
    const typeColor = socketTypeColor(selectedLink.type);
    const custom = normalizeEdgeColor(selectedLink.color);
    return (
      <aside className="node-helper node-helper--compare-only">
        <header className="node-helper__header">
          <h2>Connection</h2>
          <span className="node-helper__id">{selectedLink.id}</span>
        </header>
        <div className="node-helper__scroll">
          <p className="node-helper__edge-meta">
            <SocketTypeBadge type={selectedLink.type} />{" "}
            {selectedLink.from[0]}:{selectedLink.from[1]} → {selectedLink.to[0]}:{selectedLink.to[1]}
          </p>
          <label className="node-helper__field">
            Stroke color
            <div className="edge-color-picker" role="listbox" aria-label="Connection color">
              {EDGE_COLOR_PALETTE.map((hex) => {
                const active = (custom ?? typeColor).toLowerCase() === hex.toLowerCase();
                return (
                  <button
                    key={hex}
                    type="button"
                    role="option"
                    aria-selected={active}
                    title={hex}
                    className={`edge-color-picker__swatch${active ? " edge-color-picker__swatch--active" : ""}`}
                    style={{ background: hex }}
                    onClick={() => onLinkColorChange?.(selectedLink.id, hex)}
                  />
                );
              })}
            </div>
          </label>
          <button
            type="button"
            className="edge-color-picker__reset"
            disabled={!custom}
            onClick={() => onLinkColorChange?.(selectedLink.id, null)}
          >
            Reset to type default
          </button>
          <button
            type="button"
            className="node-helper__delete-link"
            onClick={() => onDeleteLink?.(selectedLink.id)}
          >
            Delete connection
          </button>
          <p className="node-helper__hint">Or press Delete / Backspace after clicking the wire.</p>
        </div>
      </aside>
    );
  }

  if (selectedNodes.length > 2) {
    return (
      <aside className="node-helper node-helper--selection-only">
        <div className="node-helper__scroll">
          <MultiSelectSummary
            nodes={selectedNodes}
            workflow={workflow}
            outputs={selectionOutputs}
            loadAudioChannels={loadAudioChannels}
            channelLayouts={channelLayouts}
          />
        </div>
      </aside>
    );
  }

  if (!node) {
    return (
      <aside className="node-helper node-helper--compare-only">
        <div className="node-helper__scroll">
          <p className="node-helper__empty-hint">Select a node or connection to edit.</p>
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
        {schema && (schema.sample_accurate !== undefined || schema.deterministic !== undefined || schema.duration_locked !== undefined) ? (
          <p className="node-helper__integrity-meta" title="Integrity metadata only — does not change render behavior">
            {[
              schema.sample_accurate === false
                ? "offline bus: n/a"
                : schema.sample_accurate
                  ? "offline sample-accurate"
                  : null,
              schema.deterministic === false ? "nondeterministic" : schema.deterministic ? "deterministic" : null,
              schema.duration_locked === false
                ? "duration model-chosen"
                : schema.duration_locked
                  ? "duration locked"
                  : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        ) : null}
        {hasMinimalPatch(node.type) ? (
          <p className="node-helper__hint">Press <kbd>Tab</kbd> to wire missing example inputs and outputs for this node.</p>
        ) : null}
        <nav className="node-helper__tabs">
        <button type="button" className={tab === "config" ? "active" : ""} onClick={() => setTab("config")}>
          Config
        </button>
        <button
          type="button"
          className={tab === "subgraph" ? "active" : ""}
          onClick={() => setTab("subgraph")}
          disabled={!schema}
        >
          Subgraph
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
        {node.type !== "SaveAudio" ? (
          <button
            type="button"
            className={tab === "provenance" ? "active" : ""}
            onClick={() => setTab("provenance")}
            disabled={!jobOutputAtSlot(output, 0)?.cache_id && !output?.cache_id}
          >
            Provenance
          </button>
        ) : null}
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
            {node.type === "ControlCurve" ? (
              <section className="node-helper__curve-panel">
                <h4 className="node-helper__compare-subtitle">Curve</h4>
                <ControlCurvePreview
                  widgets={node.widgets}
                  onChange={(patch) => {
                    for (const [name, value] of Object.entries(patch)) {
                      onWidgetChange(node.id, name, value);
                    }
                  }}
                />
              </section>
            ) : null}
            {node.type === "TrajectoryAuthor" ? (
              <section className="node-helper__trajectory-author">
                <h4 className="node-helper__compare-subtitle">Object path</h4>
                <TrajectoryAuthorPad
                  widgets={node.widgets}
                  onChange={(patch) => {
                    for (const [name, value] of Object.entries(patch)) {
                      onWidgetChange(node.id, name, value);
                    }
                  }}
                />
              </section>
            ) : null}
            {node.type === "MatrixMixer" ? (
              <section className="node-helper__matrix-panel">
                <h4 className="node-helper__compare-subtitle">Matrix</h4>
                <MatrixMixerPanel
                  widgets={node.widgets}
                  onChange={(name, value) => onWidgetChange(node.id, name, value)}
                />
              </section>
            ) : null}
            {(() => {
              const widgetsForForm =
                node.type === "ControlCurve"
                  ? schema.widgets.filter((widget) => widget.name !== "points")
                  : node.type === "TrajectoryAuthor"
                    ? schema.widgets.filter(
                        (widget) =>
                          !["start_x", "start_z", "end_x", "end_z", "points"].includes(widget.name),
                      )
                  : node.type === "MatrixMixer"
                    ? schema.widgets.filter((widget) => !widget.name.startsWith("gain_"))
                    : schema.widgets;
              const { pinned, rest } = partitionExplorationWidgets(widgetsForForm, node.type);
              const renderWidget = (widget: (typeof schema.widgets)[number]) => {
                const mergedWidget = mergeSpecWithModelParam(widget, modelParamMap.get(widget.name));
                const supersededBy = wiredInputSupersedesWidget(node.type, mergedWidget.name, inputRows);
                const wiredPreview = supersededBy ? wiredPromptPreview(supersededBy.sourceNode) : null;
                return (
                  <label
                    key={mergedWidget.name}
                    className={[
                      "node-helper__field",
                      supersededBy ? "node-helper__field--superseded" : "",
                      isPromptLikeWidget(mergedWidget.name) ? "node-helper__field--prompt" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <span>{widgetLabel(mergedWidget.name, node.type)}</span>
                    {mergedWidget.description ? <small className="node-helper__hint">{mergedWidget.description}</small> : null}
                    {supersededBy ? (
                      <small className="node-helper__hint node-helper__hint--wired">
                        {node.type === "TrajectoryAuthor" &&
                        (mergedWidget.name === "duration_sec" || mergedWidget.name === "sample_rate") ? (
                          <>
                            Locked to wired LoadAudio
                            {mergedWidget.name === "duration_sec" && node.widgets.duration_sec != null
                              ? ` · ${Number(node.widgets.duration_sec).toFixed(3)} s`
                              : null}
                            {mergedWidget.name === "sample_rate" && node.widgets.sample_rate != null
                              ? ` · ${Number(node.widgets.sample_rate)} Hz`
                              : null}
                          </>
                        ) : (
                          <>
                            Wired from {supersededBy.sourceNode?.type ?? "upstream"}
                            {supersededBy.sourceNode?.id ? (
                              <>
                                {" "}
                                <span className="node-helper__mono">({supersededBy.sourceNode.id})</span>
                              </>
                            ) : null}
                            — edit on the source node.
                          </>
                        )}
                      </small>
                    ) : null}
                    {wiredPreview ? (
                      <p className="node-helper__wired-preview" title="Resolved prompt at render">
                        {wiredPreview}
                      </p>
                    ) : null}
                    <WidgetInput
                      spec={mergedWidget}
                      value={node.widgets[mergedWidget.name] ?? mergedWidget.default ?? ""}
                      onChange={(value) => {
                        if (node.type === "ControlCurve") {
                          const synced = syncPointsFromStartEnd(node.widgets, mergedWidget.name, value);
                          if (synced) {
                            for (const [name, next] of Object.entries(synced)) {
                              onWidgetChange(node.id, name, next);
                            }
                            return;
                          }
                        }
                        onWidgetChange(node.id, mergedWidget.name, value);
                        if (
                          node.type === "SaveAudio" &&
                          mergedWidget.name === "format" &&
                          String(value).toLowerCase() === "flac"
                        ) {
                          const depth = String(node.widgets.bit_depth ?? "float").toLowerCase();
                          if (depth !== "16" && depth !== "24") {
                            onWidgetChange(node.id, "bit_depth", "24");
                          }
                        }
                      }}
                      disabled={Boolean(supersededBy)}
                      nodeType={node.type}
                      nodeWidgets={node.widgets}
                      onMultiWidgetChange={(name, value) => onWidgetChange(node.id, name, value)}
                      onBrowse={
                        mergedWidget.type === "MODEL_REF"
                          ? () => onBrowseModel?.(node.id, mergedWidget.name)
                          : undefined
                      }
                    />
                  </label>
                );
              };
              return (
                <>
                  {pinned.length > 0 ? (
                    <section className="node-helper__exploration">
                      <h4 className="node-helper__compare-subtitle">Exploration</h4>
                      {pinned.map(renderWidget)}
                    </section>
                  ) : null}
                  {rest.map(renderWidget)}
                </>
              );
            })()}
            {modelParamRows.length > 0 ? (
              <section className="node-helper__model-params">
                <h4 className="node-helper__compare-subtitle">Model parameters</h4>
                {modelParamRows.map((param) => {
                  const spec = asWidgetSpec(param);
                  return (
                  <label key={param.name} className="node-helper__field">
                    <span>{widgetLabel(param.name, node.type)}</span>
                    {param.description ? <small className="node-helper__hint">{param.description}</small> : null}
                    <WidgetInput
                      spec={spec}
                      value={node.widgets[param.name] ?? paramDefault(param)}
                      onChange={(value) => onWidgetChange(node.id, param.name, value)}
                    />
                  </label>
                  );
                })}
              </section>
            ) : null}
            {node.type === "SaveAudio" ? (
              <>
                <p className="node-helper__hint">
                  Filename template:{" "}
                  <code>
                    {joinSaveAudioPath(
                      node.widgets.path,
                      node.widgets.filename,
                      node.widgets.format,
                    )}
                  </code>
                  . The extension follows Format and a UTC timestamp is appended when rendered. Use
                  Choose file… to pick the folder and base name.
                </p>
                {output?.type === "STRING" && output.path && output.provenance_path ? (
                  <SaveAudioExportPair output={output} onOpenCompliance={onOpenCompliance} />
                ) : null}
              </>
            ) : null}
            {node.type === "LoadAudio" ? (
              <p className="node-helper__hint">
                Choose a file to upload into the project, or enter a project-relative path (e.g.{" "}
                <code>assets/samples/podcast_denoise_demo.wav</code>). You can also drop audio onto the canvas.
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
        {tab === "subgraph" && schema ? (
          <ModelSubgraphPanel
            nodeType={node.type}
            modelLabel={selectedModelId}
            inputs={inputRows.map((row) => ({
              index: row.index,
              name: row.name,
              type: row.type,
              optional: row.optional,
              connected: row.connected,
              detail: row.connected
                ? `← ${row.sourceNode?.type ?? "upstream"}${row.sourceNode?.id ? ` (${row.sourceNode.id.slice(0, 8)})` : ""}`
                : row.optional
                  ? "optional — unwired"
                  : "required — unwired",
            }))}
            outputs={outputRows.map((row) => ({
              index: row.index,
              name: row.name,
              type: row.type,
              connected: row.connected,
              detail: row.connected
                ? `→ ${row.linkCount} wire${row.linkCount === 1 ? "" : "s"}`
                : "unwired",
            }))}
            architectureNotes={modelCard?.architecture_notes}
            internalConnections={modelCard?.internal_connections}
            onDisconnectInput={(slot) => onDisconnectPort?.(node.id, "in", slot)}
            onDisconnectOutput={(slot) => onDisconnectPort?.(node.id, "out", slot)}
            config={
              <div className="model-subgraph__config-fields">
                {(() => {
                  const widgetsForForm =
                    node.type === "ControlCurve"
                      ? schema.widgets.filter((widget) => widget.name !== "points")
                      : node.type === "TrajectoryAuthor"
                        ? schema.widgets.filter(
                            (widget) =>
                              !["start_x", "start_z", "end_x", "end_z", "points"].includes(widget.name),
                          )
                      : node.type === "MatrixMixer"
                        ? schema.widgets.filter((widget) => !widget.name.startsWith("gain_"))
                        : schema.widgets;
                  const { pinned, rest } = partitionExplorationWidgets(widgetsForForm, node.type);
                  const renderWidget = (widget: (typeof schema.widgets)[number]) => {
                    const mergedWidget = mergeSpecWithModelParam(widget, modelParamMap.get(widget.name));
                    const supersededBy = wiredInputSupersedesWidget(node.type, mergedWidget.name, inputRows);
                    return (
                      <label
                        key={mergedWidget.name}
                        className={[
                          "node-helper__field",
                          supersededBy ? "node-helper__field--superseded" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <span>{widgetLabel(mergedWidget.name, node.type)}</span>
                        <WidgetInput
                          spec={mergedWidget}
                          value={node.widgets[mergedWidget.name] ?? mergedWidget.default ?? ""}
                          disabled={Boolean(supersededBy)}
                          onChange={(value) => onWidgetChange(node.id, mergedWidget.name, value)}
                          nodeType={node.type}
                          nodeWidgets={node.widgets}
                          onMultiWidgetChange={(name, value) => onWidgetChange(node.id, name, value)}
                          onBrowse={
                            mergedWidget.type === "MODEL_REF"
                              ? () => onBrowseModel?.(node.id, mergedWidget.name)
                              : undefined
                          }
                        />
                      </label>
                    );
                  };
                  return (
                    <>
                      {[...pinned, ...rest].map(renderWidget)}
                      {modelParamRows.map((param) => {
                        const spec = asWidgetSpec(param);
                        return (
                          <label key={param.name} className="node-helper__field">
                            <span>{widgetLabel(param.name, node.type)}</span>
                            <WidgetInput
                              spec={spec}
                              value={node.widgets[param.name] ?? paramDefault(param)}
                              onChange={(value) => onWidgetChange(node.id, param.name, value)}
                            />
                          </label>
                        );
                      })}
                      {widgetsForForm.length === 0 && modelParamRows.length === 0 ? (
                        <p className="node-helper__hint">No configurable parameters on this node.</p>
                      ) : null}
                    </>
                  );
                })()}
              </div>
            }
          />
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
            {node?.type === "VerifySamples" ? (
              <VerifySamplesOutputsPanel output={output} onAudition={previewUrl ? onAudition : undefined} />
            ) : node?.type === "Meter" ? (
              <MeterOutputsPanel output={output} onAudition={previewUrl ? onAudition : undefined} />
            ) : (
              <>
                {(() => {
                  const pair = resolveTrajectoryPair(workflow, selectionOutputs ?? null);
                  if (!pair.inputId && !pair.outputId) return null;
                  if (
                    node?.type !== "TrajectoryAuthor" &&
                    node?.type !== "TrajectoryMonitor" &&
                    node?.type !== "AmbisonicTrajectoryExtract" &&
                    node?.type !== "AmbisonicUpmix"
                  ) {
                    return null;
                  }
                  return (
                    <TrajectoryPanel
                      inputId={pair.inputId}
                      outputId={pair.outputId}
                      compact
                      className="trajectory-panel--helper"
                    />
                  );
                })()}
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
                            onOpenCompliance={
                              node.type === "SaveAudio" || socket.type === "AUTHENTICITY"
                                ? onOpenCompliance
                                : undefined
                            }
                          />
                        ) : (
                          <p className="node-helper__hint">Render to populate this output.</p>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {previewUrl ? (
                  <button type="button" className="node-helper__audition" onClick={onAudition}>
                    ▶ Audition node
                  </button>
                ) : null}
              </>
            )}
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
  loadAudioChannels,
  channelLayouts,
}: {
  nodes: WorkflowNode[];
  workflow: Workflow;
  outputs?: Record<string, JobOutput> | null;
  loadAudioChannels?: Record<string, number>;
  channelLayouts?: Record<string, string>;
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
      return Boolean(out?.cache_id || out?.midi_id || out?.text || out?.stems || out?.outputs?.length);
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
        <h4 className="node-helper__compare-section-title">Channels</h4>
        <ul className="node-helper__selection-nodes">
          {nodes.map((node) => {
            const channel =
              resolveIoChannelLabel(
                workflow,
                node.id,
                loadAudioChannels,
                outputs ?? undefined,
                channelLayouts,
              ) ?? "—";
            return (
              <li key={`ch-${node.id}`}>
                <span className="node-helper__selection-id">{node.id}</span>
                <span className="node-helper__selection-node-type">{node.type}</span>
                <span className="node-helper__selection-channel">{channel}</span>
              </li>
            );
          })}
        </ul>
      </div>

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
            const hasRender = Boolean(
              out?.cache_id || out?.midi_id || out?.text || out?.stems || out?.outputs?.length,
            );
            const channel =
              resolveIoChannelLabel(
                workflow,
                node.id,
                loadAudioChannels,
                outputs ?? undefined,
                channelLayouts,
              ) ?? "—";
            return (
              <li key={node.id}>
                <span className="node-helper__selection-id">{node.id}</span>
                <span className="node-helper__selection-node-type">{node.type}</span>
                <span className="node-helper__selection-channel">{channel}</span>
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
  workflow,
  loadAudioChannels,
  channelLayouts,
  selectionOutputs,
}: {
  comparePair?: CompareEntry[] | null;
  compareNote?: string | null;
  compareMissingRender?: boolean;
  chainHops?: CompareHop[];
  waveforms: [number[], number[]];
  onCompareAudition?: (nodeId: string) => void;
  onSelectCompareHop?: (nodeIdA: string, nodeIdB: string) => void;
  workflow: Workflow;
  loadAudioChannels?: Record<string, number>;
  channelLayouts?: Record<string, string>;
  selectionOutputs?: Record<string, JobOutput> | null;
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
  const channelA = a
    ? resolveIoChannelLabel(
        workflow,
        a.node.id,
        loadAudioChannels,
        selectionOutputs ?? undefined,
        channelLayouts,
      ) ?? "—"
    : "—";
  const channelB = b
    ? resolveIoChannelLabel(
        workflow,
        b.node.id,
        loadAudioChannels,
        selectionOutputs ?? undefined,
        channelLayouts,
      ) ?? "—"
    : "—";

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

      <p className="node-helper__sample-inline node-helper__sample-inline--channels">
        <span>
          <em>A channels</em> {channelA}
        </span>
        <span>
          <em>B channels</em> {channelB}
        </span>
      </p>

      <CompareSampleIntegrity
        cacheIdA={a.output.cache_id}
        cacheIdB={b.output.cache_id}
        labelA={legendA}
        labelB={legendB}
      />

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

              <p className="node-helper__sample-inline">
                <span>
                  <em>Model</em> {models.find((model) => model.id === result.model_id)?.name ?? result.model_id}
                </span>
                <span>
                  <em>Clips</em> {legendA} (A) vs {legendB} (B)
                </span>
              </p>

              <CompareSampleIntegrity
                cacheIdA={a.output.cache_id}
                cacheIdB={b.output.cache_id}
                labelA={legendA}
                labelB={legendB}
              />

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
              <CompareSampleIntegrity
                cacheIdA={a.output.cache_id}
                cacheIdB={b.output.cache_id}
                labelA={legendA}
                labelB={legendB}
              />
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

/** Meter Outputs tab — channel bars + head/tail first (Inspector-only; not on canvas). */
function MeterOutputsPanel({
  output,
  onAudition,
}: {
  output?: JobOutput;
  onAudition?: () => void;
}) {
  const levelsSlot =
    jobOutputAtSlot(output, 1)?.type === "TEXT"
      ? jobOutputAtSlot(output, 1)
      : output?.type === "MULTI"
        ? output.outputs?.find((slot) => slot.type === "TEXT" && typeof slot.text === "string")
        : output?.type === "TEXT"
          ? output
          : undefined;
  const thruSlot =
    jobOutputAtSlot(output, 0)?.type === "AUDIO" || jobOutputAtSlot(output, 0)?.type === "AMBISONICS"
      ? jobOutputAtSlot(output, 0)
      : output?.type === "MULTI"
        ? output.outputs?.find(
            (slot) =>
              (slot.type === "AUDIO" || slot.type === "AMBISONICS") && Boolean(slot.cache_id),
          )
        : output?.type === "AUDIO" || output?.type === "AMBISONICS"
          ? output
          : undefined;
  const levelsText = typeof levelsSlot?.text === "string" ? levelsSlot.text : "";
  const parsed = levelsText ? parseMeterPayload(levelsText) : null;
  const thruCacheId = thruSlot?.cache_id ?? null;
  const thruType = thruSlot?.type === "AMBISONICS" ? "AMBISONICS" : "AUDIO";

  return (
    <div className="node-helper__meter-panel">
      <p className="node-helper__hint">
        Channel meters scrub with Preview play (cached envelope — not a live graph meter). Head/tail
        stats are whole-clip. Auto labels follow inlet layout / FOA·HOA metadata.
      </p>
      {parsed ? (
        <MeterLevelsPanel text={levelsText} cacheId={thruCacheId} />
      ) : levelsText ? (
        <p className="node-helper__text" style={{ whiteSpace: "pre-wrap" }}>
          {meterDisplayText(levelsText)}
        </p>
      ) : (
        <p className="node-helper__hint">Render this Meter node to populate channel levels.</p>
      )}
      {thruCacheId ? (
        <OutputSnapshot output={thruSlot!} socketType={thruType} />
      ) : (
        <p className="node-helper__hint">AUDIO / AMBISONICS passthrough appears here after render.</p>
      )}
      {onAudition ? (
        <button type="button" className="node-helper__audition" onClick={onAudition}>
          ▶ Audition node
        </button>
      ) : null}
    </div>
  );
}

/** VerifySamples Outputs tab — sample check first, no socket boilerplate. */
function VerifySamplesOutputsPanel({
  output,
  onAudition,
}: {
  output?: JobOutput;
  onAudition?: () => void;
}) {
  const reportSlot =
    jobOutputAtSlot(output, 0)?.type === "SAMPLE_CHECK"
      ? jobOutputAtSlot(output, 0)
      : output?.type === "MULTI"
        ? output.outputs?.find((slot) => slot.type === "SAMPLE_CHECK")
        : output?.type === "SAMPLE_CHECK"
          ? output
          : undefined;
  const audioSlot =
    jobOutputAtSlot(output, 1)?.type === "AUDIO"
      ? jobOutputAtSlot(output, 1)
      : output?.type === "MULTI"
        ? output.outputs?.find((slot) => slot.type === "AUDIO" && slot.cache_id)
        : output?.type === "AUDIO"
          ? output
          : undefined;

  const [sampleCheck, setSampleCheck] = useState<Record<string, unknown> | null>(null);
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const id = reportSlot?.sample_check_id;
    if (!id) {
      setSampleCheck(null);
      return;
    }
    let cancelled = false;
    fetchSampleCheck(id)
      .then((report) => {
        if (!cancelled) {
          setSampleCheck((report.sample_check as Record<string, unknown> | undefined) ?? report);
        }
      })
      .catch(() => {
        if (!cancelled) setSampleCheck(null);
      });
    return () => {
      cancelled = true;
    };
  }, [reportSlot?.sample_check_id]);

  useEffect(() => {
    const cacheId = audioSlot?.cache_id;
    if (!cacheId) {
      setMeta(null);
      return;
    }
    fetchCacheMeta(cacheId)
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [audioSlot?.cache_id]);

  if (!reportSlot?.sample_check_id && !audioSlot?.cache_id) {
    return <p className="node-helper__hint">Render this node to populate sample info.</p>;
  }

  return (
    <div className="node-helper__verify-samples">
      {sampleCheck ? (
        <SampleCheckFromReport sampleCheck={sampleCheck} />
      ) : reportSlot?.sample_check_id ? (
        <p className="node-helper__hint">Loading sample check…</p>
      ) : null}
      {meta ? (
        <div className="node-helper__sample-inline">
          <span>
            <em>Source</em> {String(meta.source_node_type ?? "AUDIO")}
          </span>
          <span>
            <em>Cache</em> <code>{String(audioSlot?.cache_id ?? "").slice(0, 8)}…</code>
          </span>
        </div>
      ) : null}
      {onAudition ? (
        <button type="button" className="node-helper__audition" onClick={onAudition}>
          ▶ Audition node
        </button>
      ) : null}
    </div>
  );
}

function resolveTrajectoryPair(
  workflow: Workflow,
  outputs: Record<string, JobOutput> | null,
): { inputId: string | null; outputId: string | null } {
  let inputId: string | null = null;
  let outputId: string | null = null;
  let authorId: string | null = null;
  let extractId: string | null = null;
  if (!outputs) return { inputId, outputId };
  const typeById = new Map(workflow.nodes.map((n) => [n.id, n.type]));
  const roleById = new Map(
    workflow.nodes.map((n) => [n.id, String(n.widgets.role ?? "").toLowerCase()]),
  );
  for (const [nodeId, out] of Object.entries(outputs)) {
    if (out?.type !== "TRAJECTORY" || !out.trajectory_id) continue;
    const nodeType = typeById.get(nodeId);
    if (nodeType === "TrajectoryMonitor") {
      if (roleById.get(nodeId) === "output") outputId = out.trajectory_id;
      else inputId = out.trajectory_id;
    } else if (nodeType === "TrajectoryAuthor") {
      authorId = out.trajectory_id;
    } else if (nodeType === "AmbisonicTrajectoryExtract") {
      extractId = out.trajectory_id;
    }
  }
  return { inputId: inputId ?? authorId, outputId: outputId ?? extractId };
}

function OutputSnapshot({
  output,
  socketType,
  onOpenCompliance,
}: {
  output: JobOutput;
  socketType: string;
  onOpenCompliance?: () => void;
}) {
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null);
  const [signalMetrics, setSignalMetrics] = useState<CacheSignalMetrics | null>(null);
  const [waveform, setWaveform] = useState<number[]>([]);
  const [authenticity, setAuthenticity] = useState<Record<string, unknown> | null>(null);
  const [sampleCheckReport, setSampleCheckReport] = useState<Record<string, unknown> | null>(null);

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

  useEffect(() => {
    const authenticityId = output.authenticity_id;
    if (!authenticityId && output.type !== "AUTHENTICITY") {
      setAuthenticity(null);
      return;
    }
    const id = authenticityId ?? (output.type === "AUTHENTICITY" ? output.authenticity_id : null);
    if (!id) {
      setAuthenticity(null);
      return;
    }
    let cancelled = false;
    fetchAuthenticity(id)
      .then((report) => {
        if (!cancelled) setAuthenticity(report);
      })
      .catch(() => {
        if (!cancelled) setAuthenticity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [output.authenticity_id, output.type]);

  useEffect(() => {
    const id = output.sample_check_id;
    if (!id) {
      setSampleCheckReport(null);
      return;
    }
    let cancelled = false;
    fetchSampleCheck(id)
      .then((report) => {
        if (!cancelled) setSampleCheckReport(report);
      })
      .catch(() => {
        if (!cancelled) setSampleCheckReport(null);
      });
    return () => {
      cancelled = true;
    };
  }, [output.sample_check_id]);

  if (output.type !== socketType && socketType !== "AUDIO") {
    if (socketType === "STRING" && (output.type === "STRING" || output.type === "TEXT")) {
      // SaveAudio path output (STRING) or legacy TEXT path payloads
    } else if (socketType === "MIDI" && output.type === "MIDI") {
      // AudioToMIDI and other MIDI outputs
    } else if (socketType === "TEXT" && output.type === "TEXT") {
      // Prompt node text output
    } else if (socketType === "AUTHENTICITY" && output.type === "AUTHENTICITY") {
      // VerifyProvenance / DeepfakeDetect / AuthenticitySummary
    } else if (socketType === "SAMPLE_CHECK" && output.type === "SAMPLE_CHECK") {
      // VerifySamples
    } else if (socketType === "TRAJECTORY" && output.type === "TRAJECTORY") {
      // TrajectoryAuthor / AmbisonicTrajectoryExtract
    } else {
      return <p className="node-helper__hint">No render for this socket yet.</p>;
    }
  }

  const sampleCheck = sampleCheckReport?.sample_check as Record<string, unknown> | undefined;

  return (
    <div className="node-helper__output-snapshot">
      <p className="node-helper__socket-wire">
        <SocketTypeBadge type={socketType} /> {output.type === "STRING" ? "written" : "cached"}
      </p>
      {output.type === "TRAJECTORY" && output.trajectory_id ? (
        <TrajectoryPanel
          inputId={output.trajectory_id}
          compact
          className="trajectory-panel--helper"
        />
      ) : null}
      {output.type === "SAMPLE_CHECK" || socketType === "SAMPLE_CHECK" ? (
        sampleCheck ? (
          <SampleCheckFromReport sampleCheck={sampleCheck} />
        ) : (
          <p className="node-helper__hint">Render to populate sample check.</p>
        )
      ) : null}
      {output.type === "AUTHENTICITY" || socketType === "AUTHENTICITY" ? (
        <>
          {authenticity?.overall ? (
            <p className="node-helper__hint">
              {(authenticity.overall as { summary?: string }).summary ??
                (authenticity.overall as { label?: string }).label}
            </p>
          ) : null}
          {onOpenCompliance ? (
            <button type="button" className="node-helper__linkish" onClick={onOpenCompliance}>
              Open Compliance · Authenticity
            </button>
          ) : null}
        </>
      ) : null}
      {output.type === "STRING" && output.path && output.provenance_path ? (
        <SaveAudioExportPair output={output} onOpenCompliance={onOpenCompliance} />
      ) : output.type === "STRING" && output.path ? (
        <p className="node-helper__text">
          <code>{output.path}</code>
        </p>
      ) : null}
      {output.type === "MIDI" && output.midi_id ? (
        <p className="node-helper__text">
          MIDI cache <code>{output.midi_id.slice(0, 8)}…</code>
        </p>
      ) : null}
      {output.type === "TEXT" && output.text ? (
        parseMeterPayload(output.text) ? (
          <MeterLevelsPanel text={output.text} cacheId={output.cache_id ?? null} />
        ) : (
          <p className="node-helper__text">{output.text}</p>
        )
      ) : null}
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
          <div className="node-helper__sample-hero node-helper__sample-hero--compact">
            <span className="node-helper__sample-hero-label">Samples</span>
            <strong className="node-helper__sample-hero-value">
              {Number(meta.frame_count || 0).toLocaleString()}
            </strong>
          </div>
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
            {String(meta.frame_count)} samples @ {String(meta.sample_rate)} Hz
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

function parseMeterPayload(text: string): {
  summary: string;
  meter: {
    layout?: string;
    channel_count?: number;
    channels?: Array<{
      name?: string;
      peak_db?: number | null;
      rms_db?: number | null;
      peak_db_head?: number | null;
      peak_db_tail?: number | null;
    }>;
  };
} | null {
  const marker = "§METER§";
  const idx = text.indexOf(marker);
  if (idx < 0) return null;
  const summary = meterDisplayText(text);
  try {
    const meter = JSON.parse(text.slice(idx + marker.length)) as {
      layout?: string;
      channel_count?: number;
      channels?: Array<{
        name?: string;
        peak_db?: number | null;
        rms_db?: number | null;
        peak_db_head?: number | null;
        peak_db_tail?: number | null;
      }>;
    };
    if (!meter || !Array.isArray(meter.channels)) return null;
    return { summary, meter };
  } catch {
    return null;
  }
}

function formatDb(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "−∞";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function linearToDb(peak: number): number | null {
  if (!(peak > 0)) return null;
  return 20 * Math.log10(peak);
}

function dbToBarWidth(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 0;
  // Map −60…0 dBFS → 0…100%
  const clamped = Math.max(-60, Math.min(0, value));
  return ((clamped + 60) / 60) * 100;
}

function useTransportPlayhead(): { tSec: number; playing: boolean } {
  const [tSec, setTSec] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const transport = document.querySelector<HTMLAudioElement>(".transport__audio");
      if (transport) {
        const fromUi = Number(transport.dataset.playheadSec);
        const t =
          Number.isFinite(fromUi) && fromUi >= 0
            ? fromUi
            : !Number.isNaN(transport.currentTime)
              ? transport.currentTime
              : 0;
        setTSec(t);
        setPlaying(!transport.paused && !transport.ended);
      } else {
        setPlaying(false);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return { tSec, playing };
}

function MeterLevelsPanel({ text, cacheId }: { text: string; cacheId?: string | null }) {
  const parsed = parseMeterPayload(text);
  const { tSec, playing } = useTransportPlayhead();
  const [envelope, setEnvelope] = useState<MeterEnvelopePayload | null>(null);
  const [liveDb, setLiveDb] = useState<number[]>([]);
  const holdRef = useRef<number[]>([]);
  const lastTSecRef = useRef(0);

  useEffect(() => {
    if (!cacheId) {
      setEnvelope(null);
      return;
    }
    let cancelled = false;
    fetchMeterEnvelope(cacheId, 512)
      .then((data) => {
        if (!cancelled) setEnvelope(data);
      })
      .catch(() => {
        if (!cancelled) setEnvelope(null);
      });
    return () => {
      cancelled = true;
    };
  }, [cacheId]);

  useEffect(() => {
    if (!envelope?.channels.length || envelope.duration <= 0) {
      setLiveDb([]);
      return;
    }
    const width = envelope.width || envelope.channels[0]?.length || 0;
    if (width <= 0) return;

    const ratio = Math.min(1, Math.max(0, tSec / envelope.duration));
    const idx = Math.min(width - 1, Math.floor(ratio * width));
    const instant = envelope.channels.map((ch) => linearToDb(ch[idx] ?? 0) ?? -60);

    // Scrub / seek: snap like XYZ monitors. Soft release only during continuous play.
    const seekJump = Math.abs(tSec - lastTSecRef.current) > 0.05;
    lastTSecRef.current = tSec;
    if (!playing || seekJump) {
      holdRef.current = instant;
      setLiveDb(instant);
      return;
    }

    const prev = holdRef.current;
    const releaseDbPerSec = 24;
    const next = instant.map((target, i) => {
      const held = prev[i] ?? -60;
      if (target >= held) return target;
      // ~1 frame at 60fps
      return Math.max(target, held - releaseDbPerSec * (1 / 60));
    });
    holdRef.current = next;
    setLiveDb(next);
  }, [envelope, tSec, playing]);

  if (!parsed) {
    return <p className="node-helper__text">{text}</p>;
  }
  const { summary, meter } = parsed;
  const channelCount = meter.channels?.length ?? 0;
  const labels =
    envelope?.labels?.length === channelCount
      ? envelope.labels
      : (meter.channels ?? []).map((ch, i) => ch.name ?? `ch${i}`);

  return (
    <div className="node-helper__meter">
      <p className="node-helper__hint">
        {meter.layout ?? envelope?.layout ?? "auto"} · {channelCount} ch
        {envelope ? ` · ${playing ? "playing" : "scrub"} @ ${tSec.toFixed(2)}s` : null}
      </p>
      <ul className="node-helper__meter-channels node-helper__meter-channels--live">
        {(meter.channels ?? []).map((ch, i) => {
          const live = liveDb[i];
          const fallback = ch.peak_db;
          const displayDb = live != null && Number.isFinite(live) ? live : fallback;
          return (
            <li key={`${labels[i] ?? "ch"}-${i}`} className="node-helper__meter-channel">
              <div className="node-helper__meter-channel-head">
                <strong>{labels[i] ?? ch.name ?? `ch${i}`}</strong>
                <span className="node-helper__meter-live-db">{formatDb(displayDb)} dBFS</span>
              </div>
              <div className="node-helper__meter-bar node-helper__meter-bar--live" aria-hidden>
                <span
                  className="node-helper__meter-bar-fill"
                  style={{ width: `${dbToBarWidth(displayDb)}%` }}
                />
              </div>
              <p className="node-helper__hint">
                clip peak {formatDb(ch.peak_db)} · rms {formatDb(ch.rms_db)} · head{" "}
                {formatDb(ch.peak_db_head)} · tail {formatDb(ch.peak_db_tail)}
              </p>
            </li>
          );
        })}
      </ul>
      <p className="node-helper__text node-helper__meter-summary">{summary}</p>
      {!cacheId ? (
        <p className="node-helper__hint">Wire / render AUDIO passthrough to animate meters on play.</p>
      ) : !envelope ? (
        <p className="node-helper__hint">Loading channel envelopes…</p>
      ) : null}
    </div>
  );
}

function SaveAudioExportPair({
  output,
  onOpenCompliance,
}: {
  output: JobOutput;
  onOpenCompliance?: () => void;
}) {
  const [revealError, setRevealError] = useState<string | null>(null);

  const reveal = async (path: string) => {
    setRevealError(null);
    try {
      await revealProjectPath(path);
    } catch (err) {
      setRevealError(err instanceof Error ? err.message : "Could not open file browser");
    }
  };

  if (!output.path || !output.provenance_path) return null;
  return (
    <section className="node-helper__export-pair" aria-label="Saved audio and provenance">
      <div className="node-helper__export-artifact">
        <span className="node-helper__export-label">Output file</span>
        <button
          type="button"
          className="node-helper__export-path"
          title={`Open in file browser\n${output.path}`}
          onClick={() => void reveal(output.path!)}
        >
          <code>{output.path}</code>
        </button>
      </div>
      <div className="node-helper__export-artifact">
        <span className="node-helper__export-label">Compliance sidecar</span>
        <button
          type="button"
          className="node-helper__export-path"
          title={`Open in file browser\n${output.provenance_path}`}
          onClick={() => void reveal(output.provenance_path!)}
        >
          <code>{output.provenance_path}</code>
        </button>
      </div>
      {revealError ? <p className="node-helper__hint node-helper__export-error">{revealError}</p> : null}
      {onOpenCompliance ? (
        <button type="button" className="node-helper__export-compliance" onClick={onOpenCompliance}>
          Review compliance
        </button>
      ) : null}
    </section>
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
  if (GENERATIVE_NODE_TYPES.has(nodeType)) {
    if (name === "prompt" || (name === "text" && nodeType !== "SingFromMIDI")) return "Prompt";
    if (name === "text" && nodeType === "SingFromMIDI") return "Lyrics";
    if (name === "seed") return "Seed";
    if (name === "model") return "Model";
  }
  if (nodeType === "ControlCurve") {
    if (name === "start_value") return "Start value";
    if (name === "end_value") return "End value";
    if (name === "frame_count") return "Frame count";
    if (name === "sample_rate") return "Sample rate (Hz)";
  }
  return name;
}

function isPromptLikeWidget(name: string): boolean {
  return name === "prompt" || name === "text" || name === "lyrics";
}

function promptPlaceholder(widgetName: string, nodeType: string): string | undefined {
  if (!GENERATIVE_NODE_TYPES.has(nodeType)) return undefined;
  if (widgetName === "prompt") return "describe the sound.";
  if (widgetName === "text" && nodeType === "TTS") return "describe the sound.";
  if (widgetName === "text" && nodeType === "SingFromMIDI") return "type the lyrics.";
  return undefined;
}

function partitionExplorationWidgets<T extends { name: string }>(
  widgets: T[],
  nodeType: string,
): { pinned: T[]; rest: T[] } {
  if (!GENERATIVE_NODE_TYPES.has(nodeType)) {
    return { pinned: [], rest: widgets };
  }
  const byName = new Map(widgets.map((widget) => [widget.name, widget]));
  const pinned: T[] = [];
  const pinnedNames = new Set<string>();
  for (const name of EXPLORATION_WIDGET_ORDER) {
    const widget = byName.get(name);
    if (!widget) continue;
    pinned.push(widget);
    pinnedNames.add(name);
  }
  const rest = widgets.filter((widget) => !pinnedNames.has(widget.name));
  return { pinned, rest };
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
  if (fmt === "mp4" || fmt === "m4a" || fmt === "aac") {
    return [{ description: "MPEG-4 audio", accept: { "audio/mp4": [".mp4", ".m4a"] } }];
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
        accept="audio/*,.wav,.flac,.aiff,.aif,.mp3,.ogg,.opus,.mp4,.m4a,.aac"
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
        accept="audio/*,.wav,.flac,.aiff,.aif,.mp3,.ogg,.opus,.mp4,.m4a,.aac"
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

  if (spec.name === "seed" && (spec.type === "INT" || spec.type === "FLOAT")) {
    const display =
      typeof value === "number" || typeof value === "string" ? String(value) : String(spec.default ?? -1);
    return (
      <input
        type="number"
        value={display}
        disabled={disabled}
        min={typeof spec.min === "number" ? spec.min : -1}
        max={typeof spec.max === "number" ? spec.max : undefined}
        step={1}
        onChange={(e) => {
          const parsed = parseInt(e.target.value, 10);
          onChange(Number.isFinite(parsed) ? parsed : -1);
        }}
      />
    );
  }

  if (
    nodeType &&
    GENERATIVE_NODE_TYPES.has(nodeType) &&
    isPromptLikeWidget(spec.name) &&
    (spec.type === "STRING" || spec.type === "TEXT")
  ) {
    const str = typeof value === "string" ? value : String(value ?? "");
    return (
      <textarea
        rows={3}
        value={str}
        disabled={disabled}
        placeholder={promptPlaceholder(spec.name, nodeType)}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  if (nodeType === "Note" && spec.name === "text" && (spec.type === "STRING" || spec.type === "TEXT")) {
    const str = typeof value === "string" ? value : String(value ?? "");
    return (
      <textarea
        rows={5}
        value={str}
        disabled={disabled}
        placeholder="Add a comment for this patch…"
        onChange={(e) => onChange(e.target.value)}
      />
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
