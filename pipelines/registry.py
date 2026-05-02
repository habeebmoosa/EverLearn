from __future__ import annotations

from typing import Dict, List

from orchestrator.types import PipelinePlugin

_PIPELINES: Dict[str, PipelinePlugin] = {}


def register_pipeline(plugin: PipelinePlugin) -> None:
    _PIPELINES[plugin.plugin_id] = plugin


def get_pipeline(plugin_id: str) -> PipelinePlugin:
    if plugin_id not in _PIPELINES:
        raise KeyError(f"Unknown pipeline: {plugin_id!r}. Available: {list(_PIPELINES)}")
    return _PIPELINES[plugin_id]


def get_pipeline_ids() -> List[str]:
    """Return the IDs of all currently registered pipelines."""
    return list(_PIPELINES.keys())


def list_pipelines() -> List[dict]:
    return [
        {
            "id": p.plugin_id,
            "name": getattr(p, "display_name", p.plugin_id),
            "description": getattr(p, "description", ""),
            "output_label": getattr(p, "output_label", "Artifact"),
        }
        for p in _PIPELINES.values()
    ]
