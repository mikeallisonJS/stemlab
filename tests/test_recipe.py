from pathlib import Path

import pytest

from stemlab import recipe
from stemlab.recipe import RecipeError

WORKED_EXAMPLE = Path(__file__).parent.parent / "recipes" / "full-split-v1.yaml"

SMALL = """
version: 1
name: small
nodes:
  vox:
    op: separate
    model: vocal-model
    targets: [vocals]
  inst:
    op: subtract
    inputs: {a: mix, b: vox.vocals}
  out:
    op: export
    inputs: [vox.vocals, inst.out]
"""


def broken(text: str, match: str):
    with pytest.raises(RecipeError, match=match):
        recipe.loads(text)


def test_the_worked_example_from_the_handoff_parses():
    parsed = recipe.load(WORKED_EXAMPLE)
    assert parsed.name == "full-split-v1"
    assert parsed.defaults == {"device": "auto", "dtype": "auto", "normalize": True}
    assert [node.op for node in parsed.nodes.values()] == [
        "separate",
        "subtract",
        "separate",
        "separate",
        "ensemble",
        "postprocess",
        "analyze",
        "export",
    ]
    assert parsed.nodes["drums"].params.weights == [0.6, 0.4]
    assert parsed.nodes["out"].params.bit_depth == 24
    order = parsed.order()
    assert order.index("vox") < order.index("inst") < order.index("six") < order.index("drums") < order.index("out")


def test_order_does_not_depend_on_how_the_file_is_written():
    shuffled = """
nodes:
  out: {op: export, inputs: [inst.out]}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  vox: {op: separate, model: m, targets: [vocals]}
"""
    assert recipe.loads(shuffled).order() == ["vox", "inst", "out"]


def test_defaults_are_filled_in():
    parsed = recipe.loads(SMALL)
    assert parsed.nodes["vox"].inputs.audio == "mix"
    assert parsed.nodes["inst"].params.gain_b == 1.0
    export = parsed.nodes["out"].params
    assert (export.format, export.bit_depth, export.sample_rate, export.naming) == ("flac", 24, None, "{track}_{stem}")


def test_references_must_exist():
    broken(SMALL.replace("b: vox.vocals", "b: nope.vocals"), "there is no node 'nope'")
    broken(SMALL.replace("b: vox.vocals", "b: vox.drums"), r"'vox' only emits \['vocals'\]")
    broken(SMALL.replace("[vox.vocals, inst.out]", "[inst.vocals]"), "the output of a subtract node is 'inst.out'")
    broken(SMALL.replace("b: vox.vocals", "b: vox"), "use `mix` or `node.stem`")
    broken(SMALL.replace("b: vox.vocals", "b: out.x"), "export nodes have no outputs")


def test_cycles_are_rejected_at_load_time():
    cyclic = """
nodes:
  a: {op: subtract, inputs: {a: mix, b: b.out}}
  b: {op: subtract, inputs: {a: mix, b: a.out}}
"""
    broken(cyclic, "contains a cycle: a -> b -> a")
    broken("nodes:\n  a: {op: subtract, inputs: {a: mix, b: a.out}}\n", "reads its own output")


def test_structure_is_checked():
    broken("just a string", "must be a mapping")
    broken("nodes: {}", "nodes")
    broken("nodes:\n  mix: {op: export, inputs: [mix]}\n", "'mix' is reserved")
    broken("nodes:\n  'a.b': {op: export, inputs: [mix]}\n", "may only contain")
    broken("nodes:\n  a: {op: frobnicate}\n", "nodes.a")
    broken(SMALL + "  extra: {op: export, inputs: [mix], surprise: 1}\n", "surprise")
    broken("version: 2\n" + SMALL.split("\n", 2)[2], "version")
    broken("nodes: [unclosed", "not valid YAML")


def test_op_parameters_are_checked():
    ensemble = """
nodes:
  a: {op: separate, model: m, targets: [x]}
  b: {op: separate, model: n, targets: [x]}
  e:
    op: ensemble
    inputs: [a.x, b.x]
    params: PARAMS
"""
    assert recipe.loads(ensemble.replace("PARAMS", "{method: median}")).nodes["e"].params.method == "median"
    broken(ensemble.replace("PARAMS", "{method: loudest}"), "method")
    broken(ensemble.replace("PARAMS", "{weights: [1.0]}"), "1 entries for 2 inputs")
    broken(ensemble.replace("PARAMS", "{weights: [0, 0]}"), "not all zero")
    broken(ensemble.replace("inputs: [a.x, b.x]", "inputs: [a.x]"), "inputs")

    export = "nodes:\n  out: {op: export, inputs: [mix], params: PARAMS}\n"
    broken(export.replace("PARAMS", "{format: ogg}"), "format")
    broken(export.replace("PARAMS", "{bit_depth: 20}"), "bit_depth")
    broken(export.replace("PARAMS", "{naming: '{artist}'}"), "naming may only use")
    broken("nodes:\n  out: {op: export, inputs: []}\n", "at least one input")


def test_unreferenced_nodes_are_kept():
    """An analyze node nobody reads still runs."""
    text = SMALL + "  check:\n    op: analyze\n    inputs: {stems: [vox.vocals, inst.out]}\n"
    assert "check" in recipe.loads(text).order()


def test_export_labels():
    parsed = recipe.load(WORKED_EXAMPLE)
    assert list(recipe.export_labels(parsed.nodes["out"])) == ["vox_dry", "drums", "bass", "other", "piano", "guitar"]
    named = recipe.loads("nodes:\n  out: {op: export, inputs: {lead: mix}}\n")
    assert recipe.export_labels(named.nodes["out"]) == {"lead": "mix"}
    clash = recipe.loads("""
nodes:
  a: {op: separate, model: m, targets: [vocals]}
  b: {op: separate, model: n, targets: [vocals]}
  out: {op: export, inputs: [a.vocals, b.vocals]}
""")
    assert list(recipe.export_labels(clash.nodes["out"])) == ["vocals", "b_vocals"]


def test_yaml_round_trip_loses_nothing():
    for text in (SMALL, WORKED_EXAMPLE.read_text(encoding="utf-8")):
        parsed = recipe.loads(text)
        again = recipe.loads(parsed.to_yaml())
        assert again == parsed
        assert again.to_yaml() == parsed.to_yaml()
    assert "gain_b" not in recipe.loads(SMALL).to_yaml(), "defaults are not written out"


def test_json_schema_describes_every_op():
    schema = recipe.json_schema()
    text = str(schema)
    for op in ("separate", "subtract", "ensemble", "postprocess", "analyze", "export"):
        assert f"'const': '{op}'" in text
    assert schema["properties"]["nodes"]["type"] == "object"


def test_backend_param_schema():
    from stemlab.backends.base import ParamSpec

    schema = recipe.backend_param_schema(
        {
            "overlap": ParamSpec("int", 2, "Overlap", minimum=1, maximum=32),
            "dtype": ParamSpec("enum", "auto", "Precision", choices=("auto", "fp16", "fp32")),
            "tta": ParamSpec("bool", False, "TTA"),
        }
    )
    assert schema["properties"]["overlap"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 32,
        "default": 2,
        "description": "Overlap",
    }
    assert schema["properties"]["dtype"]["enum"] == ["auto", "fp16", "fp32"]
    assert schema["properties"]["tta"]["type"] == "boolean"
