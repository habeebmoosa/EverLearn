from __future__ import annotations

from typing import Dict, List

from orchestrator.types import PipelinePlugin

_PIPELINES: Dict[str, PipelinePlugin] = {}


def register_pipeline(plugin: PipelinePlugin) -> None:
    _PIPELINES[plugin.plugin_id] = plugin


def get_pipeline(plugin_id: str) -> PipelinePlugin:
    if plugin_id not in _PIPELINES:
        raise KeyError(f"Unknown pipeline: {plugin_id}")
    return _PIPELINES[plugin_id]


def list_pipelines() -> List[dict]:
    return [
        {"id": p.plugin_id, "name": p.display_name}
        for p in _PIPELINES.values()
    ]

