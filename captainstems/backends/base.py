"""
The interface every separation backend implements.

A backend turns a model manifest into a loaded model; a model separates one
piece of audio. Backends declare the inference parameters they honor, so the
recipe validator and the UI only offer knobs that do something.
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

BACKENDS = ("msst", "demucs", "onnx")

ProgressFn = Callable[[float], None]


class Cancelled(Exception):
    """The run was cancelled by the user."""


class BackendError(Exception):
    """A backend could not load or run a model."""


@dataclass(frozen=True)
class ParamSpec:
    """One inference knob: its type, default and limits."""

    type: str  # "int", "float", "bool" or "enum"
    default: Any
    description: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple | None = None

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}

    def coerce(self, name: str, value: Any) -> Any:
        """Validate a value given in a recipe and convert it to the declared type."""
        if self.type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be true or false")
            return value
        if self.type == "enum":
            if value not in (self.choices or ()):
                raise ValueError(f"{name} must be one of {', '.join(map(str, self.choices or ()))}")
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a number")
        if self.type == "int":
            if float(value) != int(value):
                raise ValueError(f"{name} must be a whole number")
            value = int(value)
        else:
            value = float(value)
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{name} must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{name} must be at most {self.maximum}")
        return value


# Knobs shared by every backend. Device and dtype are resolved by the runner.
COMMON_PARAMS: dict[str, ParamSpec] = {
    "device": ParamSpec("enum", "auto", "Where to run the model", choices=("auto", "cuda", "mps", "cpu")),
    "dtype": ParamSpec(
        "enum", "auto", "Numeric precision; auto is fp16 on CUDA and fp32 elsewhere", choices=("auto", "fp16", "fp32")
    ),
    "normalize": ParamSpec("bool", False, "Normalize the input before separation and undo it afterwards"),
}


class Model(ABC):
    """A loaded model, ready to separate audio."""

    #: Stems in the model's native output order
    stems: list[str]
    #: Sample rate the model works at
    sample_rate: int

    @abstractmethod
    def separate(
        self, audio: np.ndarray, sample_rate: int, params: dict, progress: ProgressFn | None = None, cancel: Any = None
    ) -> dict[str, np.ndarray]:
        """
        Separate audio into stems.

        Args:
            audio: float32 of shape (channels, samples), already at the model's sample rate
            sample_rate: Sample rate of `audio`
            params: Fully resolved inference parameters
            progress: Called with a fraction between 0 and 1
            cancel: Object with `is_set()`; checked between chunks

        Returns:
            Stem name -> float32 audio with the shape of the input

        Raises:
            Cancelled: if `cancel` was set
        """

    def close(self) -> None:  # noqa: B027 - optional hook, not every model holds resources
        """Release the model's memory."""


class Backend(ABC):
    """Loads models of one family."""

    name: str
    #: Parameter name -> spec, for every knob this backend honors
    supported_params: dict[str, ParamSpec]

    @abstractmethod
    def load(self, manifest, params: dict) -> Model:
        """Load the model described by a registry manifest onto the device in `params`."""

    @abstractmethod
    def version(self) -> dict:
        """Versions of the libraries behind this backend, recorded in run.json."""

    def device_defaults(self, device: str, vram_mb: int | None) -> dict:
        """Starting values that depend on the hardware (batch size, overlap)."""
        return {}

    def model_defaults(self, manifest) -> dict:
        """Values the model's own config file asks for (its chunk size)."""
        return {}

    def available(self) -> str | None:
        """None if the backend can run, otherwise the reason it cannot."""
        try:
            self.version()
        except Exception as e:
            return str(e)
        return None


_instances: dict[str, Backend] = {}


def get_backend(name: str) -> Backend:
    """The backend with the given name. Imports its libraries on first use."""
    if name not in BACKENDS:
        raise BackendError(f"Unknown backend '{name}' (use one of {', '.join(BACKENDS)})")
    if name not in _instances:
        module = importlib.import_module(f"captainstems.backends.{name}")
        _instances[name] = module.create()
    return _instances[name]


def supported_params(name: str) -> dict[str, ParamSpec]:
    return get_backend(name).supported_params


def backend_versions() -> dict:
    """Versions of every backend, or the reason it is unavailable."""
    versions = {}
    for name in BACKENDS:
        try:
            versions[name] = get_backend(name).version()
        except Exception as e:
            versions[name] = {"error": str(e)}
    return versions


def check_cancel(cancel: Any) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()
