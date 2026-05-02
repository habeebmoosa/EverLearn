"""
pipelines/code_reviewer.py — CodeReviewerPipeline

Iteratively improves code review feedback for any code snippet, diff,
or PR description. Each iteration adds what was missed and refines
severity/actionability until the review is comprehensive.

Per-iteration flow:
  Plan (what to check) → Review (write comments)
  [Ratchet evaluates with ReviewEvaluatorAgent separately]

Registers as pipeline_id = "code_reviewer".
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

from orchestrator.types import Artifact, EvaluationResult, IterationResult
from pipelines.base import BasePipeline
from sub_agents.code_reviewer_agents import (
    code_planner_agent,
    code_reviewer_agent,
    review_evaluator_agent,
)

logger = logging.getLogger(__name__)

# ADK sequential pipeline: Plan → Review
review_iteration_pipeline = SequentialAgent(
    name="review_iteration_pipeline",
    description="Runs one code review iteration: plan what to check then write the review.",
    sub_agents=[code_planner_agent, code_reviewer_agent],
)

_APP_NAME = "code_reviewer"


def _extract_code_content(request: Any) -> str:
    """Combine data_sources into a single code/diff string for the agents."""
    sources = getattr(request, "data_sources_list", []) or []
    if not sources:
        return ""
    parts = []
    for i, ds in enumerate(sources, 1):
        label = ds.get("label") or ds.get("type", "source")
        content = ds.get("content", "")
        if len(content) > 20000:
            content = content[:20000] + "\n... [truncated]"
        parts.append(f"--- {label} ---\n{content}")
    return "\n\n".join(parts)


def _build_state(
    request: Any,
    iteration: int,
    max_iterations: int,
    best_review: Optional[str],
    session: Dict[str, Any],
) -> Dict[str, str]:
    inputs = getattr(request, "inputs", {}) or {}
    previous_gaps = ""
    if session.get("iterations"):
        previous_gaps = session["iterations"][-1].get("summary", "")

    code_content = _extract_code_content(request)

    return {
        "task_label": request.label,
        "language": str(inputs.get("language", "unknown")),
        "focus": str(inputs.get("focus", "general correctness and security")),
        "review_level": str(inputs.get("review_level", "thorough")),
        "code_content": code_content or "(No code provided — review from description only)",
        "iteration_number": str(iteration),
        "max_iterations": str(max_iterations),
        "previous_best_review": best_review or "No previous review. This is the first iteration.",
        "previous_gaps": previous_gaps or "First iteration — no gaps yet.",
        "review_plan": "",
        "code_review": "",
        "review_evaluation": "",
        "new_review": "",
    }


class CodeReviewerPipeline(BasePipeline):
    """Iterative code review pipeline.

    Works on any code snippet, git diff, or PR description.
    Each iteration adds missed findings and sharpens severity/actionability.
    """

    plugin_id = "code_reviewer"
    display_name = "Code Reviewer"
    description = (
        "Iteratively improve code review feedback for any snippet, diff, or PR. "
        "Each pass finds more issues, refines severity, and adds missing fixes."
    )
    output_label = "Review Comments"

    # ── Metadata interface ─────────────────────────────────────────────────

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "title": "PR / Change Description",
                    "description": "e.g. 'Add JWT authentication to login endpoint' or 'Refactor data pipeline'",
                },
                "language": {
                    "type": "string",
                    "title": "Language / Stack",
                    "description": "e.g. Python, TypeScript, Java, Go",
                },
                "focus": {
                    "type": "string",
                    "title": "Review Focus",
                    "description": "e.g. security, performance, correctness, style, all",
                },
                "review_level": {
                    "type": "string",
                    "title": "Review Depth",
                    "enum": ["quick", "thorough", "exhaustive"],
                    "default": "thorough",
                },
            },
            "required": ["label"],
        }

    def get_display_config(self) -> dict:
        return {
            "label_placeholder": "e.g. Add JWT auth to login endpoint, Refactor database layer...",
            "max_iterations_default": 3,
            "depth_options": ["quick", "standard", "deep"],
            "show_web_search": False,
            "show_data_sources": True,
            "show_focus_areas": False,
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
        best_review = best_artifact.content if best_artifact else None
        state = _build_state(request, iteration, max_iterations, best_review, session)

        runner = InMemoryRunner(agent=review_iteration_pipeline, app_name=_APP_NAME)
        adk_session = await runner.session_service.create_session(
            app_name=_APP_NAME, user_id="review_user", state=state
        )

        trigger_text = (
            f"Execute code review iteration {iteration} of {max_iterations}.\n"
            f"PR/Change: {request.label}\n"
            f"Language: {state['language']}\n"
            f"Focus: {state['focus']}\n"
            f"Review depth: {state['review_level']}\n"
            f"Previous review exists: {'Yes' if best_review else 'No'}"
        )
        if state["code_content"] and state["code_content"] != "(No code provided — review from description only)":
            trigger_text += f"\n\n## Code / Diff to Review\n\n{state['code_content']}"

        trigger = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=trigger_text)],
        )

        step_names = {
            "code_planner_agent": "Planning review strategy...",
            "code_reviewer_agent": "Writing review comments...",
        }

        collected_responses: List[str] = []
        new_review: Optional[str] = None

        try:
            async for event in runner.run_async(
                user_id="review_user",
                session_id=adk_session.id,
                new_message=trigger,
            ):
                author = getattr(event, "author", None)
                if author in step_names:
                    session["current_step"] = step_names[author]
                    session["updated_at"] = _now()
                    logger.info(f"[{session_id}] Iter {iteration}: {step_names[author]}")
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            collected_responses.append(part.text)
                if partial is not None:
                    partial["collected_responses"] = list(collected_responses)
        except Exception as e:
            logger.error(f"[{session_id}] CodeReviewer pipeline error iter {iteration}: {e}")

        # Extract code_review from session state
        try:
            final_state = await runner.session_service.get_session(
                app_name=_APP_NAME, user_id="review_user", session_id=adk_session.id
            )
            if final_state and final_state.state:
                draft = final_state.state.get("code_review", "")
                if draft and len(draft) > 50:
                    new_review = draft
        except Exception as e:
            logger.warning(f"[{session_id}] Could not extract code_review from state: {e}")

        # Fallback: pick longest markdown response
        if not new_review:
            candidates = [
                r for r in collected_responses
                if r and len(r) > 100 and not r.strip().startswith("{")
            ]
            if candidates:
                new_review = max(candidates, key=len)

        iter_details: Dict[str, Any] = {
            "search_queries": [],
            "sources_collected": [],
            "total_sources": len(getattr(request, "data_sources_list", []) or []),
            "urls_fetched": 0,
        }

        if partial is not None:
            partial["iteration_details"] = iter_details

        if not new_review:
            return IterationResult(artifact=None, iteration_details=iter_details, raw_outputs=collected_responses)

        return IterationResult(
            artifact=Artifact(content=new_review, content_type="text/markdown"),
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
        best_review = best_artifact.content if best_artifact else None
        inputs = getattr(request, "inputs", {}) or {}

        eval_state = {
            "task_label": request.label,
            "language": str(inputs.get("language", "unknown")),
            "focus": str(inputs.get("focus", "general")),
            "code_content": _extract_code_content(request),
            "new_review": new_artifact.content,
            "previous_best_review": best_review or "",
            "iteration_number": str(iteration),
        }

        eval_app = _APP_NAME + "_eval"
        runner = InMemoryRunner(agent=review_evaluator_agent, app_name=eval_app)
        adk_session = await runner.session_service.create_session(
            app_name=eval_app, user_id="review_eval_user", state=eval_state
        )

        trigger = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(
                text=(
                    f"Evaluate the code review for iteration {iteration}.\n"
                    f"PR/Change: {request.label}\n"
                    f"Previous best score: {best_score}\n"
                    f"First iteration: {'Yes' if not best_review else 'No'}"
                )
            )],
        )

        try:
            async for _ in runner.run_async(
                user_id="review_eval_user",
                session_id=adk_session.id,
                new_message=trigger,
            ):
                pass
        except Exception as e:
            logger.error(f"[{session_id}] Review evaluator error iter {iteration}: {e}")
            return EvaluationResult(
                new_score=max(int(best_score), 1),
                previous_score=int(best_score),
                is_improvement=False,
                summary="Evaluation failed — keeping previous best.",
            )

        # Extract structured evaluation
        try:
            final_state = await runner.session_service.get_session(
                app_name=eval_app, user_id="review_eval_user", session_id=adk_session.id
            )
            raw = (final_state.state or {}).get("review_evaluation", {})
            if isinstance(raw, str):
                cleaned = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r"```$", "", cleaned.strip())
                raw = json.loads(cleaned)
            if isinstance(raw, dict):
                return EvaluationResult(
                    new_score=float(raw.get("new_score", 0)),
                    previous_score=float(raw.get("previous_score", best_score)),
                    is_improvement=bool(raw.get("is_improvement", False)),
                    summary=str(raw.get("improvement_summary", "")),
                    scoring_breakdown=raw.get("scoring_breakdown"),
                    remaining_gaps=raw.get("remaining_gaps"),
                )
        except Exception as e:
            logger.warning(f"[{session_id}] Could not parse ReviewEvaluation: {e}")

        return EvaluationResult(
            new_score=max(int(best_score) + 5, 50),
            previous_score=int(best_score),
            is_improvement=not bool(best_artifact),
            summary="Review evaluation parsed with defaults.",
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
