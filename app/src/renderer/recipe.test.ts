import { describe, expect, it } from "vitest";

import {
  autoLayout,
  deleteNode,
  depths,
  newNode,
  nodeRefs,
  opParamSchema,
  outputsOf,
  pruneRefs,
  renameNode,
  resolveSchema,
  slotRefs,
  splitRef,
  uniqueName,
  withSlotRefs,
} from "./recipe";
import type { ModelInfo, RecipeData, Schema } from "./types";

const ops: Schema["ops"] = {
  separate: { inputs: [{ name: "audio", many: false }], outputs: "model", model: true },
  subtract: { inputs: [{ name: "a", many: false }, { name: "b", many: false }], outputs: ["out"] },
  ensemble: { inputs: [{ name: "inputs", many: true }], outputs: ["out"] },
  postprocess: { inputs: [{ name: "audio", many: false }], outputs: ["out"], model: true },
  analyze: { inputs: [{ name: "mix", many: false }, { name: "stems", many: true }], outputs: ["residual"] },
  export: { inputs: [{ name: "inputs", many: true }], outputs: [] },
};

const models: ModelInfo[] = [
  { id: "vocal", backend: "msst", stems: ["vocals"], installed: true },
  { id: "six", backend: "demucs", stems: ["drums", "bass", "other", "vocals", "guitar", "piano"], installed: true },
];

const recipe: RecipeData = {
  name: "test",
  nodes: {
    vox: { op: "separate", model: "vocal", targets: ["vocals"] },
    inst: { op: "subtract", inputs: { a: "mix", b: "vox.vocals" } },
    six: { op: "separate", model: "six", inputs: { audio: "inst.out" } },
    both: { op: "ensemble", inputs: ["six.drums", "six.bass"] },
    check: { op: "analyze", inputs: { stems: ["vox.vocals", "inst.out"] } },
    out: { op: "export", inputs: { lead: "vox.vocals", rest: "inst.out" } },
  },
};

describe("references", () => {
  it("splits mix and node.stem", () => {
    expect(splitRef("mix")).toEqual({ node: "mix", stem: "mix" });
    expect(splitRef("vox.vocals")).toEqual({ node: "vox", stem: "vocals" });
    expect(splitRef("nodot")).toBeNull();
    expect(splitRef("")).toBeNull();
  });

  it("reads slots, with the mix as the default source", () => {
    expect(slotRefs(recipe.nodes.vox, "audio")).toEqual(["mix"]);
    expect(slotRefs(recipe.nodes.six, "audio")).toEqual(["inst.out"]);
    expect(slotRefs(recipe.nodes.inst, "b")).toEqual(["vox.vocals"]);
    expect(slotRefs(recipe.nodes.both, "inputs")).toEqual(["six.drums", "six.bass"]);
    expect(slotRefs(recipe.nodes.check, "mix")).toEqual(["mix"]);
    expect(slotRefs(recipe.nodes.out, "inputs")).toEqual(["vox.vocals", "inst.out"]);
  });

  it("lists every reference with its slot", () => {
    expect(nodeRefs(recipe.nodes.check, ops.analyze)).toEqual([
      { slot: "mix", ref: "mix" },
      { slot: "stems", ref: "vox.vocals" },
      { slot: "stems", ref: "inst.out" },
    ]);
  });
});

describe("editing inputs", () => {
  it("replaces a single slot and leaves it empty when disconnected", () => {
    expect(withSlotRefs(recipe.nodes.inst, "b", ["six.vocals"], false).inputs).toEqual({ a: "mix", b: "six.vocals" });
    expect(withSlotRefs(recipe.nodes.inst, "b", [], false).inputs).toEqual({ a: "mix", b: "" });
  });

  it("keeps the labels of a labelled export and names new entries", () => {
    const next = withSlotRefs(recipe.nodes.out, "inputs", ["inst.out", "six.drums", "both.out"], true);
    expect(next.inputs).toEqual({ rest: "inst.out", drums: "six.drums", both: "both.out" });
  });

  it("does not change the node it was given", () => {
    withSlotRefs(recipe.nodes.both, "inputs", [], true);
    expect(recipe.nodes.both.inputs).toEqual(["six.drums", "six.bass"]);
  });
});

describe("editing nodes", () => {
  it("renames a node everywhere it is read", () => {
    const next = renameNode(recipe, "vox", "lead");
    expect(Object.keys(next.nodes)).toEqual(["lead", "inst", "six", "both", "check", "out"]);
    expect(next.nodes.inst.inputs).toEqual({ a: "mix", b: "lead.vocals" });
    expect(next.nodes.out.inputs).toEqual({ lead: "lead.vocals", rest: "inst.out" });
    expect(recipe.nodes.vox).toBeDefined();
  });

  it("deletes a node and what pointed at it", () => {
    const next = deleteNode(recipe, "inst");
    expect("inst" in next.nodes).toBe(false);
    expect(next.nodes.six.inputs).toEqual({ audio: "" });
    expect(next.nodes.check.inputs).toEqual({ stems: ["vox.vocals"] });
    expect(next.nodes.out.inputs).toEqual({ lead: "vox.vocals" });
  });

  it("drops references to stems a node stops offering", () => {
    const next = pruneRefs(recipe, "six", ["bass"]);
    expect(next.nodes.both.inputs).toEqual(["six.bass"]);
  });

  it("offers the stems of the model, or the chosen targets", () => {
    expect(outputsOf(recipe.nodes.vox, ops.separate, models)).toEqual(["vocals"]);
    expect(outputsOf(recipe.nodes.six, ops.separate, models)).toHaveLength(6);
    expect(outputsOf({ op: "separate", model: "missing" }, ops.separate, models)).toEqual([]);
    expect(outputsOf(recipe.nodes.inst, ops.subtract, models)).toEqual(["out"]);
    expect(outputsOf(recipe.nodes.out, ops.export, models)).toEqual([]);
  });

  it("creates nodes with unique names and the inputs their op needs", () => {
    expect(uniqueName(recipe, "vox")).toBe("vox2");
    expect(uniqueName(recipe, "fresh")).toBe("fresh");
    expect(uniqueName(recipe, "mix")).toBe("mix2");
    expect(newNode("separate", models)).toEqual({ op: "separate", model: "vocal" });
    expect(newNode("subtract", models).inputs).toEqual({ a: "mix", b: "" });
    expect(newNode("postprocess", models).model).toBe("vocal");
  });
});

describe("layout", () => {
  it("places nodes left to right by how far they are from the mix", () => {
    expect(depths(recipe, ops)).toEqual({ vox: 1, inst: 2, six: 3, both: 4, check: 3, out: 3 });
    const positions = autoLayout(recipe, ops);
    expect(positions.mix.x).toBeLessThan(positions.vox.x);
    expect(positions.vox.x).toBeLessThan(positions.inst.x);
    expect(positions.six.y).not.toBe(positions.check.y);
  });

  it("survives a cycle typed into the YAML", () => {
    const cyclic: RecipeData = {
      name: "loop",
      nodes: { a: { op: "subtract", inputs: { a: "mix", b: "b.out" } }, b: { op: "subtract", inputs: { a: "mix", b: "a.out" } } },
    };
    expect(Object.keys(autoLayout(cyclic, ops))).toEqual(["mix", "b", "a"]);
  });
});

describe("schemas", () => {
  const root = {
    $defs: {
      SubtractParams: { type: "object", properties: { gain_b: { type: "number", default: 1 } } },
      SubtractNode: { properties: { params: { $ref: "#/$defs/SubtractParams" } } },
      SeparateNode: { properties: { params: { type: "object" } } },
    },
  };

  it("follows references and unwraps optional fields", () => {
    expect(resolveSchema({ $ref: "#/$defs/SubtractParams" }, root).properties?.gain_b.default).toBe(1);
    expect(resolveSchema({ anyOf: [{ type: "integer", minimum: 8000 }, { type: "null" }], description: "rate" }, root)).toEqual({
      type: "integer",
      minimum: 8000,
      description: "rate",
      default: undefined,
    });
  });

  it("finds an op's parameters in the recipe schema", () => {
    const schema = { recipe: root, ops, backends: {}, export_formats: [] } as Schema;
    expect(opParamSchema("subtract", schema)?.properties).toHaveProperty("gain_b");
    expect(opParamSchema("separate", schema)).toBeNull();
  });
});
