import type { InferenceParamSpec, NodeWidgetSpec } from "./types";
import { inferenceParamsForModel } from "./modelInferenceParams";

type SpecLike = {
  name: string;
  type: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  optional?: boolean;
};

/** Prefer live model-card params; fall back to the small client mirror. */
export function resolveInferenceParams(
  modelId: string,
  cardParams?: InferenceParamSpec[] | null,
): InferenceParamSpec[] {
  if (cardParams && cardParams.length > 0) return cardParams;
  return inferenceParamsForModel(modelId);
}

export function paramDefault(param: InferenceParamSpec): unknown {
  if (param.default !== undefined && param.default !== null) return param.default;
  const type = (param.type || "FLOAT").toUpperCase();
  if (type === "BOOLEAN" || type === "BOOL") return false;
  if (type === "INT") return typeof param.min === "number" ? Math.trunc(param.min) : 0;
  if (type === "FLOAT") return typeof param.min === "number" ? param.min : 0;
  return "";
}

/** Schema defaults + model id + every inference param at its catalog default. */
export function widgetsForDroppedModel(opts: {
  schemaDefaults: Record<string, unknown>;
  modelId: string;
  params: InferenceParamSpec[];
}): Record<string, unknown> {
  const widgets: Record<string, unknown> = {
    ...opts.schemaDefaults,
    model: opts.modelId,
  };
  for (const param of opts.params) {
    widgets[param.name] = paramDefault(param);
  }
  return widgets;
}

/**
 * After switching models on an existing node: drop previous model-only params,
 * apply the new model's defaults, keep unrelated schema widgets (prompt, path, …).
 */
export function widgetsAfterModelSwap(opts: {
  existing: Record<string, unknown>;
  modelId: string;
  schemaWidgetNames: Iterable<string>;
  previousParams: InferenceParamSpec[];
  nextParams: InferenceParamSpec[];
}): Record<string, unknown> {
  const schemaNames = new Set(opts.schemaWidgetNames);
  const nextNames = new Set(opts.nextParams.map((param) => param.name));
  const widgets: Record<string, unknown> = { ...opts.existing, model: opts.modelId };

  for (const param of opts.previousParams) {
    if (schemaNames.has(param.name)) continue;
    if (nextNames.has(param.name)) continue;
    delete widgets[param.name];
  }

  for (const param of opts.nextParams) {
    widgets[param.name] = paramDefault(param);
  }
  return widgets;
}

/** Prefer model-catalog min/max/step/default when a schema widget shares the name. */
export function mergeSpecWithModelParam<T extends SpecLike>(
  spec: T,
  param: InferenceParamSpec | undefined,
): T {
  if (!param) return spec;
  return {
    ...spec,
    type: param.type || spec.type,
    default: param.default !== undefined && param.default !== null ? param.default : spec.default,
    min: param.min ?? spec.min,
    max: param.max ?? spec.max,
    step: param.step ?? spec.step,
    description: param.description || spec.description,
  };
}

export function modelParamByName(
  params: InferenceParamSpec[],
): Map<string, InferenceParamSpec> {
  return new Map(params.map((param) => [param.name, param]));
}

export function asWidgetSpec(param: InferenceParamSpec): NodeWidgetSpec {
  return {
    name: param.name,
    type: param.type,
    default: param.default,
    min: param.min,
    max: param.max,
    step: param.step,
    description: param.description,
    optional: true,
  };
}
