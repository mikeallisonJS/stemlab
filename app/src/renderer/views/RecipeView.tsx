import {
  Background,
  Controls,
  type Connection,
  type Edge,
  type EdgeChange,
  Handle,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { SchemaForm } from "../components/SchemaForm";
import {
  MIX,
  autoLayout,
  compact,
  deleteNode,
  makeRef,
  newNode,
  nodeRefs,
  opParamSchema,
  outputsOf,
  pruneRefs,
  renameNode,
  slotRefs,
  splitRef,
  uniqueName,
  withSlotRefs,
} from "../recipe";
import type { JsonSchema, ModelInfo, NodeData, Op, RecipeData, Schema, Validation } from "../types";

type Positions = Record<string, { x: number; y: number }>;

interface CardData extends Record<string, unknown> {
  name: string;
  op: Op | "mix";
  model?: string;
  inputs: { name: string; many: boolean; count: number }[];
  outputs: string[];
  problem: boolean;
}

const OP_LABEL: Record<string, string> = {
  mix: "input file",
  separate: "separate",
  subtract: "subtract",
  ensemble: "ensemble",
  postprocess: "postprocess",
  analyze: "analyze",
  export: "export",
};

/** One node of the graph: inputs on the left, output stems on the right. */
function RecipeCard({ data, selected }: NodeProps<Node<CardData>>) {
  const rows = Math.max(data.inputs.length, data.outputs.length, 1);
  return (
    <div className={`card op-${data.op}${selected ? " selected" : ""}${data.problem ? " problem" : ""}`}>
      <div className="card-head">
        <span className="card-name">{data.name}</span>
        <span className="card-op">{OP_LABEL[data.op]}</span>
      </div>
      {data.model !== undefined && <div className="card-model">{data.model || "no model chosen"}</div>}
      <div className="card-ports" style={{ minHeight: rows * 22 }}>
        <div className="ports-in">
          {data.inputs.map((slot) => (
            <div key={slot.name} className="port">
              <Handle type="target" position={Position.Left} id={slot.name} />
              <span>
                {slot.name}
                {slot.many ? ` (${slot.count})` : ""}
              </span>
            </div>
          ))}
        </div>
        <div className="ports-out">
          {data.outputs.map((stem) => (
            <div key={stem} className="port">
              <span>{stem}</span>
              <Handle type="source" position={Position.Right} id={stem} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { recipe: RecipeCard };

interface Props {
  recipe: RecipeData;
  setRecipe: (recipe: RecipeData) => void;
  schema: Schema;
  models: ModelInfo[];
  validation: Validation | null;
  onRun: () => void;
}

export function RecipeView({ recipe, setRecipe, schema, models, validation, onRun }: Props) {
  const [positions, setPositions] = useState<Positions>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedEdges, setSelectedEdges] = useState<Set<string>>(new Set());
  const [yamlOpen, setYamlOpen] = useState(false);
  const [examples, setExamples] = useState<{ file: string; name: string; yaml: string }[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const layoutFor = useRef<string>("");

  useEffect(() => {
    api.recipes().then(setExamples).catch(() => setExamples([]));
  }, []);

  // Lay the graph out when another recipe is loaded; new nodes get a free spot
  useEffect(() => {
    const names = Object.keys(recipe.nodes);
    if (layoutFor.current !== recipe.name) {
      layoutFor.current = recipe.name;
      setPositions(autoLayout(recipe, schema.ops));
      return;
    }
    const missing = names.filter((name) => !(name in positions));
    if (missing.length) {
      const laid = autoLayout(recipe, schema.ops);
      setPositions((current) => {
        const next = { ...current };
        if (!(MIX in next)) next[MIX] = laid[MIX];
        for (const name of missing) next[name] = laid[name];
        return next;
      });
    }
  }, [recipe, schema.ops, positions]);

  const failing = validation && !validation.ok ? (validation.error?.match(/node '([^']+)'/)?.[1] ?? null) : null;

  const nodes: Node<CardData>[] = useMemo(() => {
    const cards: Node<CardData>[] = [
      {
        id: MIX,
        type: "recipe",
        position: positions[MIX] ?? { x: 0, y: 120 },
        deletable: false,
        selected: selected === MIX,
        data: { name: MIX, op: "mix", inputs: [], outputs: [MIX], problem: false },
      },
    ];
    for (const [name, node] of Object.entries(recipe.nodes)) {
      const info = schema.ops[node.op];
      cards.push({
        id: name,
        type: "recipe",
        position: positions[name] ?? { x: 300, y: 0 },
        selected: selected === name,
        data: {
          name,
          op: node.op,
          model: info.model ? (node.model ?? "") : undefined,
          inputs: info.inputs.map((slot) => ({ ...slot, count: slotRefs(node, slot.name).length })),
          outputs: outputsOf(node, info, models),
          problem: failing === name,
        },
      });
    }
    return cards;
  }, [recipe, positions, selected, schema.ops, models, failing]);

  const edges: Edge[] = useMemo(() => {
    const result: Edge[] = [];
    for (const [name, node] of Object.entries(recipe.nodes)) {
      nodeRefs(node, schema.ops[node.op]).forEach(({ slot, ref }, index) => {
        const source = splitRef(ref);
        if (!source || (source.node !== MIX && !(source.node in recipe.nodes))) return;
        const id = `${ref}->${name}.${slot}#${index}`;
        result.push({
          id,
          source: source.node,
          sourceHandle: source.stem,
          target: name,
          targetHandle: slot,
          selected: selectedEdges.has(id),
          data: { ref, slot },
        });
      });
    }
    return result;
  }, [recipe, schema.ops, selectedEdges]);

  const updateNode = (name: string, node: NodeData) => setRecipe({ ...recipe, nodes: { ...recipe.nodes, [name]: node } });

  const onNodesChange = (changes: NodeChange<Node<CardData>>[]) => {
    let next = recipe;
    for (const change of changes) {
      if (change.type === "position" && change.position) {
        const { id, position } = change;
        setPositions((current) => ({ ...current, [id]: position }));
      } else if (change.type === "select") {
        if (change.selected) setSelected(change.id);
        else setSelected((current) => (current === change.id ? null : current));
      } else if (change.type === "remove" && change.id !== MIX) {
        next = deleteNode(next, change.id);
      }
    }
    if (next !== recipe) setRecipe(next);
  };

  const removeEdge = (current: RecipeData, edge: Edge): RecipeData => {
    const node = current.nodes[edge.target];
    const slot = schema.ops[node.op].inputs.find((item) => item.name === edge.targetHandle);
    if (!node || !slot) return current;
    const ref = (edge.data as { ref: string }).ref;
    const refs = slotRefs(node, slot.name);
    const index = refs.indexOf(ref);
    const remaining = index < 0 ? refs : [...refs.slice(0, index), ...refs.slice(index + 1)];
    return { ...current, nodes: { ...current.nodes, [edge.target]: withSlotRefs(node, slot.name, remaining, slot.many) } };
  };

  const onEdgesChange = (changes: EdgeChange[]) => {
    let next = recipe;
    const picked = new Set(selectedEdges);
    for (const change of changes) {
      if (change.type === "select") {
        if (change.selected) picked.add(change.id);
        else picked.delete(change.id);
      } else if (change.type === "remove") {
        const edge = edges.find((item) => item.id === change.id);
        if (edge) next = removeEdge(next, edge);
        picked.delete(change.id);
      }
    }
    setSelectedEdges(picked);
    if (next !== recipe) setRecipe(next);
  };

  const onConnect = (connection: Connection) => {
    const { source, sourceHandle, target, targetHandle } = connection;
    if (!source || !target || !sourceHandle || !targetHandle || source === target) return;
    const node = recipe.nodes[target];
    const slot = node && schema.ops[node.op].inputs.find((item) => item.name === targetHandle);
    if (!node || !slot) return;
    const ref = makeRef(source, sourceHandle);
    const refs = slotRefs(node, slot.name);
    if (slot.many && refs.includes(ref)) return;
    updateNode(target, withSlotRefs(node, slot.name, slot.many ? [...refs, ref] : [ref], slot.many));
  };

  const addNode = (op: Op) => {
    const name = uniqueName(recipe, op === "postprocess" ? "post" : op);
    // Right of the selected node (or of everything), moved down until it covers no other node
    const taken = Object.values(positions);
    const anchor = selected && positions[selected]
      ? positions[selected]
      : { x: Math.max(-300, ...taken.map((spot) => spot.x)), y: 120 };
    const spot = { x: anchor.x + 300, y: anchor.y };
    while (taken.some((other) => Math.abs(other.x - spot.x) < 220 && Math.abs(other.y - spot.y) < 150)) spot.y += 170;
    setPositions((current) => ({ ...current, [name]: spot }));
    setRecipe({ ...recipe, nodes: { ...recipe.nodes, [name]: newNode(op, models) } });
    setSelected(name);
  };

  const rename = (from: string, to: string) => {
    const clean = to.trim().replace(/[^A-Za-z0-9_-]/g, "_");
    if (!clean || clean === from || clean === MIX || clean in recipe.nodes) return;
    setPositions((current) => {
      const { [from]: moved, ...rest } = current;
      return moved ? { ...rest, [clean]: moved } : rest;
    });
    setRecipe(renameNode(recipe, from, clean));
    setSelected(clean);
  };

  const loadYaml = async (text: string) => {
    try {
      const parsed = await api.parseRecipe(text);
      layoutFor.current = "";
      setSelected(null);
      setRecipe(parsed);
      setMessage(null);
      return true;
    } catch (error) {
      setMessage((error as Error).message);
      return false;
    }
  };

  const openFile = (file: File | undefined) => {
    if (file) file.text().then(loadYaml);
  };

  const download = async () => {
    try {
      const text = await api.recipeYaml(recipe);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([text], { type: "text/yaml" }));
      link.download = `${recipe.name || "recipe"}.yaml`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      setMessage((error as Error).message);
    }
  };

  const node = selected && selected !== MIX ? recipe.nodes[selected] : null;

  return (
    <div className="recipe-view">
      <div className="toolbar">
        <label>
          Recipe
          <input className="name-input" value={recipe.name} aria-label="Recipe name"
            onChange={(e) => {
              layoutFor.current = e.target.value;
              setRecipe({ ...recipe, name: e.target.value });
            }} />
        </label>
        <select value="" aria-label="Load an example" onChange={(e) => {
          const example = examples.find((item) => item.file === e.target.value);
          if (example) loadYaml(example.yaml);
        }}>
          <option value="">Load example...</option>
          {examples.map((example) => (
            <option key={example.file} value={example.file}>{example.name}</option>
          ))}
        </select>
        <label className="button">
          Open YAML...
          <input type="file" accept=".yaml,.yml" hidden onChange={(e) => {
            openFile(e.target.files?.[0]);
            e.target.value = "";
          }} />
        </label>
        <button onClick={download}>Save YAML</button>
        <button onClick={() => setYamlOpen(true)}>Edit as YAML</button>
        <span className="spacer" />
        <span className="add-label">Add node:</span>
        {(Object.keys(schema.ops) as Op[]).map((op) => (
          <button key={op} className={`add op-${op}`} onClick={() => addNode(op)}>{op}</button>
        ))}
        <button onClick={() => setPositions(autoLayout(recipe, schema.ops))}>Tidy</button>
        <button className="primary" onClick={onRun} disabled={!validation?.ok}>Run...</button>
      </div>

      {(message || (validation && !validation.ok)) && (
        <div className="banner error" role="alert">{message ?? validation?.error}</div>
      )}

      <div className="recipe-body">
        <div className="graph">
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange} onConnect={onConnect} fitView minZoom={0.2} deleteKeyCode={["Delete", "Backspace"]}
            colorMode="dark" proOptions={{ hideAttribution: true }}>
            <Background gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <aside className="panel">
          {node && selected ? (
            <NodePanel key={selected} name={selected} node={node} recipe={recipe} schema={schema} models={models}
              resolved={validation?.nodes?.[selected]?.params} onRename={(to) => rename(selected, to)}
              onChange={(next, outputsChanged) => {
                let updated: RecipeData = { ...recipe, nodes: { ...recipe.nodes, [selected]: next } };
                if (outputsChanged) updated = pruneRefs(updated, selected, outputsOf(next, schema.ops[next.op], models));
                setRecipe(updated);
              }}
              onDelete={() => {
                setRecipe(deleteNode(recipe, selected));
                setSelected(null);
              }} />
          ) : (
            <RecipePanel recipe={recipe} setRecipe={setRecipe} schema={schema} selectedMix={selected === MIX} />
          )}
        </aside>
      </div>

      {yamlOpen && <YamlDialog recipe={recipe} onApply={loadYaml} onClose={() => setYamlOpen(false)} />}
    </div>
  );
}

/** The knob panel of the selected node, generated from the schemas. */
function NodePanel(props: {
  name: string;
  node: NodeData;
  recipe: RecipeData;
  schema: Schema;
  models: ModelInfo[];
  resolved?: Record<string, unknown>;
  onRename: (to: string) => void;
  onChange: (node: NodeData, outputsChanged: boolean) => void;
  onDelete: () => void;
}) {
  const { name, node, recipe, schema, models, resolved, onRename, onChange, onDelete } = props;
  const [draftName, setDraftName] = useState(name);
  const info = schema.ops[node.op];
  const model = models.find((item) => item.id === node.model);

  let paramSchema: JsonSchema | null;
  if (info.model) {
    const backend = model ? schema.backends[model.backend] : null;
    paramSchema = backend && !backend.error ? backend : null;
  } else {
    paramSchema = opParamSchema(node.op, schema);
  }

  // Everything another node offers, as choices for this node's inputs
  const available = [MIX];
  for (const [other, otherNode] of Object.entries(recipe.nodes)) {
    if (other === name) continue;
    for (const stem of outputsOf(otherNode, schema.ops[otherNode.op], models)) available.push(makeRef(other, stem));
  }

  const setParams = (params: Record<string, unknown>) => {
    const cleaned = compact(params);
    const { params: _old, ...rest } = node;
    onChange(Object.keys(cleaned).length ? { ...rest, params: cleaned } : rest, false);
  };

  return (
    <div>
      <h3>
        <span className={`dot op-${node.op}`} /> {node.op}
      </h3>
      <label className="field">
        <span className="field-name">name</span>
        <input value={draftName} onChange={(e) => setDraftName(e.target.value)} onBlur={() => onRename(draftName)}
          onKeyDown={(e) => e.key === "Enter" && onRename(draftName)} />
      </label>

      {info.model && (
        <label className="field">
          <span className="field-name">model</span>
          <select value={node.model ?? ""} onChange={(e) => {
            const { targets: _t, target: _k, params: _p, ...rest } = node;
            onChange({ ...rest, model: e.target.value }, true);
          }}>
            {!model && <option value={node.model ?? ""}>{node.model ? `${node.model} (not installed)` : "choose..."}</option>}
            {models.filter((item) => item.installed).map((item) => (
              <option key={item.id} value={item.id}>{item.id}</option>
            ))}
          </select>
          {model && <span className="field-help">{model.backend} · {model.arch} · {model.notes}</span>}
        </label>
      )}

      {node.op === "separate" && model && (
        <div className="field">
          <span className="field-name">targets</span>
          <div className="checks">
            {model.stems.map((stem) => {
              const active = node.targets ? node.targets.includes(stem) : true;
              return (
                <label key={stem}>
                  <input type="checkbox" checked={active} onChange={() => {
                    const current = node.targets ?? model.stems;
                    const next = active ? current.filter((item) => item !== stem) : model.stems.filter((item) => current.includes(item) || item === stem);
                    const { targets: _t, ...rest } = node;
                    onChange(next.length === model.stems.length || !next.length ? rest : { ...rest, targets: next }, true);
                  }} />
                  {stem}
                </label>
              );
            })}
          </div>
          <span className="field-help">Stems this node offers to others. All of them are computed and cached either way.</span>
        </div>
      )}

      {node.op === "postprocess" && model && model.stems.length > 1 && (
        <label className="field">
          <span className="field-name">keep</span>
          <select value={node.target ?? ""} onChange={(e) => {
            const { target: _t, ...rest } = node;
            onChange(e.target.value ? { ...rest, target: e.target.value } : rest, false);
          }}>
            <option value="">default ({model.stems[0]})</option>
            {model.stems.map((stem) => <option key={stem} value={stem}>{stem}</option>)}
          </select>
        </label>
      )}

      <h4>Inputs</h4>
      {info.inputs.map((slot) => {
        const refs = slotRefs(node, slot.name);
        return (
          <div key={slot.name} className="field">
            <span className="field-name">{slot.name}</span>
            {slot.many ? (
              <>
                {refs.map((ref, index) => (
                  <div key={ref + index} className="ref-row">
                    <code>{ref}</code>
                    <button className="small" title="Remove" onClick={() => onChange(withSlotRefs(node, slot.name, refs.filter((_, i) => i !== index), true), false)}>×</button>
                  </div>
                ))}
                <select value="" aria-label={`Add to ${slot.name}`} onChange={(e) => e.target.value && onChange(withSlotRefs(node, slot.name, [...refs, e.target.value], true), false)}>
                  <option value="">add...</option>
                  {available.filter((ref) => !refs.includes(ref)).map((ref) => <option key={ref} value={ref}>{ref}</option>)}
                </select>
              </>
            ) : (
              <select value={refs[0] ?? ""} aria-label={slot.name} onChange={(e) => onChange(withSlotRefs(node, slot.name, e.target.value ? [e.target.value] : [], false), false)}>
                <option value="">not connected</option>
                {available.map((ref) => <option key={ref} value={ref}>{ref}</option>)}
              </select>
            )}
          </div>
        );
      })}

      <h4>Parameters</h4>
      {paramSchema ? (
        <SchemaForm schema={paramSchema} root={schema.recipe} value={(node.params ?? {}) as Record<string, unknown>}
          onChange={setParams} resolved={resolved} />
      ) : (
        <p className="muted">{info.model ? "Choose an installed model to see its knobs." : "This node has no parameters."}</p>
      )}

      <button className="danger" onClick={onDelete}>Delete node</button>
    </div>
  );
}

/** Shown when no node is selected: settings of the recipe as a whole. */
function RecipePanel({ recipe, setRecipe, schema, selectedMix }: {
  recipe: RecipeData;
  setRecipe: (recipe: RecipeData) => void;
  schema: Schema;
  selectedMix: boolean;
}) {
  // Defaults apply across backends, so offer every knob any backend has
  const merged: JsonSchema = { type: "object", properties: {} };
  const fields = merged.properties as Record<string, JsonSchema>;
  for (const [backendName, backend] of Object.entries(schema.backends)) {
    for (const [name, field] of Object.entries(backend.properties ?? {})) {
      const known = fields[name];
      if (!known) {
        fields[name] = { ...field, default: undefined, title: backendName };
      } else if (known.type !== field.type || known.minimum !== field.minimum || known.maximum !== field.maximum) {
        // The same name means different things per backend (overlap: a chunk count for msst,
        // a fraction for demucs and onnx). Take any number; each node uses it only if it fits.
        fields[name] = {
          type: "number",
          description: `Differs per backend. ${known.title}: ${known.description} / ${backendName}: ${field.description}. A node only takes the value if it fits its backend.`,
        };
      }
    }
  }
  return (
    <div>
      <h3>{selectedMix ? "mix" : "Recipe"}</h3>
      <p className="muted">
        {selectedMix
          ? "The input file. Every recipe starts here; choose the file when you run it."
          : "Select a node to edit it. Drag from an output on the right of a node to an input on the left of another to connect them; select a connection and press Delete to remove it."}
      </p>
      <h4>Defaults</h4>
      <p className="muted">Applied to every separate and postprocess node unless the node sets its own value.</p>
      <SchemaForm schema={merged} value={recipe.defaults ?? {}} onChange={(defaults) => {
        const cleaned = compact(defaults);
        const { defaults: _old, ...rest } = recipe;
        setRecipe(Object.keys(cleaned).length ? { ...rest, defaults: cleaned } : rest);
      }} />
    </div>
  );
}

function YamlDialog({ recipe, onApply, onClose }: {
  recipe: RecipeData;
  onApply: (text: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.recipeYaml(recipe).then(setText).catch((e: Error) => setError(e.message));
    // Only when the dialog opens: typing must not be overwritten
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Recipe as YAML">
        <h3>Recipe as YAML</h3>
        {error && <div className="banner error">{error}</div>}
        <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        <div className="modal-buttons">
          <button onClick={() => navigator.clipboard?.writeText(text)}>Copy</button>
          <span className="spacer" />
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={async () => {
            try {
              await api.parseRecipe(text);
            } catch (e) {
              return setError((e as Error).message);
            }
            if (await onApply(text)) onClose();
          }}>Apply</button>
        </div>
      </div>
    </div>
  );
}
