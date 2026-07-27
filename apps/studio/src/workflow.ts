import type { Edge, Node } from "@xyflow/react";
import type { JobOutput, NodeRenderStatus, NodeSchema, Workflow, WorkflowGroup, WorkflowLink, WorkflowModule, WorkflowNode, WorkflowValidationResult } from "./types";
import type { GroovyGroupNodeData } from "./components/ModuleGroupNode";
import type { GroovyNodeData, NodeSocketSpec } from "./components/GroovyFlowNode";
import { edgeTypeClass, socketTypeColor } from "./socketTypes";

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

  const direct = outputs[nodeId];
  if (previewListenId(direct, 0)) {
    return jobOutputAtSlot(direct, 0);
  }

  if (direct?.type === "MULTI") {
    const slot = previewOutputSlot(workflow, nodeId);
    const slotOutput = jobOutputAtSlot(direct, slot);
    if (slotOutput && previewListenId(slotOutput, 0)) return slotOutput;
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
      out?.type === "STRING"
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

export function previewMidiId(output?: JobOutput): string | null {
  if (output?.type === "MIDI" && output.midi_id) return output.midi_id;
  if (output?.midi_id && !output.cache_id) return output.midi_id;
  return null;
}

/** Truncated TEXT payload for on-node display (Preview / STT / Prompt). */
export function previewTextSnippet(output?: JobOutput, maxLen = 140): string | null {
  // Preview may return AUDIO with an attached `text` transcript field.
  const raw = typeof output?.text === "string" ? output.text.trim() : "";
  if (!raw) return null;
  const collapsed = raw.replace(/\s+/g, " ");
  if (collapsed.length <= maxLen) return collapsed;
  return `${collapsed.slice(0, Math.max(1, maxLen - 1))}…`;
}

/**
 * Inspector payload: prefer the node's own job output (keeps Preview transcripts)
 * while retaining listen/upstream cache_id for waveform when needed.
 */
export function resolveNodeInspectorOutput(
  direct?: JobOutput,
  listen?: JobOutput,
): JobOutput | undefined {
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
  // SaveAudio: keep the written-file STRING payload (path + provenance sidecar)
  // so the Inspector can show the output path and Review compliance action.
  // Auditioning still works via the separately-resolved listen id.
  if (direct?.type === "STRING" && direct.path) {
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
  "AUTHENTICITY",
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
    });
  }
  return merged;
}

export function proxyNodeId(groupId: string): string {
  return `proxy_${groupId}`;
}

export function collapsedMemberIds(workflow: Workflow): Set<string> {
  const hidden = new Set<string>();
  for (const group of workflow.groups) {
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
export function loadAudioChannelOutletSockets(channelCount: number): NodeSocketSpec[] {
  const count = Math.max(1, Math.floor(channelCount));
  const stereoNames = ["L", "R"];
  return Array.from({ length: count }, (_, slot) => ({
    name: count === 2 ? stereoNames[slot]! : count === 1 ? "audio" : `ch${slot}`,
    type: "AUDIO",
    slot,
  }));
}

export function workflowToFlowNodes(
  workflow: Workflow,
  nodeStatus: Record<string, NodeRenderStatus>,
  outputs?: Record<string, JobOutput>,
  schemas?: Record<string, NodeSchema>,
  nodeIssues?: Record<string, string>,
  /** Probed channel counts for LoadAudio nodes (path → channels), keyed by node id. */
  loadAudioChannels?: Record<string, number>,
): Node<GroovyNodeData | GroovyGroupNodeData>[] {
  const hidden = collapsedMemberIds(workflow);
  const nodes: Node<GroovyNodeData | GroovyGroupNodeData>[] = workflow.nodes
    .filter((node) => !hidden.has(node.id))
    .map((n: WorkflowNode) => {
      const schema = schemas?.[n.type];
      const linkCounts = inferNodeSocketCounts(workflow, n.id);
      const inputs: NodeSocketSpec[] = schema
        ? schemaInputSockets(schema)
        : linkCounts.inputs > 0
          ? placeholderInputSockets(linkCounts.inputs)
          : [];
      const jobOut = outputs?.[n.id];
      const outputSockets: NodeSocketSpec[] = (() => {
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
        }
        if (!schema) return placeholderOutputSockets(linkCounts.outputs);
        return schema.outputs.map((socket, slot) => ({
          name: socket.name,
          // When Preview (or passthrough) emits TEXT, color the handle from the job.
          type: slot === 0 && jobOut?.type === "TEXT" ? "TEXT" : socket.type,
          slot,
        }));
      })();
      const noteText =
        n.type === "Note"
          ? typeof n.widgets.text === "string"
            ? n.widgets.text
            : String(n.widgets.text ?? "")
          : undefined;
      return {
        id: n.id,
        type: "groovy",
        position: n.pos ?? { x: 0, y: 0 },
        data: {
          label: n.type,
          status: nodeStatus[n.id] ?? "idle",
          nodeId: n.id,
          canAudition: nodeHasListenableOutput(workflow, n.id, outputs),
          issue: nodeIssues?.[n.id],
          previewText: previewTextSnippet(jobOut) ?? undefined,
          noteText,
          inputs,
          outputs: outputSockets,
        },
      };
    });

  for (const group of workflow.groups) {
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
    const color = socketTypeColor(l.type);
    return {
      id: l.id,
      source: l.from[0],
      target: l.to[0],
      sourceHandle: String(l.from[1]),
      targetHandle: String(l.to[1]),
      label: l.type,
      className: [typeClass, active ? "groovy-edge--active" : ""].filter(Boolean).join(" "),
      animated: active,
      style: { stroke: color, strokeWidth: 2 },
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
const WIRED_TEXT_SUPERSEDES_WIDGET: Record<string, Record<string, string>> = {
  GenerateAudio: { text: "prompt" },
  MIDIToAudio: { text: "prompt" },
  SingFromMIDI: { lyrics: "text" },
  TTS: { transcript: "text" },
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
    if (supersededWidget !== widgetName) continue;
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
    .map((edge) => `${edge.id}:${edge.source}->${edge.target}:${edge.className ?? ""}:${edge.animated ? 1 : 0}`)
    .join("|");
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
  const linkType =
    targetSchema?.inputs[targetSlot]?.type ?? sourceSchema?.outputs[sourceSlot]?.type ?? "AUDIO";

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
const NODE_PLACEMENT_GAP = 36;

type Rect = { x: number; y: number; w: number; h: number };

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

/** Conservative canvas footprint for collision / auto-layout (visual node chrome). */
export function estimateNodeSize(node: WorkflowNode): { width: number; height: number } {
  let width = DEFAULT_NODE_SIZE.width;
  let height = DEFAULT_NODE_SIZE.height;
  switch (node.type) {
    case "Note":
      width = 220;
      height = 130;
      break;
    case "SeparateStems":
      width = 220;
      height = 120;
      break;
    case "Prompt":
    case "GenerateAudio":
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
      if (rectsOverlap(rects[i], rects[j])) return true;
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
    if (!obstacles.some((obstacle) => rectsOverlap(candidate, obstacle))) {
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
