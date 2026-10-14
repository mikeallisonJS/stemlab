// Pure helpers for editing a recipe as a graph. Nothing here talks to the server.

import type { JsonSchema, ModelInfo, NodeData, Op, OpInfo, RecipeData, Schema } from "./types";

export const MIX = "mix";

export interface Ref {
  node: string;
  stem: string;
}

export function splitRef(reference: string): Ref | null {
  if (reference === MIX) return { node: MIX, stem: MIX };
  const dot = reference.indexOf(".");
  if (dot <= 0 || dot === reference.length - 1) return null;
  return { node: reference.slice(0, dot), stem: reference.slice(dot + 1) };
}

export function makeRef(node: string, stem: string): string {
  return node === MIX ? MIX : `${node}.${stem}`;
}

/** ensemble and export take a plain list of inputs; every other op has named slots. */
function isListOp(op: Op): boolean {
  return op === "ensemble" || op === "export";
}

/** References plugged into one input slot of a node, in order. */
export function slotRefs(node: NodeData, slot: string): string[] {
  const inputs = node.inputs;
  if (isListOp(node.op)) {
    if (Array.isArray(inputs)) return inputs;
    return inputs ? (Object.values(inputs) as string[]) : [];
  }
  const value = (inputs as Record<string, string | string[]> | undefined)?.[slot];
  if (value === undefined) {
    // separate, postprocess and analyze read the mix unless told otherwise
    return slot === "audio" || slot === "mix" ? [MIX] : [];
  }
  return Array.isArray(value) ? value : value ? [value] : [];
}

/** A copy of the node with one input slot replaced. */
export function withSlotRefs(node: NodeData, slot: string, refs: string[], many: boolean): NodeData {
  if (isListOp(node.op)) {
    const current = node.inputs;
    if (current && !Array.isArray(current)) {
      // A labelled export: keep the labels of what stays, name new entries after their stem
      const labelled: Record<string, string> = {};
      const used = new Set<string>();
      for (const [label, ref] of Object.entries(current as Record<string, string>)) {
        if (refs.includes(ref) && !used.has(ref)) {
          labelled[label] = ref;
          used.add(ref);
        }
      }
      for (const ref of refs) {
        if (used.has(ref)) continue;
        const parsed = splitRef(ref);
        let label = parsed ? (parsed.stem === "out" || parsed.stem === MIX ? parsed.node : parsed.stem) : ref;
        while (label in labelled) label += "_";
        labelled[label] = ref;
      }
      return { ...node, inputs: labelled };
    }
    return { ...node, inputs: refs };
  }
  const inputs = { ...((node.inputs as Record<string, string | string[]> | undefined) ?? {}) };
  if (many) inputs[slot] = refs;
  else if (refs.length) inputs[slot] = refs[refs.length - 1];
  else inputs[slot] = "";
  return { ...node, inputs };
}

/** Every reference a node reads, with the slot it is plugged into. */
export function nodeRefs(node: NodeData, info: OpInfo): { slot: string; ref: string }[] {
  return info.inputs.flatMap((slot) => slotRefs(node, slot.name).map((ref) => ({ slot: slot.name, ref })));
}

/** The stems a node offers to other nodes. */
export function outputsOf(node: NodeData, info: OpInfo, models: ModelInfo[]): string[] {
  if (info.outputs !== "model") return info.outputs;
  if (node.targets && node.targets.length) return node.targets;
  return models.find((model) => model.id === node.model)?.stems ?? [];
}

export function uniqueName(recipe: RecipeData, base: string): string {
  if (!(base in recipe.nodes) && base !== MIX) return base;
  for (let index = 2; ; index++) {
    const name = `${base}${index}`;
    if (!(name in recipe.nodes)) return name;
  }
}

/** A new node with the inputs its op needs, left for the user to connect. */
export function newNode(op: Op, models: ModelInfo[]): NodeData {
  const installed = models.filter((model) => model.installed);
  switch (op) {
    case "separate":
      return { op, model: installed[0]?.id ?? "" };
    case "postprocess":
      return { op, model: installed.find((model) => model.stems.length === 1)?.id ?? "", inputs: { audio: "" } };
    case "subtract":
      return { op, inputs: { a: MIX, b: "" } };
    case "ensemble":
      return { op, inputs: [] };
    case "analyze":
      return { op, inputs: { stems: [] } };
    case "export":
      return { op, inputs: [] };
  }
}

function mapRefs(node: NodeData, change: (ref: string) => string | null): NodeData {
  const apply = (refs: string[]) => refs.map(change).filter((ref): ref is string => ref !== null);
  const inputs = node.inputs;
  if (!inputs) return node;
  if (Array.isArray(inputs)) return { ...node, inputs: apply(inputs) };
  const result: Record<string, string | string[]> = {};
  for (const [key, value] of Object.entries(inputs)) {
    if (Array.isArray(value)) result[key] = apply(value);
    else {
      const changed = change(value);
      // A labelled export entry disappears; a named slot is left empty to be reconnected
      if (changed !== null) result[key] = changed;
      else if (!isListOp(node.op)) result[key] = "";
    }
  }
  return { ...node, inputs: result };
}

export function renameNode(recipe: RecipeData, from: string, to: string): RecipeData {
  if (from === to || !(from in recipe.nodes)) return recipe;
  const nodes: Record<string, NodeData> = {};
  for (const [name, node] of Object.entries(recipe.nodes)) {
    const updated = mapRefs(node, (ref) => {
      const parsed = splitRef(ref);
      return parsed && parsed.node === from ? makeRef(to, parsed.stem) : ref;
    });
    nodes[name === from ? to : name] = updated;
  }
  return { ...recipe, nodes };
}

export function deleteNode(recipe: RecipeData, name: string): RecipeData {
  const nodes: Record<string, NodeData> = {};
  for (const [key, node] of Object.entries(recipe.nodes)) {
    if (key === name) continue;
    nodes[key] = mapRefs(node, (ref) => (splitRef(ref)?.node === name ? null : ref));
  }
  return { ...recipe, nodes };
}

/** Drop references to stems a node no longer offers (after its model or targets changed). */
export function pruneRefs(recipe: RecipeData, name: string, outputs: string[]): RecipeData {
  const nodes: Record<string, NodeData> = {};
  for (const [key, node] of Object.entries(recipe.nodes)) {
    nodes[key] = mapRefs(node, (ref) => {
      const parsed = splitRef(ref);
      return parsed && parsed.node === name && !outputs.includes(parsed.stem) ? null : ref;
    });
  }
  return { ...recipe, nodes };
}

/** How far each node is from the mix, for laying the graph out left to right. */
export function depths(recipe: RecipeData, ops: Schema["ops"]): Record<string, number> {
  const result: Record<string, number> = {};
  const visit = (name: string, trail: Set<string>): number => {
    if (name in result) return result[name];
    const node = recipe.nodes[name];
    if (!node || trail.has(name)) return 0;
    trail.add(name);
    let depth = 1;
    for (const { ref } of nodeRefs(node, ops[node.op])) {
      const source = splitRef(ref)?.node;
      if (source && source !== MIX && source in recipe.nodes) depth = Math.max(depth, visit(source, trail) + 1);
    }
    trail.delete(name);
    result[name] = depth;
    return depth;
  };
  for (const name of Object.keys(recipe.nodes)) visit(name, new Set());
  return result;
}

export function autoLayout(recipe: RecipeData, ops: Schema["ops"]): Record<string, { x: number; y: number }> {
  const depth = depths(recipe, ops);
  const columns: Record<number, string[]> = {};
  for (const name of Object.keys(recipe.nodes)) (columns[depth[name]] ??= []).push(name);
  const positions: Record<string, { x: number; y: number }> = { [MIX]: { x: 0, y: 120 } };
  for (const [column, names] of Object.entries(columns)) {
    names.forEach((name, row) => {
      positions[name] = { x: Number(column) * 300, y: row * 190 + (Number(column) % 2) * 40 };
    });
  }
  return positions;
}

// JSON Schema -------------------------------------------------------------------

/** Follow $ref and unwrap `anyOf [X, null]` as Pydantic writes optional fields. */
export function resolveSchema(schema: JsonSchema | undefined, root: JsonSchema): JsonSchema {
  let current = schema ?? {};
  for (let guard = 0; guard < 8; guard++) {
    if (current.$ref) {
      const name = current.$ref.split("/").pop() as string;
      current = { ...root.$defs?.[name], description: current.description ?? root.$defs?.[name]?.description };
    } else if (current.allOf?.length === 1) {
      current = { ...current.allOf[0], description: current.description, default: current.default };
    } else if (current.anyOf) {
      const real = current.anyOf.filter((option) => option.type !== "null");
      if (real.length !== 1) break;
      current = { ...real[0], description: current.description, default: current.default };
    } else break;
  }
  return current;
}

/** The schema of an op's `params`, taken from the recipe's JSON Schema. */
export function opParamSchema(op: Op, schema: Schema): JsonSchema | null {
  const defs = schema.recipe.$defs ?? {};
  const nodeDef = defs[op.charAt(0).toUpperCase() + op.slice(1) + "Node"];
  const params = resolveSchema(nodeDef?.properties?.params, schema.recipe);
  return params.properties ? params : null;
}

/** Remove settings that are unset, so the saved recipe only holds what was chosen. */
export function compact<T extends Record<string, unknown>>(values: T): T {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== "") result[key] = value;
  }
  return result as T;
}
