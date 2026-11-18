import { useMemo } from "react";
import {
  getMinimalPatch,
  summarizeMinimalPatch,
  type MinimalPatch,
} from "../nodeMinimalPatches";
import type { NodeSchema } from "../types";

type Props = {
  nodeType: string;
  schema: NodeSchema | null;
  schemas?: Record<string, NodeSchema>;
  onApplyToCanvas: (patch: MinimalPatch) => void;
};

/** Inspector Help tab — curated minimal example + apply-to-canvas. */
export default function NodeHelpPanel({ nodeType, schema, schemas = {}, onApplyToCanvas }: Props) {
  const patch = useMemo(
    () => getMinimalPatch(nodeType, schema ? { ...schemas, [nodeType]: schema } : schemas),
    [nodeType, schema, schemas],
  );
  const summary = useMemo(() => (patch ? summarizeMinimalPatch(patch) : null), [patch]);

  if (!patch || !summary) {
    return (
      <div className="node-help">
        <p className="node-helper__hint">No minimal example is available for this node yet.</p>
      </div>
    );
  }

  const focus = patch.workflow.nodes.find((node) => node.id === patch.focusNodeId);

  return (
    <div className="node-help">
      <header className="node-help__head">
        <h4 className="node-help__title">{summary.title}</h4>
        <p className="node-help__desc">{summary.description}</p>
      </header>

      <section className="node-help__example" aria-label="Minimal example">
        <p className="node-help__label">Example chain</p>
        <pre className="node-help__chain">{summary.chain}</pre>
        <ul className="node-help__nodes">
          {patch.workflow.nodes.map((node) => (
            <li
              key={node.id}
              className={
                node.id === patch.focusNodeId ? "node-help__node node-help__node--focus" : "node-help__node"
              }
            >
              <span className="node-help__node-type">{node.type}</span>
              {node.id === patch.focusNodeId ? <span className="node-help__badge">focus</span> : null}
            </li>
          ))}
        </ul>
        {focus ? (
          <p className="node-helper__hint">
            Expands this <strong>{focus.type}</strong> with the example chain (no duplicate focus
            node).
          </p>
        ) : null}
      </section>

      <div className="node-help__actions">
        <button type="button" className="node-help__apply" onClick={() => onApplyToCanvas(patch)}>
          Apply to canvas
        </button>
      </div>
    </div>
  );
}
