from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    body_id: str
    target: Tuple[float, ...]
    required_modalities: Tuple[str, ...] = ("joint_position",)
    tolerance: float = 0.01
    max_attempts: int = 2
    timeout_s: float = 5.0


@dataclass(frozen=True)
class EmbodimentSpec:
    body_id: str
    calibration_version: str
    limits: Tuple[Tuple[float, float], ...]
    modalities: Tuple[str, ...]
    simulated: bool = True


@dataclass(frozen=True)
class Capability:
    name: str
    version: str
    mode: str
    simulated_only: bool = True


@dataclass
class Episode:
    task_id: str
    attempt: int
    body_id: str
    calibration_version: str
    observations: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


@dataclass(frozen=True)
class Review:
    verdict: str
    score: float
    reason: str
    metrics: Dict[str, float] = field(default_factory=dict)
    next_step: str = "stop"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    layer: str
    parent_version: str
    source_task_id: str
    proposal: str
    status: str = "proposed"


def record(value):
    return asdict(value)
