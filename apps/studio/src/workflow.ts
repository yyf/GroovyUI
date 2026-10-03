import type { Edge, Node } from "@xyflow/react";
import type { JobOutput, NodeRenderStatus, NodeSchema, Workflow, WorkflowGroup, WorkflowLink, WorkflowModule, WorkflowNode, WorkflowValidationResult } from "./types";
import type { GroovyGroupNodeData } from "./components/ModuleGroupNode";
import type { GroovyNodeData, NodeSocketSpec } from "./components/GroovyFlowNode";
import { canvasNodeKind } from "./nodeKinds";
import { edgeTypeClass, normalizeEdgeColor, resolveEdgeStroke } from "./socketTypes";

export function previewOutputSlot(workflow: Workflow, nodeId: string): number {
  const outbound = workflow.links.filter((link) => link.from[0] === nodeId);
  if (!outbound.length) return 0;
  const previewLink = outbound.find((link) => {
    const target = workflow.nodes.find((node) => node.id === link.to[0]);
    return target?.type === "Preview";
  });
  return previewLink?.from[1] ?? outbound[0].from[1];
}

const LISTEN_UPSTREAM_SOCKETS = new Set(["AUDIO", "MIDI"]);

function listenOutputFromInboundLinks(
  workflow: Workflow,
  nodeId: string,
  outputs: Record<string, JobOutput>,
): JobOutput | undefined {
  for (const link of workflow.links) {
    if (link.to[0] !== nodeId) continue;
    if (!LISTEN_UPSTREAM_SOCKETS.has(link.type)) continue;
    const slotOutput = jobOutputAtSlot(outputs[link.from[0]], link.from[1]);
    if (slotOutput && previewListenId(slotOutput, 0)) return slotOutput;
  }
  return undefined;
}

/**
 * PreviewVideo ← VIDEO ← MuxVideo ← AUDIO: transport should audition the muxed PCM,
 * not the VIDEO path (HTML5 video lives on-canvas / Node Helper).
 */
function listenOutputFromVideoChain(
  workflow: Workflow,
  nodeId: string,
  outputs: Record<string, JobOutput>,
  depth = 0,
): JobOutput | undefined {
  if (depth > 8) return undefined;
  const audioOrMidi = listenOutputFromInboundLinks(workflow, nodeId, outputs);
  if (audioOrMidi) return audioOrMidi;
  for (const link of workflow.links) {
    if (link.to[0] !== nodeId || link.type !== "VIDEO") continue;
    const upstream = listenOutputFromVideoChain(workflow, link.from[0], outputs, depth + 1);
    if (upstream) return upstream;
  }
  return undefined;
}

/** Job output slot to audition for a node (direct render or wired upstream). */
export function resolveNodeListenOutput(
  workflow: Workflow,
  nodeId: string,
  outputs?: Record<string, JobOutput>,
): JobOutput | undefined {
  if (!outputs) return undefined;

  const node = workflow.nodes.find((entry) => entry.id === nodeId);
  if (node?.type === "Preview") {
    const wired = listenOutputFromInboundLinks(workflow, nodeId, outputs);
    if (wired) return wired;
  }
  if (node?.type === "PreviewVideo" || node?.type === "MuxVideo") {
    const wired = listenOutputFromVideoChain(workflow, nodeId, outputs);
    if (wired) return wired;
  }

  const direct = outputs[nodeId];
  if (previewListenId(direct, 0)) {
    return jobOutputAtSlot(direct, 0);
  }

  if (direct?.type === "MULTI") {
    const slot = previewOutputSlot(workflow, nodeId);
    const slotOutput = jobOutputAtSlot(direct, slot);
    if (slotOutput && previewListenId(slotOutput, 0)) return slotOutput;
    // SAMPLE_CHECK+AUDIO or AUTHENTICITY+AUDIO — report is often slot 0.
    for (let i = 0; i < (direct.outputs?.length ?? 0); i++) {
      const candidate = jobOutputAtSlot(direct, i);
      if (candidate && previewListenId(candidate, 0)) return candidate;
    }
  }

  return listenOutputFromInboundLinks(workflow, nodeId, outputs);
}

export function resolveNodeListenId(
  workflow: Workflow,
  nodeId: string,
  outputs?: Record<string, JobOutput>,
): string | null {
  const listenOutput = resolveNodeListenOutput(workflow, nodeId, outputs);
  if (!listenOutput) return null;
  return previewCacheId(listenOutput) ?? previewMidiId(listenOutput);
}

/** Prefer a Preview sink for post-render audition, then the last listenable node. */
export function preferredAuditionNodeId(
  workflow: Workflow,
  outputs?: Record<string, JobOutput>,
): string | null {
  const preview = workflow.nodes.find(
    (node) => node.type === "Preview" && resolveNodeListenId(workflow, node.id, outputs),
  );
  if (preview) return preview.id;
  return (
    [...workflow.nodes]
      .reverse()
      .find((node) => resolveNodeListenId(workflow, node.id, outputs))?.id ?? null
  );
}

/** Prefer PreviewVideo when a muxed VIDEO clip is ready (on-node player + transport PCM). */
export function preferredVideoPreviewNodeId(
  workflow: Workflow,
  outputs?: Record<string, JobOutput>,
): string | null {
  if (!outputs) return null;
  const hit = workflow.nodes.find((node) => {
    if (node.type !== "PreviewVideo") return false;
    const out = outputs[node.id];
    return out?.type === "VIDEO" && Boolean(out.path);
  });
  return hit?.id ?? null;
}

/** Project-relative VIDEO path for on-canvas PreviewVideo / MuxVideo players. */
export function previewVideoPath(output?: JobOutput): string | null {
  if (output?.type === "VIDEO" && output.path) return output.path;
  return null;
}

const PREVIEW_VIDEO_DEFAULT_ASPECT = 16 / 9;
const PREVIEW_VIDEO_MIN_W = 120;
const PREVIEW_VIDEO_MAX_W = 960;
const PREVIEW_VIDEO_MIN_H = 68;
const PREVIEW_VIDEO_MAX_H = 720;
/** Title row + video top margin — keep in sync with GroovyFlowNode minHeight. */
const PREVIEW_VIDEO_CHROME_H = 36;
/**
 * Node horizontal chrome for PreviewVideo footprint.
 * Matches `.groovy-node` padding `8px 10px` + `1px` border each side (border-box).
 */
const PREVIEW_VIDEO_CHROME_W = 22;

/** Aspect ratio (width / height) from muxed VIDEO job output, else null. */
export function previewVideoAspect(output?: JobOutput): number | null {
  const w = Number(output?.width);
  const h = Number(output?.height);
  if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) return w / h;
  return null;
}

export function clampPreviewVideoWidth(width: number): number {
  return Math.round(Math.min(PREVIEW_VIDEO_MAX_W, Math.max(PREVIEW_VIDEO_MIN_W, width)));
}

export function clampPreviewVideoHeight(height: number): number {
  return Math.round(Math.min(PREVIEW_VIDEO_MAX_H, Math.max(PREVIEW_VIDEO_MIN_H, height)));
}

/** Keep PreviewVideo on-canvas size locked to source aspect (width or height drives the other). */
export function lockPreviewVideoSize(
  changed: "preview_width" | "preview_height",
  value: number,
  aspect: number = PREVIEW_VIDEO_DEFAULT_ASPECT,
): { preview_width: number; preview_height: number } {
  const ratio = aspect > 0 ? aspect : PREVIEW_VIDEO_DEFAULT_ASPECT;
  if (changed === "preview_width") {
    const preview_width = clampPreviewVideoWidth(value);
    return {
      preview_width,
      preview_height: clampPreviewVideoHeight(preview_width / ratio),
    };
  }
  const preview_height = clampPreviewVideoHeight(value);
  return {
    preview_width: clampPreviewVideoWidth(preview_height * ratio),
    preview_height,
  };
}

export function previewVideoPanelSize(
  node: WorkflowNode,
  output?: JobOutput,
): { width: number; height: number; aspect: number } {
  const aspect = previewVideoAspect(output) ?? PREVIEW_VIDEO_DEFAULT_ASPECT;
  const rawW = Number(node.widgets.preview_width);
  const rawH = Number(node.widgets.preview_height);
  const locked =
    Number.isFinite(rawW) && rawW > 0
      ? lockPreviewVideoSize("preview_width", rawW, aspect)
      : Number.isFinite(rawH) && rawH > 0
        ? lockPreviewVideoSize("preview_height", rawH, aspect)
        : lockPreviewVideoSize("preview_width", 240, aspect);
  return {
    width: locked.preview_width,
    height: locked.preview_height,
    aspect,
  };
}

export function previewVideoNodeFootprint(panel: {
  width: number;
  height: number;
}): { width: number; height: number } {
  return {
    width: panel.width + PREVIEW_VIDEO_CHROME_W,
    height: panel.height + PREVIEW_VIDEO_CHROME_H,
  };
}

export function nodeHasListenableOutput(
  workflow: Workflow,
  nodeId: string,
  outputs?: Record<string, JobOutput>,
): boolean {
  return resolveNodeListenId(workflow, nodeId, outputs) != null;
}

export function cachedStatusFromOutputs(
  workflow: Workflow,
  outputs: Record<string, JobOutput>,
): Record<string, NodeRenderStatus> {
  const cached: Record<string, NodeRenderStatus> = {};
  for (const node of workflow.nodes) {
    const out = outputs[node.id];
    if (
      nodeHasListenableOutput(workflow, node.id, outputs) ||
      out?.cache_id ||
      out?.stems_id ||
      out?.midi_id ||
      out?.authenticity_id ||
      out?.automation_id ||
      out?.type === "MULTI" ||
      out?.type === "TEXT" ||
      out?.type === "STRING" ||
      (out?.type === "VIDEO" && Boolean(out.path))
    ) {
      cached[node.id] = "cached";
    }
  }
  return cached;
}

export function previewCacheId(output?: JobOutput): string | null {
  if (!output?.cache_id) return null;
  return output.cache_id;
}

const STEM_SLOT_NAMES = ["vocals", "drums", "bass", "other"] as const;

export function jobOutputAtSlot(output?: JobOutput, slot = 0): JobOutput | undefined {
  if (!output) return undefined;
  if (output.type === "MULTI" && output.outputs?.length) {
    return output.outputs[slot];
  }
  if (output.type === "STEMS" && output.stems) {
    const name = STEM_SLOT_NAMES[slot];
    const cacheId = name ? output.stems[name] : undefined;
    if (cacheId) return { type: "AUDIO", cache_id: cacheId, name };
    return undefined;
  }
  return slot === 0 ? output : undefined;
}

export function authenticityIdFromOutput(output?: JobOutput): string | null {
  if (!output) return null;
  if (output.authenticity_id) return output.authenticity_id;
  if (output.type === "MULTI" && output.outputs?.length) {
    for (const slot of output.outputs) {
      if (slot.authenticity_id) return slot.authenticity_id;
    }
  }
  return null;
}

/** Prefer AuthenticitySummary even if DeepfakeDetect/Preview is selected. */
export function authenticityReportId(
  workflow: Workflow,
  outputs: Record<string, JobOutput>,
  targetNodeId?: string | null,
): string | null {
  for (const node of workflow.nodes) {
    if (node.type !== "AuthenticitySummary") continue;
    const id = authenticityIdFromOutput(outputs[node.id]);
    if (id) return id;
  }
  if (targetNodeId) {
    const focused = authenticityIdFromOutput(outputs[targetNodeId]);
    if (focused) return focused;
  }
  for (const node of workflow.nodes) {
    const id = authenticityIdFromOutput(outputs[node.id]);
    if (id) return id;
  }
  return null;
}

export function previewMidiId(output?: JobOutput): string | null {
  if (output?.type === "MIDI" && output.midi_id) return output.midi_id;
  if (output?.midi_id && !output.cache_id) return output.midi_id;
  return null;
}

/** Pull TEXT from a job output or the first TEXT slot on MULTI. */
export function textFromJobOutput(output?: JobOutput): string | null {
  if (!output) return null;
  if (output.type === "MULTI" && output.outputs?.length) {
    for (const slot of output.outputs) {
      const nested = textFromJobOutput(slot);
      if (nested) return nested;
    }
    return null;
  }
  const raw = typeof output.text === "string" ? output.text.trim() : "";
  return raw || null;
}

/** Strip §METER§ machine payload; keep human summary + head/tail lines. */
export function meterDisplayText(raw: string): string {
  const cut = raw.indexOf("§METER§");
  return (cut >= 0 ? raw.slice(0, cut) : raw).trim();
}

/** Truncated TEXT payload for on-node display (Preview / STT / Prompt / Meter). */
export function previewTextSnippet(output?: JobOutput, maxLen = 140): string | null {
  // Preview may return AUDIO with an attached `text` transcript field.
  // Meter / MULTI TEXT slots are walked via textFromJobOutput.
  const raw = textFromJobOutput(output);
  if (!raw) return null;
  const display = raw.includes("§METER§") ? meterDisplayText(raw) : raw;
  // Preserve newlines for Meter head/tail lines on canvas.
  if (display.includes("\n")) {
    const clipped = display.length <= maxLen ? display : `${display.slice(0, Math.max(1, maxLen - 1))}…`;
    return clipped.trim() || null;
  }
  return truncatePreviewText(display, maxLen);
}

/** Collapse whitespace and truncate for on-node Prompt / transcript chrome. */
export function truncatePreviewText(text: string, maxLen = 140): string | null {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (!collapsed) return null;
  if (collapsed.length <= maxLen) return collapsed;
  return `${collapsed.slice(0, Math.max(1, maxLen - 1))}…`;
}

/** Live Prompt body for canvas chrome — widget text, not last-render output. */
export function promptWidgetSnippet(node: WorkflowNode, maxLen = 140): string | null {
  if (node.type !== "Prompt") return null;
  const raw = node.widgets.text;
  const text = typeof raw === "string" ? raw : raw == null ? "" : String(raw);
  return truncatePreviewText(text, maxLen);
}

/**
 * Inspector payload: prefer the node's own job output (keeps Preview transcripts)
 * while retaining listen/upstream cache_id for waveform when needed.
 */
export function resolveNodeInspectorOutput(
  direct?: JobOutput,
  listen?: JobOutput,
): JobOutput | undefined {
  // Muxed VIDEO (PreviewVideo / MuxVideo) must keep its path for the HTML5 player.
  if (direct?.type === "VIDEO" && direct.path) {
    return direct;
  }
  if (direct?.text) {
    const cacheId = direct.cache_id ?? listen?.cache_id;
    return {
      ...(listen ?? {}),
      ...direct,
      cache_id: cacheId,
      type: cacheId ? "AUDIO" : direct.type,
      text: direct.text,
    };
  }
  // SaveAudio / SaveVideo: keep the written-file STRING payload (path + optional provenance).
  if (direct?.type === "STRING" && direct.path) {
    return direct;
  }
  // Keep MULTI (SAMPLE_CHECK+AUDIO, AUTHENTICITY+AUDIO, stems, …) so the Outputs
  // tab can render every socket. Audition still uses resolveNodeListenOutput.
  if (direct?.type === "MULTI" && direct.outputs?.length) {
    return direct;
  }
  return listen ?? direct;
}

/** Cache id used for offline preview/listen (audio WAV or synthesized MIDI audition). */
export function previewListenId(output?: JobOutput, slot = 0): string | null {
  const slotOutput = jobOutputAtSlot(output, slot);
  return previewCacheId(slotOutput) ?? previewMidiId(slotOutput);
}

export function savedFilePath(output?: JobOutput): string | null {
  if (output?.type === "STRING" && output.path) return output.path;
  if (output?.type === "TEXT" && output.text && /\.(wav|flac|aiff|mp3|ogg|opus)$/i.test(output.text)) {
    return output.text;
  }
  return null;
}

export function savedProvenancePath(output?: JobOutput): string | null {
  return output?.type === "STRING" && output.provenance_path
    ? output.provenance_path
    : null;
}

/** Join SaveAudio path + filename widgets into a project-relative output path. */
export function joinSaveAudioPath(
  path: unknown,
  filename: unknown,
  format?: unknown,
): string {
  const folder = typeof path === "string" ? path.trim().replace(/^\/+|\/+$/g, "") : "";
  const name = typeof filename === "string" ? filename.trim().replace(/^\/+/, "") : "";
  let file = name || "output.wav";
  if (typeof format === "string" && format.trim()) {
    const extension = format.trim().toLowerCase();
    file = file.replace(/\.[^./]+$/, "");
    file = `${file}.${extension}`;
  }
  if (file.includes("/") && (!folder || folder === "exports")) {
    return file;
  }
  return folder ? `${folder}/${file}` : file;
}

const WIREABLE_INPUT_TYPES = new Set([
  "AUDIO",
  "STEMS",
  "MIDI",
  "TEXT",
  "AUTOMATION",
  "AMBISONICS",
  "OBA",
  "OSC",
  "TRAJECTORY",
  "AUTHENTICITY",
  "SAMPLE_CHECK",
  "VIDEO",
]);

/** Widget-only params — never auto-wired or shown as canvas handles. */
const WIDGET_ONLY_INPUT_TYPES = new Set(["MODEL_REF", "STRING", "INT", "FLOAT", "BOOLEAN", "BOOL"]);

/** Whether an input socket should appear as a canvas handle (optional floats stay in the inspector). */
export function isWireableInput(socket: { type: string; optional?: boolean }): boolean {
  if (WIDGET_ONLY_INPUT_TYPES.has(socket.type)) return false;
  if (!socket.optional) return true;
  return WIREABLE_INPUT_TYPES.has(socket.type);
}

/** Infer minimum socket counts from workflow links when schemas are not loaded yet. */
export function inferNodeSocketCounts(
  workflow: Workflow,
  nodeId: string,
): { inputs: number; outputs: number } {
  let inputs = 0;
  let outputs = 0;
  for (const link of workflow.links) {
    if (link.to[0] === nodeId) {
      inputs = Math.max(inputs, link.to[1] + 1);
    }
    if (link.from[0] === nodeId) {
      outputs = Math.max(outputs, link.from[1] + 1);
    }
  }
  return { inputs, outputs: Math.max(outputs, 1) };
}

function schemaInputSockets(schema: NodeSchema): NodeSocketSpec[] {
  return schema.inputs
    .map((socket, slot) => ({
      name: socket.name,
      type: socket.type,
      optional: socket.optional,
      slot,
    }))
    .filter((socket) => isWireableInput(socket));
}

/** Canvas labels for ChannelConvert: e.g. MONO inlet → STEREO outlet. */
export function channelConvertSocketLabels(
  targetLayout: unknown,
  upstreamChannels: number | null,
): { input: string; output: string } {
  const target = String(targetLayout ?? "mono").trim().toLowerCase() || "mono";
  const output =
    target === "mono"
      ? "MONO"
      : target === "stereo"
        ? "STEREO"
        : target.toUpperCase();

  if (upstreamChannels === 1) {
    return { input: "MONO", output };
  }
  if (upstreamChannels === 2) {
    return { input: "STEREO", output };
  }
  if (upstreamChannels != null && upstreamChannels > 2) {
    return { input: channelLayoutLabel(upstreamChannels).toUpperCase(), output };
  }
  // No upstream probe yet — hint the usual conversion for the target widget.
  if (target === "stereo") return { input: "MONO", output: "STEREO" };
  if (target === "mono") return { input: "STEREO", output: "MONO" };
  return { input: "AUDIO", output };
}

function placeholderInputSockets(count: number): NodeSocketSpec[] {
  return Array.from({ length: count }, (_, slot) => ({
    name: slot === 0 ? "in" : `in_${slot}`,
    type: "AUDIO",
    slot,
  }));
}

function placeholderOutputSockets(count: number): NodeSocketSpec[] {
  return Array.from({ length: count }, (_, slot) => ({
    name: slot === 0 ? "out" : `out_${slot}`,
    type: "AUDIO",
    slot,
  }));
}

/** Hardcoded sockets so TRAJECTORY handles exist even before /api/nodes schemas load. */
const TRAJECTORY_NODE_SOCKET_FALLBACKS: Record<
  string,
  { inputs: NodeSocketSpec[]; outputs: NodeSocketSpec[] }
> = {
  TrajectoryAuthor: {
    inputs: [{ name: "audio", type: "AUDIO", optional: true, slot: 0 }],
    outputs: [{ name: "trajectory", type: "TRAJECTORY", slot: 0 }],
  },
  TrajectoryMonitor: {
    inputs: [{ name: "trajectory", type: "TRAJECTORY", slot: 0 }],
    outputs: [{ name: "trajectory", type: "TRAJECTORY", slot: 0 }],
  },
  AmbisonicUpmix: {
    inputs: [
      { name: "audio", type: "AUDIO", slot: 0 },
      { name: "trajectory", type: "TRAJECTORY", optional: true, slot: 1 },
    ],
    outputs: [{ name: "ambisonics", type: "AMBISONICS", slot: 0 }],
  },
  AmbisonicTrajectoryExtract: {
    inputs: [{ name: "ambisonics", type: "AMBISONICS", slot: 0 }],
    outputs: [{ name: "trajectory", type: "TRAJECTORY", slot: 0 }],
  },
  Meter: {
    inputs: [
      { name: "audio", type: "AUDIO", optional: true, slot: 0 },
      { name: "ambisonics", type: "AMBISONICS", optional: true, slot: 1 },
    ],
    outputs: [
      { name: "audio", type: "AUDIO", slot: 0 },
      { name: "levels", type: "TEXT", slot: 1 },
    ],
  },
};

function fallbackSocketsForNode(
  nodeType: string,
): { inputs: NodeSocketSpec[]; outputs: NodeSocketSpec[] } | null {
  return TRAJECTORY_NODE_SOCKET_FALLBACKS[nodeType] ?? null;
}

/** Preserve React Flow interaction state when syncing derived nodes from workflow. */
export function mergeFlowNodes<T extends Node>(current: T[], next: T[]): T[] {
  // Trust an empty `next` — blank user templates must clear the previous canvas.
  const currentById = new Map(current.map((node) => [node.id, node]));
  const merged: T[] = [];
  const seen = new Set<string>();
  for (const fresh of next) {
    if (seen.has(fresh.id)) continue;
    seen.add(fresh.id);
    const existing = currentById.get(fresh.id);
    if (!existing) {
      merged.push(fresh);
      continue;
    }
    merged.push({
      ...existing,
      data: fresh.data,
      type: fresh.type,
      hidden: fresh.hidden,
      style: fresh.style,
      position: existing.dragging ? existing.position : fresh.position,
    });
  }
  return merged;
}

/** Preserve React Flow interaction state when syncing derived edges from workflow. */
export function mergeFlowEdges<T extends Edge>(current: T[], next: T[]): T[] {
  // Trust empty `next` the same as nodes (blank templates / cleared graphs).
  const merged: T[] = [];
  for (const fresh of next) {
    const existing = current.find((edge) => edge.id === fresh.id);
    if (!existing) {
      merged.push(fresh);
      continue;
    }
    merged.push({
      ...existing,
      source: fresh.source,
      target: fresh.target,
      label: fresh.label,
      className: fresh.className,
      animated: fresh.animated,
      hidden: fresh.hidden,
      style: fresh.style,
      labelStyle: fresh.labelStyle,
      labelBgStyle: fresh.labelBgStyle,
    });
  }
  return merged;
}

export function proxyNodeId(groupId: string): string {
  return `proxy_${groupId}`;
}

/** Ensure optional array fields exist so canvas helpers never iterate undefined. */
export function normalizeLoadedWorkflow(raw: Workflow): Workflow {
  return {
    ...raw,
    nodes: raw.nodes ?? [],
    links: raw.links ?? [],
    groups: raw.groups ?? [],
  };
}

export function collapsedMemberIds(workflow: Workflow): Set<string> {
  const hidden = new Set<string>();
  for (const group of workflow.groups ?? []) {
    if (!group.collapsed) continue;
    for (const nodeId of group.node_ids) {
      hidden.add(nodeId);
    }
  }
  return hidden;
}

export function groupForNode(workflow: Workflow, nodeId: string): WorkflowGroup | null {
  return workflow.groups.find((group) => group.node_ids.includes(nodeId)) ?? null;
}

export function groupForSelection(workflow: Workflow, nodeIds: string[]): WorkflowGroup | null {
  if (nodeIds.length === 0) return null;
  const groups = nodeIds.map((id) => groupForNode(workflow, id)).filter(Boolean) as WorkflowGroup[];
  if (groups.length === 0) return null;
  const first = groups[0];
  return groups.every((group) => group.id === first.id) ? first : null;
}

function groupCentroid(workflow: Workflow, group: WorkflowGroup): { x: number; y: number } {
  const nodes = workflow.nodes.filter((node) => group.node_ids.includes(node.id));
  if (nodes.length === 0) {
    return group.proxy_pos ?? { x: 120, y: 120 };
  }
  const x = nodes.reduce((sum, node) => sum + (node.pos?.x ?? 0), 0) / nodes.length;
  const y = nodes.reduce((sum, node) => sum + (node.pos?.y ?? 0), 0) / nodes.length;
  return { x, y };
}

export function toggleGroupCollapsed(workflow: Workflow, groupId: string): Workflow {
  return {
    ...workflow,
    groups: workflow.groups.map((group) => {
      if (group.id !== groupId) return group;
      const collapsed = !group.collapsed;
      return {
        ...group,
        collapsed,
        proxy_pos: collapsed ? group.proxy_pos ?? groupCentroid(workflow, group) : group.proxy_pos,
      };
    }),
  };
}

export function rewriteLinksForCollapsedGroups(workflow: Workflow): WorkflowLink[] {
  const collapsedGroups = workflow.groups.filter((group) => group.collapsed);
  if (collapsedGroups.length === 0) return workflow.links;

  const memberToGroup = new Map<string, WorkflowGroup>();
  for (const group of collapsedGroups) {
    for (const nodeId of group.node_ids) {
      memberToGroup.set(nodeId, group);
    }
  }

  const rewritten: WorkflowLink[] = [];
  for (const link of workflow.links) {
    const fromId = String(link.from[0]);
    const toId = String(link.to[0]);
    const fromGroup = memberToGroup.get(fromId);
    const toGroup = memberToGroup.get(toId);
    if (fromGroup && toGroup && fromGroup.id === toGroup.id) {
      continue;
    }
    if (fromGroup && !toGroup) {
      rewritten.push({ ...link, from: [proxyNodeId(fromGroup.id), link.from[1]] });
    } else if (!fromGroup && toGroup) {
      rewritten.push({ ...link, to: [proxyNodeId(toGroup.id), link.to[1]] });
    } else if (fromGroup && toGroup && fromGroup.id !== toGroup.id) {
      rewritten.push({
        ...link,
        id: `proxy_${link.id}`,
        from: [proxyNodeId(fromGroup.id), 0],
        to: [proxyNodeId(toGroup.id), 0],
      });
    } else {
      rewritten.push(link);
    }
  }
  return rewritten;
}

/** Map validation errors/warnings onto affected node ids for canvas highlighting. */
export function nodeIssuesFromValidation(
  workflow: Workflow,
  result: WorkflowValidationResult,
): Record<string, string> {
  const issues: Record<string, string> = {};
  const linkById = new Map(workflow.links.map((link) => [link.id, link]));
  const add = (nodeId: string, message: string) => {
    issues[nodeId] = issues[nodeId] ? `${issues[nodeId]} · ${message}` : message;
  };
  for (const item of [...result.errors, ...result.warnings]) {
    if (item.node_id) {
      add(item.node_id, item.message);
      continue;
    }
    if (item.link_id) {
      const edge = linkById.get(item.link_id);
      if (edge) {
        add(String(edge.from[0]), item.message);
        add(String(edge.to[0]), item.message);
      }
    }
  }
  return issues;
}

/** Per-channel outlet labels for LoadAudio (matches runtime MULTI slot order). */
export function channelLayoutLabel(channels: number): string {
  const count = Math.max(0, Math.floor(channels));
  if (count <= 0) return "—";
  if (count === 1) return "mono";
  if (count === 2) return "stereo";
  if (count === 3) return "LRC";
  if (count === 4) return "quad";
  if (count === 6) return "5.1";
  if (count === 8) return "7.1";
  if (count === 12) return "7.1.4";
  return `${count} ch`;
}

export function loadAudioChannelOutletSockets(channelCount: number): NodeSocketSpec[] {
  const count = Math.max(1, Math.floor(channelCount));
  const stereoNames = ["L", "R"];
  return Array.from({ length: count }, (_, slot) => ({
    name: count === 2 ? stereoNames[slot]! : count === 1 ? "mono" : `ch${slot}`,
    type: "AUDIO",
    slot,
  }));
}

/** Channel layout / count chip for LoadAudio, Preview, SaveAudio (and selection lists). */
export function resolveIoChannelLabel(
  workflow: Workflow,
  nodeId: string,
  loadAudioChannels?: Record<string, number>,
  outputs?: Record<string, JobOutput>,
  channelLayouts?: Record<string, string>,
): string | null {
  if (channelLayouts?.[nodeId]) return channelLayouts[nodeId];
  const count = resolveIoChannelCount(workflow, nodeId, loadAudioChannels, outputs);
  if (count == null) return null;
  return channelLayoutLabel(count);
}

const IO_CHANNEL_NODE_TYPES = new Set(["LoadAudio", "Preview", "SaveAudio"]);

/** Best-effort channel count for canvas / selection labels. */
export function resolveIoChannelCount(
  workflow: Workflow,
  nodeId: string,
  loadAudioChannels?: Record<string, number>,
  outputs?: Record<string, JobOutput>,
): number | null {
  const node = workflow.nodes.find((item) => item.id === nodeId);
  if (!node) return null;

  if (node.type === "LoadAudio") {
    const probed = loadAudioChannels?.[nodeId];
    if (typeof probed === "number" && probed > 0) return probed;
    const jobOut = outputs?.[nodeId];
    if (jobOut?.type === "MULTI" && jobOut.outputs?.length) return jobOut.outputs.length;
    // Always show a label — assume mono until the file probe returns.
    return 1;
  }

  const direct = outputs?.[nodeId];
  if (direct?.type === "MULTI" && direct.outputs?.length) return direct.outputs.length;

  if (!IO_CHANNEL_NODE_TYPES.has(node.type)) return null;

  // Preview / SaveAudio: walk upstream toward a known channel count.
  const visited = new Set<string>();
  const queue: string[] = [nodeId];
  while (queue.length) {
    const current = queue.shift()!;
    if (visited.has(current)) continue;
    visited.add(current);

    if (current !== nodeId) {
      const probed = loadAudioChannels?.[current];
      if (typeof probed === "number" && probed > 0) return probed;
      const jobOut = outputs?.[current];
      if (jobOut?.type === "MULTI" && jobOut.outputs?.length) return jobOut.outputs.length;
    }

    for (const link of workflow.links) {
      if (link.to[0] !== current) continue;
      if (link.type !== "AUDIO" && link.type !== "STEMS" && link.type !== "AMBISONICS") continue;
      queue.push(link.from[0]);
    }
  }

  return null;
}

/** Walk AUDIO inlets to find an upstream LoadAudio (for trajectory duration lock). */
export function findUpstreamLoadAudio(
  workflow: Workflow,
  nodeId: string,
): WorkflowNode | null {
  const typeById = new Map(workflow.nodes.map((n) => [n.id, n]));
  const visited = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const current = queue.shift()!;
    if (visited.has(current)) continue;
    visited.add(current);
    const node = typeById.get(current);
    if (!node) continue;
    if (node.type === "LoadAudio") return node;
    for (const link of workflow.links) {
      if (link.to[0] !== current) continue;
      if (link.type !== "AUDIO" && link.type !== "STEMS") continue;
      queue.push(link.from[0]);
    }
  }
  return null;
}

/** Rescale authored trajectory points JSON to a new duration (keeps shape). */
export function rescalePointsWidgetJson(
  pointsRaw: unknown,
  durationSec: number,
): string | null {
  if (typeof pointsRaw !== "string" || !pointsRaw.trim()) return null;
  try {
    const parsed = JSON.parse(pointsRaw) as unknown;
    if (!Array.isArray(parsed) || parsed.length < 2) return null;
    const points: Array<{ t_sec: number; x: number; y: number; z: number }> = [];
    for (const item of parsed) {
      if (!item || typeof item !== "object") continue;
      const row = item as Record<string, unknown>;
      const x = Number(row.x);
      const z = Number(row.z);
      const y = Number(row.y ?? 0);
      const t = Number(row.t_sec ?? row.t ?? NaN);
      if (!Number.isFinite(x) || !Number.isFinite(z)) continue;
      points.push({
        t_sec: Number.isFinite(t) ? Math.max(0, t) : points.length,
        x,
        y: Number.isFinite(y) ? y : 0,
        z,
      });
    }
    if (points.length < 2) return null;
    const span = Math.max(0.05, durationSec);
    const tMax = Math.max(...points.map((p) => p.t_sec), 1e-9);
    const scaled = points.map((p) => ({
      ...p,
      t_sec: (p.t_sec / tMax) * span,
    }));
    return JSON.stringify(scaled);
  } catch {
    return null;
  }
}

/** Walk TRAJECTORY inlets to find an upstream TrajectoryAuthor (for canvas XYZ edit). */
export function findUpstreamTrajectoryAuthor(
  workflow: Workflow,
  nodeId: string,
): WorkflowNode | null {
  const typeById = new Map(workflow.nodes.map((n) => [n.id, n]));
  const visited = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const current = queue.shift()!;
    if (visited.has(current)) continue;
    visited.add(current);
    const node = typeById.get(current);
    if (!node) continue;
    if (node.type === "TrajectoryAuthor") return node;
    for (const link of workflow.links) {
      if (link.to[0] !== current) continue;
      if (link.type !== "TRAJECTORY") continue;
      queue.push(link.from[0]);
    }
  }
  return null;
}

function trajectoryAuthorWidgets(node: WorkflowNode): Record<string, number | string> {
  const pointsRaw = node.widgets.points;
  const points =
    typeof pointsRaw === "string"
      ? pointsRaw
      : pointsRaw == null
        ? ""
        : String(pointsRaw);
  return {
    start_x: Number(node.widgets.start_x ?? 0.707),
    start_y: Number(node.widgets.start_y ?? 0),
    start_z: Number(node.widgets.start_z ?? 0.707),
    end_x: Number(node.widgets.end_x ?? -0.707),
    end_y: Number(node.widgets.end_y ?? 0),
    end_z: Number(node.widgets.end_z ?? 0.707),
    duration_sec: Number(node.widgets.duration_sec ?? 1),
    points,
  };
}

/** TRAJECTORY cache id for a node — prefer its own output, else inbound TRAJECTORY wire. */
export function resolveNodeTrajectoryId(
  workflow: Workflow,
  nodeId: string,
  outputs?: Record<string, JobOutput>,
): string | undefined {
  if (!outputs) return undefined;
  const direct = outputs[nodeId];
  if (direct?.type === "TRAJECTORY" && direct.trajectory_id) return direct.trajectory_id;
  for (const link of workflow.links) {
    if (link.to[0] !== nodeId) continue;
    if (link.type !== "TRAJECTORY") continue;
    const upstream = outputs[link.from[0]];
    if (upstream?.type === "TRAJECTORY" && upstream.trajectory_id) {
      return upstream.trajectory_id;
    }
  }
  return undefined;
}

export function workflowToFlowNodes(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
  schemas?: Record<string, NodeSchema>,
  nodeIssues?: Record<string, string>,
  /** Probed channel counts for LoadAudio nodes (path → channels), keyed by node id. */
  loadAudioChannels?: Record<string, number>,
  /** Optional layout strings from cache metrics (overrides inferred count labels). */
  channelLayouts?: Record<string, string>,
): Node<GroovyNodeData | GroovyGroupNodeData>[] {
  const hidden = collapsedMemberIds(workflow);
  const nodes: Node<GroovyNodeData | GroovyGroupNodeData>[] = workflow.nodes
    .filter((node) => !hidden.has(node.id))
    .map((n: WorkflowNode) => {
      const schema = schemas?.[n.type];
      const linkCounts = inferNodeSocketCounts(workflow, n.id);
      const inputs: NodeSocketSpec[] = (() => {
        if (n.type === "ChannelConvert") {
          const upstreamId = workflow.links.find(
            (link) => link.to[0] === n.id && link.to[1] === 0 && link.type === "AUDIO",
          )?.from[0];
          let resolvedUpstream: number | null =
            upstreamId != null
              ? resolveIoChannelCount(workflow, upstreamId, loadAudioChannels, outputs)
              : null;
          const layoutHint =
            (upstreamId != null ? channelLayouts?.[upstreamId] : undefined)?.toLowerCase() ?? null;
          if (layoutHint === "mono") resolvedUpstream = 1;
          else if (layoutHint === "stereo") resolvedUpstream = 2;
          const labels = channelConvertSocketLabels(n.widgets.layout, resolvedUpstream);
          return [{ name: labels.input, type: "AUDIO", slot: 0 }];
        }
        if (schema) return schemaInputSockets(schema);
        const fallback = fallbackSocketsForNode(n.type);
        if (fallback) return fallback.inputs;
        return linkCounts.inputs > 0 ? placeholderInputSockets(linkCounts.inputs) : [];
      })();
      const jobOut = outputs?.[n.id];
      const outputSockets: NodeSocketSpec[] = (() => {
        if (n.type === "ChannelConvert") {
          const upstreamId = workflow.links.find(
            (link) => link.to[0] === n.id && link.to[1] === 0 && link.type === "AUDIO",
          )?.from[0];
          let resolvedUpstream: number | null =
            upstreamId != null
              ? resolveIoChannelCount(workflow, upstreamId, loadAudioChannels, outputs)
              : null;
          const layoutHint =
            (upstreamId != null ? channelLayouts?.[upstreamId] : undefined)?.toLowerCase() ?? null;
          if (layoutHint === "mono") resolvedUpstream = 1;
          else if (layoutHint === "stereo") resolvedUpstream = 2;
          const labels = channelConvertSocketLabels(n.widgets.layout, resolvedUpstream);
          return [{ name: labels.output, type: "AUDIO", slot: 0 }];
        }
        // LoadAudio exposes one AUDIO outlet per file channel. Prefer a filesystem
        // probe (so handles appear before first render), then MULTI job output,
        // then keep enough sockets for any already-wired outbound slots.
        if (n.type === "LoadAudio") {
          const probed = loadAudioChannels?.[n.id];
          if (typeof probed === "number" && probed > 0) {
            const sockets = loadAudioChannelOutletSockets(probed);
            if (linkCounts.outputs > sockets.length) {
              return loadAudioChannelOutletSockets(linkCounts.outputs);
            }
            return sockets;
          }
          if (jobOut?.type === "MULTI" && jobOut.outputs?.length) {
            return jobOut.outputs.map((slotOut, slot) => ({
              name: slotOut.name ?? `ch${slot}`,
              type: slotOut.type ?? "AUDIO",
              slot,
            }));
          }
          if (linkCounts.outputs > 1) {
            return loadAudioChannelOutletSockets(linkCounts.outputs);
          }
          // Always expose at least a mono outlet label before probe/render.
          return loadAudioChannelOutletSockets(1);
        }
        if (schema) {
          return schema.outputs.map((socket, slot) => ({
            name: socket.name,
            type:
              n.type === "Prompt" || (slot === 0 && (jobOut?.type === "TEXT" || jobOut?.type === "STRING"))
                ? "TEXT"
                : socket.type,
            slot,
          }));
        }
        const fallback = fallbackSocketsForNode(n.type);
        if (fallback) return fallback.outputs;
        return placeholderOutputSockets(linkCounts.outputs);
      })();
      const noteText =
        n.type === "Note"
          ? typeof n.widgets.text === "string"
            ? n.widgets.text
            : String(n.widgets.text ?? "")
          : undefined;
      const channelCount = resolveIoChannelCount(workflow, n.id, loadAudioChannels, outputs);
      const channelLabel = IO_CHANNEL_NODE_TYPES.has(n.type)
        ? channelLayouts?.[n.id] ||
          (channelCount != null ? channelLayoutLabel(channelCount) : "—")
        : undefined;
      const trajectoryRole: "input" | "output" | undefined =
        n.type === "TrajectoryMonitor"
          ? String(n.widgets.role ?? "input").toLowerCase() === "output"
            ? "output"
            : "input"
          : n.type === "TrajectoryAuthor" || jobOut?.type === "TRAJECTORY"
            ? "input"
            : undefined;
      const authorForEdit =
        n.type === "TrajectoryAuthor"
          ? n
          : n.type === "TrajectoryMonitor" && trajectoryRole === "input"
            ? findUpstreamTrajectoryAuthor(workflow, n.id)
            : null;
      const videoPanel =
        n.type === "PreviewVideo" ? previewVideoPanelSize(n, jobOut) : null;
      const videoFootprint = videoPanel ? previewVideoNodeFootprint(videoPanel) : null;
      return {
        id: n.id,
        type: "groovy",
        position: n.pos ?? { x: 0, y: 0 },
        style: videoFootprint
          ? { width: videoFootprint.width, height: videoFootprint.height }
          : undefined,
        data: {
          label: n.type,
          kind: canvasNodeKind(n.type, schema?.category),
          status: nodeStatus[n.id] ?? "idle",
          nodeId: n.id,
          canAudition: nodeHasListenableOutput(workflow, n.id, outputs),
          issue: nodeIssues?.[n.id],
          previewText:
            // Meter levels live in Inspector only — keep canvas light.
            n.type === "Meter"
              ? undefined
              : promptWidgetSnippet(n) ?? previewTextSnippet(jobOut, 140) ?? undefined,
          previewVideoPath:
            n.type === "PreviewVideo" ? previewVideoPath(jobOut) ?? undefined : undefined,
          previewVideoWidth: videoPanel?.width,
          previewVideoHeight: videoPanel?.height,
          previewVideoAspect: videoPanel?.aspect,
          noteText,
          channelLabel,
          trajectoryId: resolveNodeTrajectoryId(workflow, n.id, outputs),
          trajectoryRole,
          trajectoryAuthorId: authorForEdit?.id,
          trajectoryWidgets: authorForEdit ? trajectoryAuthorWidgets(authorForEdit) : undefined,
          inputs,
          outputs: outputSockets,
        },
      };
    });

  for (const group of workflow.groups ?? []) {
    if (!group.collapsed) continue;
    const position = group.proxy_pos ?? groupCentroid(workflow, group);
    nodes.push({
      id: proxyNodeId(group.id),
      type: "groovyGroup",
      position,
      data: {
        label: group.title,
        groupId: group.id,
        nodeCount: group.node_ids.length,
      },
    });
  }

  return nodes;
}

export function workflowToFlowEdges(workflow: Workflow, activeEdgeIds?: Set<string>): Edge[] {
  const links = rewriteLinksForCollapsedGroups(workflow);
  return links.map((l: WorkflowLink) => {
    const typeClass = edgeTypeClass(l.type);
    const active = activeEdgeIds?.has(l.id) ?? false;
    const color = resolveEdgeStroke(l.type, l.color);
    return {
      id: l.id,
      source: l.from[0],
      target: l.to[0],
      sourceHandle: String(l.from[1]),
      targetHandle: String(l.to[1]),
      label: l.type,
      className: [typeClass, active ? "groovy-edge--active" : ""].filter(Boolean).join(" "),
      animated: active,
      style: {
        stroke: color,
        strokeWidth: active ? 3 : 2,
        // CSS vars so type/selected stylesheet rules cannot clobber palette colors.
        ["--edge-stroke" as string]: color,
        ["--edge-stroke-width" as string]: active ? 3 : 2,
        ["--edge-glow" as string]: color,
      },
      selectable: true,
      focusable: true,
      interactionWidth: 36,
      labelStyle: { fill: color, fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: "#151820", fillOpacity: 0.92 },
      labelBgPadding: [4, 3] as [number, number],
      labelBgBorderRadius: 3,
    };
  });
}

export type WiredInputRow = {
  index: number;
  name: string;
  type: string;
  optional?: boolean;
  description?: string;
  connected: boolean;
  sourceNode?: WorkflowNode;
  linkType?: string;
};

/** When a socket is wired, these local widgets are ignored at render. */
const WIRED_TEXT_SUPERSEDES_WIDGET: Record<string, Record<string, string | string[]>> = {
  GenerateAudio: { text: "prompt" },
  Video2Audio: { text: "prompt" },
  MIDIToAudio: { text: "prompt" },
  SingFromMIDI: { lyrics: "text" },
  TTS: { transcript: "text" },
  TrajectoryAuthor: {
    audio: ["duration_sec", "sample_rate"],
  },
  Granulate: {
    grain_ms_curve: "grain_ms",
    hop_ms_curve: "hop_ms",
    pitch_cents_curve: "pitch_cents",
    density_curve: "density",
    width_curve: "width",
  },
};

/** Returns the wired input row that disables a local widget, if any. */
export function wiredInputSupersedesWidget(
  nodeType: string,
  widgetName: string,
  inputRows: WiredInputRow[],
): WiredInputRow | null {
  const map = WIRED_TEXT_SUPERSEDES_WIDGET[nodeType];
  if (!map) return null;
  for (const [inputName, supersededWidget] of Object.entries(map)) {
    const names = Array.isArray(supersededWidget) ? supersededWidget : [supersededWidget];
    if (!names.includes(widgetName)) continue;
    const row = inputRows.find((entry) => entry.name === inputName && entry.connected);
    if (row) return row;
  }
  return null;
}

export function wiredPromptPreview(sourceNode: WorkflowNode | undefined): string | null {
  if (!sourceNode) return null;
  if (sourceNode.type === "Prompt") {
    const text = sourceNode.widgets.text;
    return typeof text === "string" && text.trim() ? text : null;
  }
  const text = sourceNode.widgets.text ?? sourceNode.widgets.prompt ?? sourceNode.widgets.lyrics;
  return typeof text === "string" && text.trim() ? text : null;
}

/** Map schema input sockets to workflow links by slot index. */
export function wiredInputsForNode(
  workflow: Workflow,
  nodeId: string,
  inputs: NodeSchema["inputs"],
): WiredInputRow[] {
  return inputs.map((spec, index) => {
    const link = workflow.links.find((item) => item.to[0] === nodeId && item.to[1] === index);
    const sourceNode = link ? workflow.nodes.find((node) => node.id === link.from[0]) : undefined;
    return {
      index,
      name: spec.name,
      type: spec.type,
      optional: spec.optional,
      description: spec.description,
      connected: Boolean(link),
      sourceNode,
      linkType: link?.type,
    };
  });
}

export type WiredOutputRow = {
  index: number;
  name: string;
  type: string;
  description?: string;
  connected: boolean;
  linkCount: number;
  targetNodeIds: string[];
};

/** Map schema output sockets to outbound workflow links by slot index. */
export function wiredOutputsForNode(
  workflow: Workflow,
  nodeId: string,
  outputs: NodeSchema["outputs"],
): WiredOutputRow[] {
  return outputs.map((spec, index) => {
    const links = workflow.links.filter((item) => item.from[0] === nodeId && item.from[1] === index);
    return {
      index,
      name: spec.name,
      type: spec.type,
      description: spec.description,
      connected: links.length > 0,
      linkCount: links.length,
      targetNodeIds: links.map((link) => String(link.to[0])),
    };
  });
}

/** Links that land on a node's input slot. */
export function linksForInputPort(workflow: Workflow, nodeId: string, slot: number): WorkflowLink[] {
  return workflow.links.filter((link) => link.to[0] === nodeId && link.to[1] === slot);
}

/** Links that leave a node's output slot. */
export function linksForOutputPort(workflow: Workflow, nodeId: string, slot: number): WorkflowLink[] {
  return workflow.links.filter((link) => link.from[0] === nodeId && link.from[1] === slot);
}

/** Disconnect every wire on one input or output slot (Inspector Subgraph checkboxes). */
export function disconnectPort(
  workflow: Workflow,
  nodeId: string,
  direction: "in" | "out",
  slot: number,
): Workflow {
  const doomed =
    direction === "in"
      ? new Set(linksForInputPort(workflow, nodeId, slot).map((link) => link.id))
      : new Set(linksForOutputPort(workflow, nodeId, slot).map((link) => link.id));
  if (doomed.size === 0) return workflow;
  return removeLinks(workflow, doomed);
}

export function flowNodesSyncKey(nodes: Node[]): string {
  return nodes
    .map(
      (node) =>
        `${node.id}:${node.type}:${node.hidden ? 1 : 0}:${node.position.x},${node.position.y}:${JSON.stringify(node.data)}`,
    )
    .join("|");
}

export function flowEdgesSyncKey(edges: Edge[]): string {
  return edges
    .map((edge) => {
      const stroke = typeof edge.style?.stroke === "string" ? edge.style.stroke : "";
      return `${edge.id}:${edge.source}->${edge.target}:${edge.className ?? ""}:${edge.animated ? 1 : 0}:${stroke}`;
    })
    .join("|");
}

/** Update optional link stroke color (palette hex or clear). */
export function setLinkColor(workflow: Workflow, linkId: string, color: string | null): Workflow {
  const normalized = color ? normalizeEdgeColor(color) : null;
  return {
    ...workflow,
    links: workflow.links.map((link) => {
      if (link.id !== linkId) return link;
      if (!normalized) {
        const next = { ...link };
        delete next.color;
        return next;
      }
      return { ...link, color: normalized };
    }),
  };
}

export function workflowToFlow(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
  activeEdgeIds?: Set<string>,
): { nodes: Node<GroovyNodeData | GroovyGroupNodeData>[]; edges: Edge[] } {
  return {
    nodes: workflowToFlowNodes(workflow, nodeStatus, outputs),
    edges: workflowToFlowEdges(workflow, activeEdgeIds),
  };
}

export function syncPositions(workflow: Workflow, nodes: Node[]): Workflow {
  const hidden = collapsedMemberIds(workflow);
  const posById = new Map(nodes.map((n) => [n.id, n.position]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node: WorkflowNode) => {
      if (hidden.has(node.id)) return node;
      const pos = posById.get(node.id);
      return pos ? { ...node, pos: { x: pos.x, y: pos.y } } : node;
    }),
    groups: workflow.groups.map((group) => {
      if (!group.collapsed) return group;
      const proxyId = proxyNodeId(group.id);
      const pos = posById.get(proxyId);
      return pos ? { ...group, proxy_pos: { x: pos.x, y: pos.y } } : group;
    }),
  };
}

export function topologicalNodeOrder(workflow: Workflow): string[] {
  const indegree = new Map(workflow.nodes.map((node) => [node.id, 0]));
  const adjacency = new Map(workflow.nodes.map((node) => [node.id, [] as string[]]));
  for (const link of workflow.links) {
    const source = link.from[0];
    const target = link.to[0];
    indegree.set(target, (indegree.get(target) ?? 0) + 1);
    adjacency.get(source)?.push(target);
  }
  const queue = workflow.nodes
    .filter((node) => (indegree.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const order: string[] = [];
  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    order.push(nodeId);
    for (const nextId of adjacency.get(nodeId) ?? []) {
      indegree.set(nextId, (indegree.get(nextId) ?? 1) - 1);
      if (indegree.get(nextId) === 0) {
        queue.push(nextId);
      }
    }
  }
  return order;
}

function listenCacheId(
  workflow: Workflow,
  nodeId: string,
  outputs: Record<string, JobOutput>,
): string | null {
  return resolveNodeListenId(workflow, nodeId, outputs);
}

function hopDiffers(
  workflow: Workflow,
  nodeA: string,
  nodeB: string,
  outputs: Record<string, JobOutput>,
): [string, string] | null {
  const cacheA = listenCacheId(workflow, nodeA, outputs);
  const cacheB = listenCacheId(workflow, nodeB, outputs);
  if (cacheA && cacheB && cacheA !== cacheB) {
    return [nodeA, nodeB];
  }
  return null;
}

function findDistinctHop(
  workflow: Workflow,
  order: string[],
  outputs: Record<string, JobOutput>,
  selectedA: string,
  selectedB: string,
): [string, string] | null {
  const indexA = order.indexOf(selectedA);
  const indexB = order.indexOf(selectedB);
  if (indexA < 0 || indexB < 0) return null;
  const lo = Math.min(indexA, indexB);
  const hi = Math.max(indexA, indexB);

  for (let index = hi - 1; index >= lo; index--) {
    const hop = hopDiffers(workflow, order[index], order[index + 1], outputs);
    if (hop) return hop;
  }
  for (let index = lo; index > 0; index--) {
    const hop = hopDiffers(workflow, order[index - 1], order[index], outputs);
    if (hop) return hop;
  }
  for (let index = order.length - 2; index >= 0; index--) {
    const left = order[index];
    const right = order[index + 1];
    if (
      (left === selectedA || left === selectedB || right === selectedA || right === selectedB) &&
      hopDiffers(workflow, left, right, outputs)
    ) {
      return hopDiffers(workflow, left, right, outputs);
    }
  }
  return null;
}

export type CompareHop = {
  a: string;
  b: string;
  label: string;
};

export type CompareResolution = {
  pair: Array<{ node: WorkflowNode; output: JobOutput }>;
  note: string | null;
  missingRender: boolean;
};

export function listDistinctChainHops(
  workflow: Workflow,
  outputs?: Record<string, JobOutput>,
): CompareHop[] {
  if (!outputs) return [];
  const order = topologicalNodeOrder(workflow);
  const hops: CompareHop[] = [];
  for (let index = 0; index < order.length - 1; index++) {
    const nodeA = order[index];
    const nodeB = order[index + 1];
    if (!hopDiffers(workflow, nodeA, nodeB, outputs)) continue;
    const left = workflow.nodes.find((node) => node.id === nodeA);
    const right = workflow.nodes.find((node) => node.id === nodeB);
    hops.push({
      a: nodeA,
      b: nodeB,
      label: `${left?.type ?? nodeA} → ${right?.type ?? nodeB}`,
    });
  }
  return hops;
}

export function resolveComparePair(
  workflow: Workflow,
  outputs: Record<string, JobOutput> | undefined,
  selectedIds: string[],
): CompareResolution | null {
  if (!outputs || selectedIds.length !== 2) return null;
  const [firstId, secondId] = selectedIds;
  const nodeA = workflow.nodes.find((node) => node.id === firstId);
  const nodeB = workflow.nodes.find((node) => node.id === secondId);
  if (!nodeA || !nodeB) return null;

  const outputA = resolveNodeListenOutput(workflow, firstId, outputs);
  const outputB = resolveNodeListenOutput(workflow, secondId, outputs);
  if (!outputA?.cache_id || !outputB?.cache_id) {
    return {
      pair: [],
      note: "Render the workflow first (Play or Shift+R) so both nodes have cached audio.",
      missingRender: true,
    };
  }

  if (outputA.cache_id !== outputB.cache_id) {
    return {
      pair: [
        { node: nodeA, output: outputA },
        { node: nodeB, output: outputB },
      ],
      note: null,
      missingRender: false,
    };
  }

  const order = topologicalNodeOrder(workflow);
  const hop = findDistinctHop(workflow, order, outputs, firstId, secondId);
  if (hop) {
    const [hopA, hopB] = hop;
    const hopNodeA = workflow.nodes.find((node) => node.id === hopA);
    const hopNodeB = workflow.nodes.find((node) => node.id === hopB);
    const hopOutputA = resolveNodeListenOutput(workflow, hopA, outputs);
    const hopOutputB = resolveNodeListenOutput(workflow, hopB, outputs);
    if (!hopNodeA || !hopNodeB || !hopOutputA?.cache_id || !hopOutputB?.cache_id) {
      return null;
    }
    return {
      pair: [
        { node: hopNodeA, output: hopOutputA },
        { node: hopNodeB, output: hopOutputB },
      ],
      note:
        `${nodeA.type} (${firstId}) and ${nodeB.type} (${secondId}) share the same cached audio. ` +
        `Comparing ${hopNodeA.type} (${hopA}) → ${hopNodeB.type} (${hopB}) instead.`,
      missingRender: false,
    };
  }

  return {
    pair: [
      { node: nodeA, output: outputA },
      { node: nodeB, output: outputB },
    ],
    note:
      "Both selections share the same cached audio. Use a chain hop below (e.g. LoadAudio → Denoise).",
    missingRender: false,
  };
}

export function resolveTargetNode(workflow: Workflow, selectedId: string | null): string {
  if (selectedId?.startsWith("proxy_")) {
    const groupId = selectedId.slice("proxy_".length);
    const group = workflow.groups.find((item) => item.id === groupId);
    if (group && group.node_ids.length > 0) {
      return group.node_ids[group.node_ids.length - 1];
    }
  }
  if (selectedId) {
    return selectedId;
  }
  const preview = workflow.nodes.find((n: WorkflowNode) => n.type === "Preview");
  if (preview) {
    return preview.id;
  }
  return workflow.nodes[workflow.nodes.length - 1]?.id ?? "";
}

/** Keep VerifyProvenance / AuthenticitySummary in the job so Compliance is not ML-only. */
export function withAuthenticityRenderTargets(workflow: Workflow, targets: string[]): string[] {
  const summaries = workflow.nodes
    .filter((node) => node.type === "AuthenticitySummary")
    .map((node) => node.id);
  const extra = summaries.length
    ? summaries
    : workflow.nodes.filter((node) => node.type === "VerifyProvenance").map((node) => node.id);
  if (!extra.length) return targets;
  return [...new Set([...targets, ...extra])];
}

/** Terminal nodes (no outgoing edges) — render-all executes each chain to its sink. */
export function resolveRenderAllTargets(workflow: Workflow): string[] {
  const sources = new Set(workflow.links.map((link) => link.from[0]));
  const terminals = workflow.nodes.filter((node) => !sources.has(node.id)).map((node) => node.id);
  if (terminals.length > 0) return terminals;

  const sinks = workflow.nodes
    .filter((node) => node.type === "Preview" || node.type === "SaveAudio")
    .map((node) => node.id);
  if (sinks.length > 0) return sinks;

  return workflow.nodes.map((node) => node.id);
}

export function downloadWorkflow(workflow: Workflow): void {
  const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${workflow.metadata.title.toLowerCase().replace(/\s+/g, "-")}.groovy.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function extractModule(workflow: Workflow, nodeIds: string[]): WorkflowModule {
  const selected = new Set(nodeIds);
  const nodes = workflow.nodes.filter((node) => selected.has(node.id));
  const links = workflow.links.filter(
    (link) => selected.has(link.from[0]) && selected.has(link.to[0]),
  );

  const explicitInlets = nodes
    .filter((node) => node.type === "ModuleInlet")
    .map((node, index) => ({
      id: `in_${node.id}`,
      name: String(node.widgets.name ?? `in${index + 1}`),
      type: String(node.widgets.socket_type ?? "AUDIO"),
      node_id: node.id,
      slot: 0,
      direction: "in" as const,
    }));
  const explicitOutlets = nodes
    .filter((node) => node.type === "ModuleOutlet")
    .map((node, index) => ({
      id: `out_${node.id}`,
      name: String(node.widgets.name ?? `out${index + 1}`),
      type: "AUDIO",
      node_id: node.id,
      slot: 0,
      direction: "out" as const,
    }));

  const boundaryInlets = workflow.links
    .filter((link) => selected.has(link.to[0]) && !selected.has(link.from[0]))
    .map((link, index) => ({
      id: `boundary_in_${link.id}`,
      name: `in${index + 1}`,
      type: link.type,
      node_id: String(link.to[0]),
      slot: Number(link.to[1]),
      direction: "in" as const,
    }));
  const boundaryOutlets = workflow.links
    .filter((link) => selected.has(link.from[0]) && !selected.has(link.to[0]))
    .map((link, index) => ({
      id: `boundary_out_${link.id}`,
      name: `out${index + 1}`,
      type: link.type,
      node_id: String(link.from[0]),
      slot: Number(link.from[1]),
      direction: "out" as const,
    }));

  const inlets = explicitInlets.length > 0 ? explicitInlets : boundaryInlets;
  const outlets = explicitOutlets.length > 0 ? explicitOutlets : boundaryOutlets;

  return {
    schema_version: workflow.schema_version,
    metadata: {
      title: `${workflow.metadata.title} module`,
      description: `Extracted module (${nodes.length} nodes; ${inlets.length} in, ${outlets.length} out)`,
    },
    nodes,
    links,
    inlets,
    outlets,
  };
}

export function downloadModule(module: WorkflowModule): void {
  const blob = new Blob([JSON.stringify(module, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${module.metadata.title.toLowerCase().replace(/\s+/g, "-")}.module.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function createGroup(workflow: Workflow, nodeIds: string[], title: string): Workflow {
  const group = {
    id: `g_${Date.now()}`,
    title,
    node_ids: [...nodeIds],
    color: "#ff002b",
    collapsed: false,
  };
  return {
    ...workflow,
    groups: [...workflow.groups, group],
  };
}

export function importModule(
  workflow: Workflow,
  module: WorkflowModule,
  anchor: { x: number; y: number } = { x: 80, y: 80 },
): Workflow {
  const prefix = `m${Date.now()}`;
  const idMap = new Map(module.nodes.map((node) => [node.id, `${prefix}_${node.id}`]));
  const xs = module.nodes.map((node) => node.pos?.x ?? 0);
  const ys = module.nodes.map((node) => node.pos?.y ?? 0);
  const minX = xs.length ? Math.min(...xs) : 0;
  const minY = ys.length ? Math.min(...ys) : 0;
  const newNodes = module.nodes.map((node) => ({
    ...node,
    id: idMap.get(node.id)!,
    pos: {
      x: (node.pos?.x ?? 0) - minX + anchor.x,
      y: (node.pos?.y ?? 0) - minY + anchor.y,
    },
  }));
  const newLinks = module.links.map((link) => ({
    ...link,
    id: `${prefix}_${link.id}`,
    from: [idMap.get(String(link.from[0]))!, link.from[1]] as [string, number],
    to: [idMap.get(String(link.to[0]))!, link.to[1]] as [string, number],
  }));
  return {
    ...workflow,
    nodes: [...workflow.nodes, ...newNodes],
    links: [...workflow.links, ...newLinks],
  };
}

export function connectNodes(
  workflow: Workflow,
  connection: { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null },
  schemas: Record<string, NodeSchema>,
): Workflow {
  const sourceSlot = Number.parseInt(connection.sourceHandle ?? "0", 10);
  const targetSlot = Number.parseInt(connection.targetHandle ?? "0", 10);
  const sourceNode = workflow.nodes.find((node) => node.id === connection.source);
  const targetNode = workflow.nodes.find((node) => node.id === connection.target);
  const targetSchema = targetNode ? schemas[targetNode.type] : undefined;
  const sourceSchema = sourceNode ? schemas[sourceNode.type] : undefined;
  const fallbackTarget = targetNode ? fallbackSocketsForNode(targetNode.type) : null;
  const fallbackSource = sourceNode ? fallbackSocketsForNode(sourceNode.type) : null;
  const linkType =
    targetSchema?.inputs[targetSlot]?.type ??
    fallbackTarget?.inputs.find((socket) => socket.slot === targetSlot)?.type ??
    sourceSchema?.outputs[sourceSlot]?.type ??
    fallbackSource?.outputs.find((socket) => socket.slot === sourceSlot)?.type ??
    "AUDIO";

  const links = workflow.links.filter(
    (link) => !(link.to[0] === connection.target && link.to[1] === targetSlot),
  );
  const link: WorkflowLink = {
    id: `l_${connection.source}_${connection.target}_${targetSlot}_${Date.now()}`,
    from: [connection.source, sourceSlot],
    to: [connection.target, targetSlot],
    type: linkType,
  };
  return { ...workflow, links: [...links, link] };
}

export function addLink(workflow: Workflow, sourceId: string, targetId: string, type = "AUDIO"): Workflow {
  const link: WorkflowLink = {
    id: `l_${sourceId}_${targetId}_${Date.now()}`,
    from: [sourceId, 0],
    to: [targetId, 0],
    type,
  };
  return { ...workflow, links: [...workflow.links, link] };
}

export function removeLinks(workflow: Workflow, linkIds: Set<string>): Workflow {
  return { ...workflow, links: workflow.links.filter((link) => !linkIds.has(link.id)) };
}

export type WorkflowClipboard = {
  nodes: WorkflowNode[];
  links: WorkflowLink[];
};

/** Collect workflow nodes + internal links for copy/paste (skips collapsed group proxies). */
export function extractSelection(workflow: Workflow, nodeIds: string[]): WorkflowClipboard {
  const selected = new Set(nodeIds.filter((id) => !id.startsWith("proxy_")));
  return {
    nodes: workflow.nodes.filter((node) => selected.has(node.id)).map((node) => structuredClone(node)),
    links: workflow.links
      .filter((link) => selected.has(String(link.from[0])) && selected.has(String(link.to[0])))
      .map((link) => structuredClone(link)),
  };
}

/** Paste a clipboard slice; returns new node ids for selection focus. */
export function pasteSelection(
  workflow: Workflow,
  clip: WorkflowClipboard,
  offset: { x: number; y: number } = { x: 48, y: 48 },
): { workflow: Workflow; newNodeIds: string[] } {
  if (clip.nodes.length === 0) {
    return { workflow, newNodeIds: [] };
  }
  const prefix = `p${Date.now()}`;
  const idMap = new Map(clip.nodes.map((node) => [node.id, `${prefix}_${node.id}`]));
  const newNodes = clip.nodes.map((node) => ({
    ...node,
    id: idMap.get(node.id)!,
    pos: {
      x: (node.pos?.x ?? 0) + offset.x,
      y: (node.pos?.y ?? 0) + offset.y,
    },
  }));
  const newLinks = clip.links.map((link) => ({
    ...link,
    id: `${prefix}_${link.id}`,
    from: [idMap.get(String(link.from[0]))!, link.from[1]] as [string, number],
    to: [idMap.get(String(link.to[0]))!, link.to[1]] as [string, number],
  }));
  return {
    workflow: {
      ...workflow,
      nodes: [...workflow.nodes, ...newNodes],
      links: [...workflow.links, ...newLinks],
    },
    newNodeIds: newNodes.map((node) => node.id),
  };
}

/** Duplicate an on-canvas selection in place (same as copy + paste once). */
export function duplicateSelection(
  workflow: Workflow,
  nodeIds: string[],
  offset: { x: number; y: number } = { x: 48, y: 48 },
): { workflow: Workflow; newNodeIds: string[] } {
  return pasteSelection(workflow, extractSelection(workflow, nodeIds), offset);
}

export function removeNodesFromWorkflow(workflow: Workflow, rawIds: Set<string>): Workflow {
  const nodeIds = new Set<string>();
  for (const id of rawIds) {
    if (id.startsWith("proxy_")) {
      const groupId = id.slice("proxy_".length);
      const group = workflow.groups.find((item) => item.id === groupId);
      if (group) {
        for (const memberId of group.node_ids) nodeIds.add(memberId);
      }
      continue;
    }
    nodeIds.add(id);
  }

  const groups = workflow.groups
    .filter((group) => !rawIds.has(proxyNodeId(group.id)))
    .map((group) => ({
      ...group,
      node_ids: group.node_ids.filter((id) => !nodeIds.has(id)),
    }))
    .filter((group) => group.node_ids.length > 0)
    .filter((group) => group.node_ids.length >= 2);

  return {
    ...workflow,
    nodes: workflow.nodes.filter((node) => !nodeIds.has(node.id)),
    links: workflow.links.filter(
      (link) => !nodeIds.has(String(link.from[0])) && !nodeIds.has(String(link.to[0])),
    ),
    groups,
  };
}

export function collectModelRefs(workflow: Workflow): string[] {
  const ids = new Set<string>();
  for (const node of workflow.nodes) {
    const model = node.widgets.model;
    if (typeof model === "string" && model) {
      ids.add(model);
    }
  }
  return [...ids];
}

const DEFAULT_NODE_SIZE = { width: 200, height: 88 };
/** Extra space between laid-out nodes (visual chrome + handles bleed past estimates). */
const NODE_PLACEMENT_GAP = 72;
/** Treat near-miss rectangles as overlapping so ensure/layout is more aggressive. */
const OVERLAP_MARGIN = 40;

type Rect = { x: number; y: number; w: number; h: number };

function rectsOverlap(a: Rect, b: Rect, margin = 0): boolean {
  return (
    a.x < b.x + b.w + margin &&
    a.x + a.w + margin > b.x &&
    a.y < b.y + b.h + margin &&
    a.y + a.h + margin > b.y
  );
}

/** Conservative canvas footprint for collision / auto-layout (visual node chrome). */
export function estimateNodeSize(node: WorkflowNode): { width: number; height: number } {
  let width = DEFAULT_NODE_SIZE.width;
  let height = DEFAULT_NODE_SIZE.height;
  switch (node.type) {
    case "Note":
      width = 260;
      height = 160;
      break;
    case "TrajectoryMonitor":
      // Node chrome + ~160–200px XYZ pad + labels.
      width = 260;
      height = 320;
      break;
    case "TrajectoryAuthor":
      width = 260;
      height = 300;
      break;
    case "AmbisonicUpmix":
    case "AmbisonicTrajectoryExtract":
    case "AmbisonicEncode":
    case "AmbisonicDecode":
      width = 230;
      height = 120;
      break;
    case "Meter":
      width = 220;
      height = 110;
      break;
    case "SeparateStems":
      width = 220;
      height = 120;
      break;
    case "MatrixMixer":
      width = 220;
      height = 140;
      break;
    case "PreviewVideo": {
      const panel = previewVideoPanelSize(node);
      const footprint = previewVideoNodeFootprint(panel);
      width = footprint.width;
      height = footprint.height;
      break;
    }
    case "Prompt":
    case "GenerateAudio":
    case "Video2Audio":
    case "TTS":
    case "SingFromMIDI":
      width = 210;
      height = 100;
      break;
    case "DiarizeTranscribe":
    case "WhisperSTT":
      height = 96;
      break;
    case "ControlCurve":
    case "SignalGenerator":
    case "Oscillator":
    case "NoiseGenerator":
    case "Envelope":
    case "LFO":
    case "Clock":
    case "BeatTrack":
    case "Float":
      height = 100;
      break;
    default:
      break;
  }
  return { width, height };
}

function nodeRect(node: WorkflowNode, size?: { width: number; height: number }): Rect {
  const footprint = size ?? estimateNodeSize(node);
  return {
    x: node.pos?.x ?? 0,
    y: node.pos?.y ?? 0,
    w: footprint.width,
    h: footprint.height,
  };
}

export function workflowHasOverlappingNodes(workflow: Workflow): boolean {
  const rects = workflow.nodes.map((node) => nodeRect(node));
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      if (rectsOverlap(rects[i], rects[j], OVERLAP_MARGIN)) return true;
    }
  }
  return false;
}

/** Find top-left position near viewport center without overlapping existing nodes. */
export function findOpenNodePosition(
  workflow: Workflow,
  center: { x: number; y: number },
  size: { width: number; height: number } = DEFAULT_NODE_SIZE,
): { x: number; y: number } {
  const obstacles = workflow.nodes.map((node) => nodeRect(node));
  const stepX = size.width + NODE_PLACEMENT_GAP;
  const stepY = size.height + NODE_PLACEMENT_GAP;
  const offsets: Array<{ dx: number; dy: number }> = [{ dx: 0, dy: 0 }];

  for (let ring = 1; ring < 24; ring++) {
    for (let dy = -ring; dy <= ring; dy++) {
      for (let dx = -ring; dx <= ring; dx++) {
        if (Math.abs(dx) === ring || Math.abs(dy) === ring) {
          offsets.push({ dx, dy });
        }
      }
    }
  }

  for (const { dx, dy } of offsets) {
    const x = center.x - size.width / 2 + dx * stepX;
    const y = center.y - size.height / 2 + dy * stepY;
    const candidate = { x, y, w: size.width, h: size.height };
    if (!obstacles.some((obstacle) => rectsOverlap(candidate, obstacle, OVERLAP_MARGIN))) {
      return { x, y };
    }
  }

  return {
    x: center.x - size.width / 2,
    y: center.y - size.height / 2 + workflow.nodes.length * (size.height + NODE_PLACEMENT_GAP),
  };
}

/**
 * Left-to-right DAG layout so no node rectangles overlap.
 * Stable within a layer (previous y, then id).
 */
export function layoutWorkflowNodes(workflow: Workflow): Workflow {
  if (workflow.nodes.length === 0) return workflow;

  const layer = new Map<string, number>();
  for (const node of workflow.nodes) layer.set(node.id, 0);

  let changed = true;
  let guard = 0;
  while (changed && guard < workflow.nodes.length + 2) {
    changed = false;
    guard += 1;
    for (const link of workflow.links) {
      const fromId = link.from[0];
      const toId = link.to[0];
      if (!layer.has(fromId) || !layer.has(toId)) continue;
      const next = (layer.get(fromId) ?? 0) + 1;
      if (next > (layer.get(toId) ?? 0)) {
        layer.set(toId, next);
        changed = true;
      }
    }
  }

  const byLayer = new Map<number, WorkflowNode[]>();
  for (const node of workflow.nodes) {
    const depth = layer.get(node.id) ?? 0;
    const bucket = byLayer.get(depth) ?? [];
    bucket.push(node);
    byLayer.set(depth, bucket);
  }
  for (const bucket of byLayer.values()) {
    bucket.sort((a, b) => (a.pos?.y ?? 0) - (b.pos?.y ?? 0) || a.id.localeCompare(b.id));
  }

  const positions = new Map<string, { x: number; y: number }>();
  let cursorX = 0;
  const maxLayer = Math.max(0, ...byLayer.keys());
  for (let depth = 0; depth <= maxLayer; depth++) {
    const column = byLayer.get(depth) ?? [];
    let cursorY = 0;
    let columnWidth = DEFAULT_NODE_SIZE.width;
    for (const node of column) {
      const size = estimateNodeSize(node);
      columnWidth = Math.max(columnWidth, size.width);
      positions.set(node.id, { x: cursorX, y: cursorY });
      cursorY += size.height + NODE_PLACEMENT_GAP;
    }
    cursorX += columnWidth + NODE_PLACEMENT_GAP;
  }

  return {
    ...workflow,
    nodes: workflow.nodes.map((node) => ({
      ...node,
      pos: positions.get(node.id) ?? node.pos ?? { x: 0, y: 0 },
    })),
  };
}

/** Relayout when node rectangles already overlap (imports / applied graphs). */
export function ensureNoOverlappingNodes(workflow: Workflow): Workflow {
  if (workflow.nodes.length < 2) return workflow;
  if (!workflowHasOverlappingNodes(workflow)) return workflow;
  return layoutWorkflowNodes(workflow);
}

export function nextWorkflowNodeId(workflow: Workflow): string {
  let max = 0;
  for (const node of workflow.nodes) {
    const match = /^n(\d+)$/.exec(node.id);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `n${max + 1}`;
}

/** Map patch-local node ids to workflow-unique ids (never collides with existing nodes). */
export function allocatePatchNodeIdMap(
  workflow: Workflow,
  patchWorkflow: Workflow,
): Map<string, string> {
  const taken = new Set(workflow.nodes.map((node) => node.id));
  const idMap = new Map<string, string>();
  let seq = 0;
  for (const node of patchWorkflow.nodes) {
    let candidate: string;
    do {
      seq += 1;
      candidate = `ex${Date.now().toString(36)}${seq.toString(36)}_${node.id}`;
    } while (taken.has(candidate));
    taken.add(candidate);
    idMap.set(node.id, candidate);
  }
  return idMap;
}

export function addNodeToWorkflow(
  workflow: Workflow,
  nodeType: string,
  widgets: Record<string, unknown>,
  center?: { x: number; y: number },
): { workflow: Workflow; nodeId: string } {
  const id = nextWorkflowNodeId(workflow);
  const anchor = center ?? { x: 320, y: 200 };
  const pos = findOpenNodePosition(workflow, anchor);
  return {
    nodeId: id,
    workflow: {
      ...workflow,
      nodes: [
        ...workflow.nodes,
        { id, type: nodeType, pos, widgets },
      ],
    },
  };
}

export function formatJobError(error: string | null | undefined): string {
  if (!error) return "unknown error";
  const fileNotFound = error.match(/FILE_NOT_FOUND:[^\n]*/);
  if (fileNotFound) {
    return fileNotFound[0].replace(/\s+/g, " ").trim();
  }
  const unsupported = error.match(/UNSUPPORTED_FORMAT:[^\n]*/);
  if (unsupported) {
    return unsupported[0].replace(/\s+/g, " ").trim();
  }
  const runtime = error.match(/RuntimeError:\s*(.+)/s);
  if (runtime?.[1]?.trim() && runtime[1].trim() !== "runtime.") {
    return runtime[1].trim();
  }
  const importErr = error.match(
    /(?:ImportError|ModuleNotFoundError):(?:[^\n]|\n(?!Traceback|  File ))+/,
  );
  if (importErr) {
    return importErr[0].replace(/\s+/g, " ").trim();
  }
  const lines = error.trim().split("\n").map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (line.startsWith("Traceback") || line.startsWith("File ")) continue;
    if (line === "runtime." || line === "runtime" || line === "ImportError:") continue;
    if (line.length > 12) return line;
  }
  return lines[lines.length - 1] ?? error;
}

export function setLoadAudioPath(workflow: Workflow, nodeId: string, path: string): Workflow {
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) =>
      node.id === nodeId ? { ...node, widgets: { ...node.widgets, path } } : node,
    ),
  };
}

export function applyDroppedAudio(workflow: Workflow, path: string): Workflow {
  const loadNode = workflow.nodes.find((node) => node.type === "LoadAudio");
  if (loadNode) {
    return setLoadAudioPath(workflow, loadNode.id, path);
  }
  const id = nextWorkflowNodeId(workflow);
  return {
    ...workflow,
    nodes: [
      { id, type: "LoadAudio", pos: { x: 40, y: 80 }, widgets: { path } },
      ...workflow.nodes,
    ],
  };
}

export function edgeIdsOnPathToNode(workflow: Workflow, targetNodeId: string): Set<string> {
  const upstream = new Map<string, string[]>();
  for (const link of rewriteLinksForCollapsedGroups(workflow)) {
    const dst = String(link.to[0]);
    const src = String(link.from[0]);
    const list = upstream.get(dst) ?? [];
    list.push(src);
    upstream.set(dst, list);
  }
  const onPath = new Set<string>([targetNodeId]);
  const queue = [targetNodeId];
  while (queue.length > 0) {
    const nodeId = queue.pop()!;
    for (const src of upstream.get(nodeId) ?? []) {
      if (!onPath.has(src)) {
        onPath.add(src);
        queue.push(src);
      }
    }
  }
  return new Set(
    rewriteLinksForCollapsedGroups(workflow)
      .filter((link) => onPath.has(String(link.from[0])) && onPath.has(String(link.to[0])))
      .map((link) => link.id),
  );
}

export function downloadTemplateJson(template: Workflow, filename: string): void {
  const blob = new Blob([JSON.stringify(template, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
