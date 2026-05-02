"""
pipelines/base.py — BasePipeline

Optional base class for pipeline plugins. Provides default implementations
of the metadata interface (get_input_schema, get_display_config, description,
output_label) so concrete pipelines only override what they need.

Pipelines do NOT have to inherit from this — the PipelinePlugin Protocol is
still the governing contract. This class just removes boilerplate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from orchestrator.types import Artifact, EvaluationResult, IterationResult


class BasePipeline:
    """Optional base class for pipeline plugins with sensible defaults.

    Subclass this or implement the PipelinePlugin Protocol directly.
    """

    # ── Identity (override in each subclass) ──────────────────────────────
    plugin_id: str = "base"
    display_name: str = "Base Pipeline"
    description: str = "Generic iterative improvement pipeline."
    output_label: str = "Artifact"       # What to call the output in the UI

    # ── Metadata interface (override to customise UI form rendering) ──────

    def get_input_schema(self) -> dict:
        """Return a JSON Schema describing the pipeline's task inputs.

        The UI renders a dynamic form from this schema. Fields defined here
        appear as form controls in the new-task dialog.
        Only the 'label' field is required by the generic /api/tasks/start.
        All other fields are pipeline-specific and arrive via TaskRequest.inputs.
        """
        return {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "title": "Task",
                    "description": "What do you want to improve?",
                },
            },
            "required": ["label"],
        }

    def get_display_config(self) -> dict:
        """Return UI display hints for this pipeline.

        Keys:
          label_placeholder  — placeholder text for the main label input
          max_iterations_default — pre-filled iteration count
          depth_options      — which depth options to show
          show_web_search    — show the web-search toggle
          show_data_sources  — show the data-sources panel
          show_focus_areas   — show focus-areas input
        """
        return {
            "label_placeholder": "Describe your task...",
            "max_iterations_default": 5,
            "depth_options": ["quick", "standard", "deep"],
            "show_web_search": False,
            "show_data_sources": True,
            "show_focus_areas": False,
        }

    # ── Core contract (must be overridden) ────────────────────────────────

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
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement run_iteration()"
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
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement evaluate()"
        )
