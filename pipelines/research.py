"""
pipelines/research.py — ResearchPipeline

Reference implementation of a pipeline plugin.
Wraps the existing research iteration + quality evaluator functions
and exposes the full plugin metadata interface so the UI can render
a dynamic form for research tasks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from orchestrator.types import Artifact, EvaluationResult, IterationResult
from pipelines.base import BasePipeline


class ResearchPipeline(BasePipeline):
    """Iterative research pipeline — autonomously researches any topic
    via a Plan → Collect → Analyze → Write → Evaluate ratchet loop."""

    plugin_id = "research"
    display_name = "Research"
    description = (
        "Autonomously research any topic across the web, files, and your own data. "
        "Each iteration builds on the previous best — quality can only improve."
    )
    output_label = "Research Report"

    def __init__(self, *, run_iteration_fn: Callable, evaluate_fn: Callable):
        self._run_iteration_fn = run_iteration_fn
        self._evaluate_fn = evaluate_fn

    # ── Metadata interface ─────────────────────────────────────────────────

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "title": "Research Topic",
                    "description": "What topic should be researched?",
                },
                "focus_areas": {
                    "type": "string",
                    "title": "Focus Areas",
                    "description": "Comma-separated subtopics to prioritise (optional)",
                },
                "enable_web_search": {
                    "type": "boolean",
                    "title": "Enable Web Search",
                    "default": True,
                    "description": "Allow the agent to search the web for sources",
                },
            },
            "required": ["label"],
        }

    def get_display_config(self) -> dict:
        return {
            "label_placeholder": (
                "e.g. The impact of quantum computing on modern cryptography"
            ),
            "max_iterations_default": 5,
            "depth_options": ["quick", "standard", "deep"],
            "show_web_search": True,
            "show_data_sources": True,
            "show_focus_areas": True,
        }

    # ── Core contract ──────────────────────────────────────────────────────

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
    ) -> IterationResult:
        best_report = best_artifact.content if best_artifact else None
        new_report, iter_details, collected_responses = await self._run_iteration_fn(
            session_id=session_id,
            session=session,
            iteration=iteration,
            max_iterations=max_iterations,
            topic=request.topic,                                          # _TaskContext.topic → request.label
            data_sources_list=getattr(request, "data_sources_list", None) or [],
            focus_areas_str=getattr(request, "focus_areas_str", "") or "",
            best_report=best_report,
            enable_web_search=getattr(request, "enable_web_search", True),
            _partial_results=partial,
        )

        if partial is not None:
            partial["iteration_details"] = iter_details

        if not new_report:
            return IterationResult(
                artifact=None,
                iteration_details=iter_details,
                raw_outputs=collected_responses,
            )

        return IterationResult(
            artifact=Artifact(content=new_report, content_type="text/markdown"),
            iteration_details=iter_details,
            raw_outputs=collected_responses,
        )

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
    ) -> EvaluationResult:
        best_report = best_artifact.content if best_artifact else None
        evaluation = await self._evaluate_fn(
            session_id=session_id,
            iteration=iteration,
            max_iterations=max_iterations,
            topic=request.topic,
            focus_areas_str=getattr(request, "focus_areas_str", "") or "",
            new_report=new_artifact.content,
            best_report=best_report,
            best_score=best_score,
        )

        return EvaluationResult(
            new_score=float(evaluation.get("new_score", 0)),
            previous_score=float(evaluation.get("previous_score", best_score)),
            is_improvement=bool(evaluation.get("is_improvement", False)),
            summary=str(evaluation.get("improvement_summary", "")),
            scoring_breakdown=evaluation.get("scoring_breakdown"),
            remaining_gaps=evaluation.get("remaining_gaps"),
        )
