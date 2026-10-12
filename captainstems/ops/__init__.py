"""
Node operations. Each module has `run(ctx, name, node, plan) -> OpResult`,
where `ctx` is the runner's RunContext and `plan` the node's resolved settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class OpResult:
    """What a node produced."""

    #: Output name -> float32 audio of shape (channels, samples)
    stems: dict[str, np.ndarray] = field(default_factory=dict)
    #: Details for run.json: metrics, written files, warnings
    info: dict = field(default_factory=dict)
