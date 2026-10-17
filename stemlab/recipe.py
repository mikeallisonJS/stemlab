"""
The recipe format: a graph of named nodes, each one operation.

A recipe is a YAML file. Nodes reference the outputs of other nodes as
`node.stem`; `mix` is the implicit source node holding the input file.

    version: 1
    name: vocals-and-instrumental
    nodes:
      vox:
        op: separate
        model: mel-band-roformer-vocals-kim
        targets: [vocals]
      inst:
        op: subtract
        inputs: {a: mix, b: vox.vocals}
      out:
        op: export
        inputs: [vox.vocals, inst.out]

What each kind of node outputs:
    separate     the stems listed in `targets` (all of the model's when omitted)
    subtract     `out`
    ensemble     `out`
    postprocess  `out`
    analyze      `residual`
    export       nothing; it writes files
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MIX = "mix"
NODE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")
ENSEMBLE_METHODS = ("avg", "max_spec", "min_spec", "median")


class RecipeError(Exception):
    """A recipe is malformed or does not fit the installed models."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Inputs -------------------------------------------------------------------------


class AudioInput(_Strict):
    audio: str = Field(MIX, description="What to process: `mix` or `node.stem`")


class SubtractInputs(_Strict):
    a: str = Field(description="The signal to subtract from")
    b: str = Field(description="The signal that is subtracted")


class AnalyzeInputs(_Strict):
    mix: str = Field(MIX, description="The signal the stems should add up to")
    stems: list[str] = Field(min_length=1, description="The stems to check against it")


# Parameters ---------------------------------------------------------------------


class SubtractParams(_Strict):
    gain_b: float = Field(1.0, description="Gain applied to b before subtracting")


class EnsembleParams(_Strict):
    method: Literal["avg", "max_spec", "min_spec", "median"] = Field(
        "avg", description="avg and median combine waveforms; max_spec and min_spec pick per frequency bin"
    )
    weights: list[float] | None = Field(None, description="One weight per input, for avg only")


class AnalyzeParams(_Strict):
    reference: str | None = Field(None, description="Path of a reference stem to score the first stem against (SI-SDR)")


class ExportParams(_Strict):
    format: Literal["flac", "wav", "mp3"] = Field("flac", description="File format")
    bit_depth: Literal[16, 24, 32] = Field(24, description="Bits per sample; 32 is float and WAV only")
    sample_rate: int | None = Field(
        None, ge=8000, le=384000, description="Output sample rate; the source's when omitted"
    )
    naming: str = Field("{track}_{stem}", description="File name template: {track}, {stem}, {node}, {recipe}")
    bitrate: Literal["128k", "192k", "256k", "320k"] = Field("320k", description="MP3 bitrate")

    @field_validator("naming")
    @classmethod
    def _valid_template(cls, value: str) -> str:
        try:
            value.format(track="t", stem="s", node="n", recipe="r")
        except (KeyError, IndexError, ValueError) as e:
            raise ValueError(f"naming may only use {{track}}, {{stem}}, {{node}} and {{recipe}} ({e})") from None
        if not value.strip():
            raise ValueError("naming must not be empty")
        return value


# Nodes --------------------------------------------------------------------------


class SeparateNode(_Strict):
    """Runs one model on one input and emits the stems asked for."""

    op: Literal["separate"]
    model: str = Field(description="Registry id of the model")
    inputs: AudioInput = Field(default_factory=AudioInput)
    targets: list[str] | None = Field(None, description="Stems to emit; all of the model's when omitted")
    params: dict[str, Any] = Field(default_factory=dict, description="Inference knobs of the model's backend")


class SubtractNode(_Strict):
    """a - b, sample-exact: the clean way to get an instrumental from a vocal model."""

    op: Literal["subtract"]
    inputs: SubtractInputs
    params: SubtractParams = Field(default_factory=SubtractParams)


class EnsembleNode(_Strict):
    """Combines several versions of the same stem."""

    op: Literal["ensemble"]
    inputs: list[str] = Field(min_length=2)
    params: EnsembleParams = Field(default_factory=EnsembleParams)

    @model_validator(mode="after")
    def _weights_match(self):
        weights = self.params.weights
        if weights is not None:
            if len(weights) != len(self.inputs):
                raise ValueError(f"weights has {len(weights)} entries for {len(self.inputs)} inputs")
            if any(weight < 0 for weight in weights) or sum(weights) <= 0:
                raise ValueError("weights must be non-negative and not all zero")
        return self


class PostprocessNode(_Strict):
    """Runs a single-purpose model (dereverb, denoise, de-echo) on one stem."""

    op: Literal["postprocess"]
    model: str = Field(description="Registry id of the model")
    inputs: AudioInput
    target: str | None = Field(None, description="Which of the model's stems to keep; its first when omitted")
    params: dict[str, Any] = Field(default_factory=dict, description="Inference knobs of the model's backend")


class AnalyzeNode(_Strict):
    """Computes residual = mix - sum(stems), with levels and an optional SI-SDR score."""

    op: Literal["analyze"]
    inputs: AnalyzeInputs
    params: AnalyzeParams = Field(default_factory=AnalyzeParams)


class ExportNode(_Strict):
    """Writes stems to files."""

    op: Literal["export"]
    inputs: list[str] | dict[str, str] = Field(description="Stems to write; a mapping names them explicitly")
    params: ExportParams = Field(default_factory=ExportParams)

    @field_validator("inputs")
    @classmethod
    def _not_empty(cls, value):
        if not value:
            raise ValueError("export needs at least one input")
        return value


Node = Annotated[
    SeparateNode | SubtractNode | EnsembleNode | PostprocessNode | AnalyzeNode | ExportNode,
    Field(discriminator="op"),
]

OUTPUT_NAME = {"subtract": "out", "ensemble": "out", "postprocess": "out", "analyze": "residual"}


class Recipe(_Strict):
    version: Literal[1] = 1
    name: str = "recipe"
    defaults: dict[str, Any] = Field(
        default_factory=dict, description="Inference knobs applied to every separate and postprocess node"
    )
    nodes: dict[str, Node] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_graph(self):
        for name in self.nodes:
            if name == MIX:
                raise ValueError("'mix' is reserved for the input file and cannot be a node name")
            if not NODE_NAME.match(name):
                raise ValueError(f"node name '{name}' may only contain letters, digits, '_' and '-'")
        for name, node in self.nodes.items():
            for reference in node_references(node):
                source, _stem = split_reference(reference)
                if source != MIX and source not in self.nodes:
                    raise ValueError(f"node '{name}' reads '{reference}', but there is no node '{source}'")
                if source == name:
                    raise ValueError(f"node '{name}' reads its own output")
                if source != MIX:
                    self._check_stem(name, reference)
        self.order()  # rejects cycles
        return self

    def _check_stem(self, reader: str, reference: str) -> None:
        """Checks that need no registry: a stem must exist on the node producing it."""
        source, stem = split_reference(reference)
        producer = self.nodes[source]
        if producer.op == "export":
            raise ValueError(f"node '{reader}' reads '{reference}', but export nodes have no outputs")
        if producer.op == "separate":
            if producer.targets is not None and stem not in producer.targets:
                raise ValueError(f"node '{reader}' reads '{reference}', but '{source}' only emits {producer.targets}")
        elif stem != OUTPUT_NAME[producer.op]:
            raise ValueError(
                f"node '{reader}' reads '{reference}', but the output of a {producer.op} node is "
                f"'{source}.{OUTPUT_NAME[producer.op]}'"
            )

    def order(self) -> list[str]:
        """Node names in an order where every node comes after the ones it reads (stable)."""
        depends = {
            name: sorted({split_reference(ref)[0] for ref in node_references(node)} - {MIX})
            for name, node in self.nodes.items()
        }
        ordered: list[str] = []
        state: dict[str, int] = {}

        def visit(name: str, trail: tuple[str, ...]) -> None:
            if state.get(name) == 2:
                return
            if state.get(name) == 1:
                cycle = " -> ".join(trail[trail.index(name) :] + (name,))
                raise ValueError(f"the recipe contains a cycle: {cycle}")
            state[name] = 1
            for dependency in depends[name]:
                visit(dependency, trail + (name,))
            state[name] = 2
            ordered.append(name)

        for name in self.nodes:
            visit(name, ())
        return ordered

    def to_yaml(self) -> str:
        """Serialize, leaving out everything that is at its default."""
        data = self.model_dump(exclude_defaults=True, mode="json")
        data = {
            "version": self.version,
            "name": self.name,
            **{k: v for k, v in data.items() if k not in ("version", "name")},
        }
        for name, node in self.nodes.items():
            data["nodes"][name] = {"op": node.op, **{k: v for k, v in data["nodes"][name].items() if k != "op"}}
        return yaml.safe_dump(data, sort_keys=False, default_flow_style=None, width=100, allow_unicode=True)


def split_reference(reference: str) -> tuple[str, str]:
    """`mix` -> ("mix", "mix"); `node.stem` -> ("node", "stem")."""
    if reference == MIX:
        return MIX, MIX
    node, dot, stem = reference.partition(".")
    if not dot or not node or not stem or "." in stem:
        raise ValueError(f"'{reference}' is not a valid input: use `mix` or `node.stem`")
    return node, stem


def node_references(node) -> list[str]:
    """Every input reference of a node, in order."""
    inputs = node.inputs
    if isinstance(inputs, list):
        return list(inputs)
    if isinstance(inputs, dict):
        return list(inputs.values())
    if isinstance(inputs, AnalyzeInputs):
        return [inputs.mix, *inputs.stems]
    if isinstance(inputs, SubtractInputs):
        return [inputs.a, inputs.b]
    return [inputs.audio]


def export_labels(node: ExportNode) -> dict[str, str]:
    """
    Label -> reference for the stems an export node writes. A stem named `out`
    takes the name of its node (`drums.out` is written as "drums").
    """
    if isinstance(node.inputs, dict):
        return dict(node.inputs)
    labels: dict[str, str] = {}
    for reference in node.inputs:
        source, stem = split_reference(reference)
        label = source if stem in ("out", MIX) else stem
        if label in labels:
            label = f"{source}_{stem}"
        labels[label] = reference
    return labels


def _format_errors(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        location = ".".join(
            str(part)
            for part in item["loc"]
            if part not in ("separate", "subtract", "ensemble", "postprocess", "analyze", "export")
        )
        message = item["msg"].removeprefix("Value error, ")
        lines.append(f"  {location}: {message}" if location else f"  {message}")
    return "\n".join(lines)


def parse(data: Any) -> Recipe:
    """Validate recipe data (as loaded from YAML or sent by the UI)."""
    if not isinstance(data, dict):
        raise RecipeError("A recipe must be a mapping with `nodes`")
    try:
        return Recipe.model_validate(data)
    except ValidationError as e:
        raise RecipeError("Invalid recipe:\n" + _format_errors(e)) from None


def loads(text: str) -> Recipe:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise RecipeError(f"The recipe is not valid YAML: {e}") from None
    return parse(data)


def load(path: str | Path) -> Recipe:
    path = Path(path)
    if not path.is_file():
        raise RecipeError(f"Recipe not found: {path}")
    return loads(path.read_text(encoding="utf-8"))


def json_schema() -> dict:
    """JSON Schema of the recipe format, for the UI's form generation."""
    return Recipe.model_json_schema()


def backend_param_schema(specs: dict) -> dict:
    """JSON Schema for the `params` of a separate or postprocess node on one backend."""
    properties = {}
    for name, spec in specs.items():
        if spec.type == "enum":
            entry: dict[str, Any] = {"type": "string", "enum": list(spec.choices or ())}
        elif spec.type == "bool":
            entry = {"type": "boolean"}
        else:
            entry = {"type": "integer" if spec.type == "int" else "number"}
            if spec.minimum is not None:
                entry["minimum"] = spec.minimum
            if spec.maximum is not None:
                entry["maximum"] = spec.maximum
        entry["default"] = spec.default
        entry["description"] = spec.description
        properties[name] = entry
    return {"type": "object", "additionalProperties": False, "properties": properties}


__all__ = [
    "MIX",
    "Recipe",
    "RecipeError",
    "SeparateNode",
    "SubtractNode",
    "EnsembleNode",
    "PostprocessNode",
    "AnalyzeNode",
    "ExportNode",
    "ExportParams",
    "backend_param_schema",
    "export_labels",
    "json_schema",
    "load",
    "loads",
    "node_references",
    "parse",
    "split_reference",
]
