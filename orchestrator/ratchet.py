from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .types import Artifact, EvaluationResult, PipelinePlugin, SessionState


@dataclass
class RatchetPolicy:
    stop_score_threshold: float = 90.0
    stop_after_consecutive_discards: int = 3


class RatchetOrchestrator:
    """Generic iterative improvement loop: run → evaluate → keep only improvements."""

    def __init__(
        self,
        *,
        plugin: PipelinePlugin,
        persist_session,
        now_fn,
        logger,
        policy: Optional[RatchetPolicy] = None,
    ):
        self.plugin = plugin
        self.persist_session = persist_session
        self.now_fn = now_fn
        self.logger = logger
        self.policy = policy or RatchetPolicy()

    async def run(
        self,
        *,
        session_id: str,
        session: Dict[str, Any],
        request: Any,
        iteration_timeout_seconds: int,
    ) -> None:
        session["status"] = SessionState.running.value
        session["updated_at"] = self.now_fn()
        await self.persist_session(session)

        max_iterations = int(session.get("max_iterations") or 1)

        best_artifact: Optional[Artifact] = None
        best_score: float = float(session.get("best_score") or 0.0)

        try:
            for iteration in range(1, max_iterations + 1):
                iter_start = time.time()
                session["current_iteration"] = iteration
                session["current_step"] = "Planning..."
                session["updated_at"] = self.now_fn()
                await self.persist_session(session)

                partial: Dict[str, Any] = {}
                timed_out = False
                try:
                    iter_result = await asyncio.wait_for(
                        self.plugin.run_iteration(
                            session_id=session_id,
                            session=session,
                            iteration=iteration,
                            max_iterations=max_iterations,
                            request=request,
                            best_artifact=best_artifact,
                            partial=partial,
                        ),
                        timeout=iteration_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    timed_out = True
                    iter_result = None

                if not iter_result or not iter_result.artifact:
                    duration = round(time.time() - iter_start, 1)
                    summary = (
                        f"Timed out after {iteration_timeout_seconds}s with no usable partial results"
                        if timed_out
                        else "No artifact produced — pipeline may have failed"
                    )
                    session["iterations"].append(
                        {
                            "iteration": iteration,
                            "quality_score": 0,
                            "kept": False,
                            "summary": summary,
                            "timestamp": self.now_fn(),
                            "duration_seconds": duration,
                            "details": (partial.get("iteration_details") or {}),
                        }
                    )
                    session["updated_at"] = self.now_fn()
                    await self.persist_session(session)
                    continue

                new_artifact = iter_result.artifact

                session["current_step"] = "Evaluating quality..."
                session["updated_at"] = self.now_fn()
                await self.persist_session(session)

                evaluation: EvaluationResult = await self.plugin.evaluate(
                    session_id=session_id,
                    iteration=iteration,
                    max_iterations=max_iterations,
                    request=request,
                    new_artifact=new_artifact,
                    best_artifact=best_artifact,
                    best_score=best_score,
                )

                new_score = float(evaluation.new_score or 0.0)
                is_improvement = bool(evaluation.is_improvement)

                if is_improvement or iteration == 1:
                    best_artifact = new_artifact
                    best_score = new_score
                    session["best_iteration"] = iteration
                    session["best_score"] = best_score
                    session["best_report"] = best_artifact.content
                    kept = True
                else:
                    kept = False

                duration = round(time.time() - iter_start, 1)
                summary = evaluation.summary or f"Score: {new_score} ({'kept' if kept else 'discarded'})"
                gaps = evaluation.remaining_gaps or []
                if gaps:
                    summary += " | Gaps: " + "; ".join(gaps[:3])

                session["iterations"].append(
                    {
                        "iteration": iteration,
                        "quality_score": new_score,
                        "kept": kept,
                        "summary": summary,
                        "timestamp": self.now_fn(),
                        "duration_seconds": duration,
                        "details": iter_result.iteration_details,
                        "evaluation": {
                            "new_score": evaluation.new_score,
                            "previous_score": evaluation.previous_score,
                            "is_improvement": evaluation.is_improvement,
                            "scoring_breakdown": evaluation.scoring_breakdown,
                            "remaining_gaps": evaluation.remaining_gaps,
                            "improvement_summary": evaluation.summary,
                        },
                    }
                )
                session["updated_at"] = self.now_fn()
                await self.persist_session(session)

                if best_score >= self.policy.stop_score_threshold:
                    break
                recent = session["iterations"][-self.policy.stop_after_consecutive_discards :]
                if (
                    len(recent) >= self.policy.stop_after_consecutive_discards
                    and all(not s.get("kept") for s in recent)
                ):
                    break

            session["status"] = SessionState.completed.value
        except Exception as e:
            session["status"] = SessionState.failed.value
            session["error"] = str(e)
            raise
        finally:
            session["updated_at"] = self.now_fn()
            await self.persist_session(session)

