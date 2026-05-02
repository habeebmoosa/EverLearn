from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


class SessionState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True)
class Artifact:
    """Primary output of an iteration (e.g. report text)."""

    content: str
    content_type: str = "text/markdown"
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class EvaluationResult:
    new_score: float
    previous_score: float
    is_improvement: bool
    summary: str = ""
    scoring_breakdown: Optional[Dict[str, Any]] = None
    remaining_gaps: Optional[List[str]] = None


@dataclass(frozen=True)
class IterationResult:
    artifact: Optional[Artifact]
    iteration_details: Dict[str, Any]
    raw_outputs: Optional[List[str]] = None


class PipelinePlugin(Protocol):
    """Pluggable pipeline for the ratchet loop."""

    plugin_id: str
    display_name: str

    async def run_iteration(
        self,
        *,
        session_id: str,
        session: Dict[str, Any],
        iteration: int,
        max_iterations: int,
        request: Any,
        best_artifact: Optional[Artifact],
        partial: Optional[Dict[str, Any]] = None,
    ) -> IterationResult: ...

    async def evaluate(
        self,
        *,
        session_id: str,
        iteration: int,
        max_iterations: int,
        request: Any,
        new_artifact: Artifact,
        best_artifact: Optional[Artifact],
        best_score: float,
    ) -> EvaluationResult: ...

