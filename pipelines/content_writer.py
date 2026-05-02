"""
pipelines/content_writer.py — ContentWriterPipeline

Iteratively improves any written content (blog posts, emails, policies,
briefs, reports, etc.) against a user-defined quality rubric.

Pipeline per iteration:
  Plan → Write → [Ratchet evaluates in separate evaluate() call]

Each iteration:
  1. ContentPlannerAgent   — analyses task + previous draft + gaps
  2. ContentWriterAgent    — writes or improves the content
  3. (separate) ContentEvaluatorAgent — scores and drives the ratchet decision

Registers as pipeline_id = "content_writer".
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner
from google import genai as genai_types

from orchestrator.types import Artifact, EvaluationResult, IterationResult
from pipelines.base import BasePipeline
from sub_agents.content_writer_agents import (
    content_evaluator_agent,
    content_planner_agent,
    content_writer_agent,
    ContentEvaluation,
)

logger = logging.getLogger(__name__)

# ── ADK sequential pipeline: Plan → Write ─────────────────────────────────────
content_iteration_pipeline = SequentialAgent(
    name="content_iteration_pipeline",
    description="Runs one content-writing iteration: plan then write/improve.",
    sub_agents=[content_planner_agent, content_writer_agent],
)

_APP_NAME = "content_writer"


def _build_session_state(
    request: Any,
    iteration: int,
    max_iterations: int,
    best_content: Optional[str],
    session: Dict[str, Any],
) -> Dict[str, str]:
    """Build the ADK session state dict for this iteration."""
    previous_gaps = ""
    if session.get("iterations"):
        last = session["iterations"][-1]
        previous_gaps = last.get("summary", "")

    inputs = getattr(request, "inputs", {}) or {}
    data_sources = getattr(request, "data_sources_list", []) or []

    # Serialise data sources as readable text
    ds_text = ""
    if data_sources:
        parts = []
        for i, ds in enumerate(data_sources, 1):
            label = ds.get("label") or ds.get("type", "source")
            content = ds.get("content", "")
            if len(content) > 10000:
                content = content[:10000] + "\n... [truncated]"
            parts.append(f"--- Source {i} ({label}) ---\n{content}")
        ds_text = "\n\n".join(parts)

    return {
        "task_label": request.label,
        "content_type": str(inputs.get("content_type", "general")),
        "target_audience": str(inputs.get("target_audience", "general audience")),
        "tone": str(inputs.get("tone", "professional")),
        "rubric": str(inputs.get("rubric", "Clear, complete, and well-structured.")),
        "iteration_number": str(iteration),
        "max_iterations": str(max_iterations),
        "previous_best_content": best_content or "No previous draft. This is the first iteration.",
        "previous_gaps": previous_gaps or "First iteration — no gaps yet.",
        "data_sources": ds_text,
        # Will be populated by evaluator for next iteration's reference
        "new_content": "",
        "content_plan": "",
        "content_draft": "",
        "content_evaluation": "",
    }


class ContentWriterPipeline(BasePipeline):
    """Iterative content improvement pipeline.

    Works for any written artefact: blog posts, emails, policies,
    investor updates, product briefs, technical docs, etc.
    """

    plugin_id = "content_writer"
    display_name = "Content Writer"
    description = (
        "Iteratively write and improve any content — blog posts, emails, "
        "policies, briefs, reports — against your quality rubric. "
        "Each iteration builds on the best draft so far."
    )
    output_label = "Content Draft"

    # ── Metadata interface ─────────────────────────────────────────────────

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "title": "What to Write",
                    "description": "e.g. 'Q3 investor update email' or 'Python async best practices blog post'",
                },
                "content_type": {
                    "type": "string",
                    "title": "Content Type",
                    "enum": ["blog_post", "email", "policy", "brief", "report", "social_post", "other"],
                    "default": "blog_post",
                },
                "target_audience": {
                    "type": "string",
                    "title": "Target Audience",
                    "description": "e.g. 'senior engineers', 'non-technical investors', 'general public'",
                },
                "tone": {
                    "type": "string",
                    "title": "Tone",
                    "enum": ["professional", "casual", "technical", "persuasive", "friendly", "formal"],
                    "default": "professional",
                },
                "rubric": {
                    "type": "string",
                    "title": "Quality Rubric",
                    "description": "What makes a great version of this content? e.g. 'clear, data-driven, under 300 words'",
                },
            },
            "required": ["label"],
        }

    def get_display_config(self) -> dict:
        return {
            "label_placeholder": "e.g. Q3 investor update email, Python async blog post...",
            "max_iterations_default": 4,
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
        best_content = best_artifact.content if best_artifact else None

        state = _build_session_state(request, iteration, max_iterations, best_content, session)

        runner = InMemoryRunner(agent=content_iteration_pipeline, app_name=_APP_NAME)
        adk_session = await runner.session_service.create_session(
            app_name=_APP_NAME,
            user_id="content_user",
            state=state,
        )

        trigger_text = (
            f"Execute content writing iteration {iteration} of {max_iterations}.\n"
            f"Task: {request.label}\n"
            f"Content type: {state['content_type']}\n"
            f"Audience: {state['target_audience']}\n"
            f"Tone: {state['tone']}\n"
            f"Quality rubric: {state['rubric']}\n"
            f"Previous draft exists: {'Yes' if best_content else 'No'}"
        )
        if state["data_sources"]:
            trigger_text += f"\n\n## Reference Material\n\n{state['data_sources']}"

        trigger = genai_types.protos.Content(
            role="user",
            parts=[genai_types.protos.Part(text=trigger_text)],
        )

        step_names = {
            "content_planner_agent": "Planning content strategy...",
            "content_writer_agent": "Writing content draft...",
        }

        collected_responses: List[str] = []
        new_content: Optional[str] = None

        try:
            async for event in runner.run_async(
                user_id="content_user",
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
            logger.error(f"[{session_id}] ContentWriter pipeline error iter {iteration}: {e}")

        # Extract content_draft from session state
        try:
            final_state = await runner.session_service.get_session(
                app_name=_APP_NAME, user_id="content_user", session_id=adk_session.id
            )
            if final_state and final_state.state:
                draft = final_state.state.get("content_draft", "")
                if draft and len(draft) > 50:
                    new_content = draft
        except Exception as e:
            logger.warning(f"[{session_id}] Could not extract content_draft from state: {e}")

        # Fallback: pick longest non-JSON response
        if not new_content:
            candidates = [r for r in collected_responses if r and len(r) > 100 and not r.strip().startswith("{")]
            if candidates:
                new_content = max(candidates, key=len)

        iter_details: Dict[str, Any] = {
            "search_queries": [],
            "sources_collected": [],
            "total_sources": len(getattr(request, "data_sources_list", []) or []),
            "urls_fetched": 0,
        }

        if partial is not None:
            partial["iteration_details"] = iter_details

        if not new_content:
            return IterationResult(artifact=None, iteration_details=iter_details, raw_outputs=collected_responses)

        return IterationResult(
            artifact=Artifact(content=new_content, content_type="text/markdown"),
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
        best_content = best_artifact.content if best_artifact else None
        inputs = getattr(request, "inputs", {}) or {}

        eval_state = {
            "task_label": request.label,
            "content_type": str(inputs.get("content_type", "general")),
            "target_audience": str(inputs.get("target_audience", "general audience")),
            "tone": str(inputs.get("tone", "professional")),
            "rubric": str(inputs.get("rubric", "Clear, complete, and well-structured.")),
            "new_content": new_artifact.content,
            "previous_best_content": best_content or "",
            "iteration_number": str(iteration),
        }

        runner = InMemoryRunner(agent=content_evaluator_agent, app_name=_APP_NAME + "_eval")
        adk_session = await runner.session_service.create_session(
            app_name=_APP_NAME + "_eval",
            user_id="content_eval_user",
            state=eval_state,
        )

        trigger = genai_types.protos.Content(
            role="user",
            parts=[genai_types.protos.Part(
                text=(
                    f"Evaluate the new content draft for iteration {iteration}.\n"
                    f"Task: {request.label}\n"
                    f"Previous best score: {best_score}\n"
                    f"Is first iteration: {'Yes' if not best_content else 'No'}"
                )
            )],
        )

        try:
            async for _ in runner.run_async(
                user_id="content_eval_user",
                session_id=adk_session.id,
                new_message=trigger,
            ):
                pass
        except Exception as e:
            logger.error(f"[{session_id}] ContentWriter evaluator error iter {iteration}: {e}")
            return EvaluationResult(
                new_score=max(int(best_score), 1),
                previous_score=int(best_score),
                is_improvement=False,
                summary="Evaluation failed — keeping previous best.",
            )

        # Extract structured evaluation from session state
        try:
            final_state = await runner.session_service.get_session(
                app_name=_APP_NAME + "_eval",
                user_id="content_eval_user",
                session_id=adk_session.id,
            )
            raw_eval = (final_state.state or {}).get("content_evaluation", {})

            # ADK may store it as dict or already-parsed Pydantic model
            if isinstance(raw_eval, str):
                import re
                # Strip markdown code fences if present
                cleaned = re.sub(r"^```[a-z]*\n?", "", raw_eval.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r"```$", "", cleaned.strip())
                raw_eval = json.loads(cleaned)

            if isinstance(raw_eval, dict):
                return EvaluationResult(
                    new_score=float(raw_eval.get("new_score", 0)),
                    previous_score=float(raw_eval.get("previous_score", best_score)),
                    is_improvement=bool(raw_eval.get("is_improvement", False)),
                    summary=str(raw_eval.get("improvement_summary", "")),
                    scoring_breakdown=raw_eval.get("scoring_breakdown"),
                    remaining_gaps=raw_eval.get("remaining_gaps"),
                )
        except Exception as e:
            logger.warning(f"[{session_id}] Could not parse ContentEvaluation: {e}")

        # Fallback: treat as improvement if no previous best
        return EvaluationResult(
            new_score=max(int(best_score) + 5, 50),
            previous_score=int(best_score),
            is_improvement=not bool(best_artifact),
            summary="Content evaluation parsed with defaults.",
        )


def _now() -> str:
    """Local timestamp — mirrors prepare.py helper."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
