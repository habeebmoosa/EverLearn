"""
EverLearn Agent — prepare.py

Data preparation, evaluation harness, and orchestration loop.
Mirrors Karpathy's autoresearch prepare.py: this file is the immutable
infrastructure that runs the learning pipeline (train.py) iteratively,
evaluates quality, and implements the ratchet mechanism.

Usage:
    uvicorn AutonomousLearningAgent.prepare:app --reload --port 8000
"""

# Python 3.9 compatibility patch for Google ADK
import sys
import types

if sys.version_info < (3, 10):
    if not hasattr(types, "UnionType"):
        types.UnionType = type(None)

import os
import re
import json
import time
import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dataclasses import dataclass, field as dc_field

from dotenv import load_dotenv

# Load environment variables
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path)

if not os.environ.get("GOOGLE_API_KEY"):
    print("WARNING: GOOGLE_API_KEY not found in environment variables!")

# Google ADK imports
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

# ──────────────────────────────────────────────────────────────────────────────
# Langfuse Observability (optional) — Initialize BEFORE importing agents
# ──────────────────────────────────────────────────────────────────────────────
LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_SECRET_KEY")
    and os.environ.get("LANGFUSE_PUBLIC_KEY")
    and os.environ.get("LANGFUSE_HOST")
)


def _noop_observe(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


if LANGFUSE_ENABLED:
    try:
        from langfuse import observe, get_client as get_langfuse_client

        _langfuse = get_langfuse_client()
        try:
            from openinference.instrumentation.google_adk import GoogleADKInstrumentor

            GoogleADKInstrumentor().instrument()
            print("Langfuse + OpenTelemetry ADK instrumentation enabled")
        except Exception as e:
            print(f"WARNING: ADK OTel instrumentation failed (non-fatal): {e}")
    except Exception as e:
        print(f"WARNING: Langfuse initialization failed (non-fatal): {e}")
        LANGFUSE_ENABLED = False
        observe = _noop_observe  # type: ignore[assignment]
        _langfuse = None
else:
    observe = _noop_observe  # type: ignore[assignment]
    _langfuse = None

# Import DB helpers (Postgres-backed session storage)
from db import (
    init_db,
    check_db,
    save_session as db_save_session,
    get_session as db_get_session,
    list_sessions as db_list_sessions,
    delete_session as db_delete_session,
    is_db_configured,
)

# Orchestration core + pipeline plugins
from orchestrator import RatchetOrchestrator
from pipelines import ResearchPipeline, ContentWriterPipeline, register_pipeline, list_pipelines, get_pipeline

# Import agents
from train import root_agent, research_iteration_pipeline
from sub_agents import quality_evaluator_agent as eval_agent

# Import cache clearing functions
from tools.web_search import clear_search_cache
from tools.web_fetch import clear_url_cache

# Import A2A models
from a2a_models import (
    AgentCard, AgentInterface, AgentProvider, AgentCapability,
    Message, Task, TaskStatus, Artifact, Part, SendMessageRequest,
)
import uuid

logger = logging.getLogger("everlearn")
logging.basicConfig(level=logging.INFO)

# DB readiness flag (Postgres is the session DB)
DB_READY: bool = False

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# FastAPI app
app = FastAPI(
    title="EverLearn Agent",
    description="Autonomous iterative learning agent with quality ratchet — inspired by Karpathy's autoresearch",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if os.path.isdir(UI_DIR):
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────────────────────────────────────

class DataSource(BaseModel):
    type: str = Field(..., description="'url', 'file', or 'text'")
    content: str = Field(..., description="URL string, file path, or raw text")
    label: Optional[str] = None

class ResearchConfig(BaseModel):
    max_iterations: int = Field(default=5, ge=1, le=20)
    depth: str = Field(default="standard", description="'quick', 'standard', 'deep'")
    focus_areas: Optional[List[str]] = None
    enable_web_search: bool = True
    max_iteration_timeout: int = Field(default=180, ge=30, le=600, description="Max seconds per iteration pipeline run")

class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500)
    data_sources: Optional[List[DataSource]] = None
    config: Optional[ResearchConfig] = None


# ── Generic models (pipeline-agnostic) ──────────────────────────────────────

class TaskConfig(BaseModel):
    """Generic task configuration — superset of ResearchConfig."""
    max_iterations: int = Field(default=5, ge=1, le=20)
    depth: str = Field(default="standard", description="'quick', 'standard', 'deep'")
    max_iteration_timeout: int = Field(default=180, ge=30, le=600)
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Pipeline-specific extra config")


class TaskRequest(BaseModel):
    """Generic task request — works with any registered pipeline."""
    pipeline_id: str = Field(default="research", description="Which pipeline to run")
    label: str = Field(..., min_length=3, max_length=500,
                       description="Human-readable task label (topic, PR title, config target, etc.)")
    inputs: Optional[Dict[str, Any]] = Field(default=None,
                    description="Pipeline-specific inputs (focus_areas, region_id, tone, etc.)")
    data_sources: Optional[List[DataSource]] = None
    config: Optional[TaskConfig] = None

class IterationSource(BaseModel):
    title: str = ""
    url: str = ""
    type: str = ""
    relevance: str = ""

class IterationDetail(BaseModel):
    search_queries: List[str] = []
    sources_collected: List[IterationSource] = []
    total_sources: int = 0
    urls_fetched: int = 0

class IterationSnapshot(BaseModel):
    iteration: int
    quality_score: float
    kept: bool
    summary: str
    timestamp: str
    duration_seconds: float = 0
    details: Optional[IterationDetail] = None

class ResearchSessionModel(BaseModel):
    session_id: str
    topic: str
    status: str
    current_iteration: int = 0
    max_iterations: int = 5
    best_iteration: int = 0
    best_score: float = 0.0
    iterations: List[IterationSnapshot] = []
    best_report: Optional[str] = None
    created_at: str
    updated_at: str
    error: Optional[str] = None

class ResearchResponse(BaseModel):
    session_id: str
    status: str
    topic: str
    current_iteration: int
    max_iterations: int
    best_score: float
    current_step: Optional[str] = None
    iterations: List[IterationSnapshot] = []
    report: Optional[str] = None
    data_sources: Optional[List[Dict[str, str]]] = None


class TaskResponse(BaseModel):
    """Generic session response — returned by /api/tasks/* endpoints."""
    session_id: str
    pipeline_id: str
    label: str
    status: str
    current_iteration: int
    max_iterations: int
    best_score: float
    current_step: Optional[str] = None
    iterations: List[IterationSnapshot] = []
    artifact: Optional[str] = None          # best output produced so far
    task_inputs: Optional[Dict[str, Any]] = None
    data_sources: Optional[List[Dict[str, str]]] = None


@dataclass
class _ResearchContext:
    """Context for the research pipeline (backward compat)."""
    topic: str
    data_sources_list: List[Dict[str, Any]] = dc_field(default_factory=list)
    focus_areas_str: str = ""
    enable_web_search: bool = True


@dataclass
class _TaskContext:
    """Generic context passed to any pipeline plugin.

    Pipelines access task-specific fields via .get(key) from the inputs dict.
    Research-compatible attributes (topic, focus_areas_str, enable_web_search,
    data_sources_list) are exposed directly so ResearchPipeline works unchanged.
    """
    pipeline_id: str
    label: str
    inputs: Dict[str, Any]
    data_sources_list: List[Dict[str, Any]] = dc_field(default_factory=list)
    focus_areas_str: str = ""
    enable_web_search: bool = True
    config_extra: Dict[str, Any] = dc_field(default_factory=dict)

    # Backward-compat alias so ResearchPipeline can use request.topic
    @property
    def topic(self) -> str:
        return self.label

    def get(self, key: str, default=None):
        """Read a pipeline-specific input value."""
        return self.inputs.get(key, default)


# ──────────────────────────────────────────────────────────────────────────────
# In-Memory Session Store
# ──────────────────────────────────────────────────────────────────────────────

_research_sessions: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _parse_state_value(val: Any, target_key: Optional[str] = None) -> Optional[dict]:
    """Parse a session state value that might be dict, JSON string, or markdown-wrapped JSON."""
    if isinstance(val, dict):
        return val.get(target_key, val) if target_key and target_key in val else val
    if not isinstance(val, str) or not val.strip():
        return None
    raw = val.strip()
    # Strip markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get(target_key, parsed) if target_key and target_key in parsed else parsed
    except (json.JSONDecodeError, ValueError):
        pass
    # Try extract_json_from_response
    result = extract_json_from_response(val, target_key)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# JSON Extraction Helper
# ──────────────────────────────────────────────────────────────────────────────

def extract_json_from_response(response_text: str, target_key: Optional[str] = None) -> Optional[Dict]:
    """Parse structured JSON from agent response text.

    Tries code-fenced JSON blocks first, then bare JSON objects.
    Uses a balanced-brace scanner to correctly handle nested JSON.
    If target_key is specified, looks for that key inside parsed objects.
    """
    candidates = []

    def _scan_json_objects(text: str):
        """Find all top-level JSON objects using balanced brace matching."""
        depth = 0
        start = None
        in_string = False
        escape_next = False
        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start : i + 1]
                    start = None

    # Strategy 1: code-fenced JSON blocks
    code_fence_pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
    for match in code_fence_pattern.finditer(response_text):
        block = match.group(1).strip()
        for json_str in _scan_json_objects(block):
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    candidates.append(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 2: bare JSON objects outside code fences
    stripped = code_fence_pattern.sub("", response_text)
    for json_str in _scan_json_objects(stripped):
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    if not candidates:
        return None

    # If target_key specified, find it
    if target_key:
        for c in candidates:
            if target_key in c:
                return c[target_key]
        # Fallback: check if any candidate has "new_score" (evaluator output)
        if target_key == "quality_evaluation":
            for c in candidates:
                if "new_score" in c:
                    return c
        # Last resort: return first candidate
        return candidates[0]

    return candidates[0]


# ──────────────────────────────────────────────────────────────────────────────
# Report Validation Helpers
# ──────────────────────────────────────────────────────────────────────────────

# Keys that indicate a response is agent JSON output, NOT a report
_AGENT_JSON_KEYS = {
    "research_plan", "collected_sources", "research_analysis",
    "quality_evaluation", "search_queries", "iteration_goal",
    "sources", "key_findings", "scoring_breakdown",
}


def _is_json_not_report(text: str) -> bool:
    """Check if text is a JSON object from a sub-agent rather than a markdown report."""
    if not text or not isinstance(text, str):
        return False
    stripped = text.strip()
    # Strip markdown code fences
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
        stripped = stripped.strip()
    # Must start with { to be JSON
    if not stripped.startswith("{"):
        return False
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            # Check if it contains known agent output keys
            if _AGENT_JSON_KEYS & set(parsed.keys()):
                return True
            # Check nested — e.g. {"research_plan": {...}}
            for v in parsed.values():
                if isinstance(v, dict) and (_AGENT_JSON_KEYS & set(v.keys())):
                    return True
        return False
    except (json.JSONDecodeError, ValueError):
        return False


def _pick_best_report(responses: list) -> Optional[str]:
    """Pick the best report-like text from a list of responses.
    Filters out JSON objects, short strings, and prefers longer markdown content."""
    if not responses:
        return None
    candidates = []
    for r in responses:
        if not r or not isinstance(r, str) or len(r) < 200:
            continue
        if _is_json_not_report(r):
            continue
        candidates.append(r)
    if not candidates:
        return None
    # Return the longest non-JSON response (most likely the full report)
    return max(candidates, key=len)


def _extract_sources_from_responses(responses: list) -> dict:
    """Extract iter_details (search queries, sources) from collected_responses JSON.
    Used as fallback when session state extraction fails or on timeout."""
    iter_details = {
        "search_queries": [],
        "sources_collected": [],
        "total_sources": 0,
        "urls_fetched": 0,
    }
    if not responses:
        return iter_details

    for r in responses:
        if not r or not isinstance(r, str):
            continue
        # Try to parse each response as JSON and extract plan/sources data
        parsed = extract_json_from_response(r)
        if not isinstance(parsed, dict):
            continue

        # Check for research_plan data
        plan = parsed.get("research_plan", parsed)
        if isinstance(plan, dict) and "search_queries" in plan:
            if not iter_details["search_queries"]:
                iter_details["search_queries"] = plan.get("search_queries", [])[:10]

        # Check for collected_sources data
        sources = parsed.get("collected_sources", parsed)
        if isinstance(sources, dict) and "sources" in sources:
            src_list = sources.get("sources", [])
            if src_list and not iter_details["sources_collected"]:
                iter_details["total_sources"] = sources.get("total_sources", len(src_list))
                iter_details["urls_fetched"] = sources.get("urls_fetched", 0)
                iter_details["sources_collected"] = [
                    {
                        "title": s.get("title", "")[:100],
                        "url": s.get("url", ""),
                        "type": s.get("type", ""),
                        "relevance": s.get("relevance", ""),
                    }
                    for s in src_list[:20]
                    if isinstance(s, dict)
                ]

    return iter_details


# ──────────────────────────────────────────────────────────────────────────────
# Core: The Research Ratchet Loop
# ──────────────────────────────────────────────────────────────────────────────

@observe(name="learning_iteration_pipeline", as_type="generation")
async def _run_iteration_pipeline(
    session_id: str,
    session: dict,
    iteration: int,
    max_iterations: int,
    topic: str,
    data_sources_list: list,
    focus_areas_str: str,
    best_report: Optional[str],
    enable_web_search: bool,
    _partial_results: Optional[dict] = None,
) -> tuple:
    """Run one iteration of the learning pipeline. Returns (new_report, iter_details, collected_responses)."""

    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "iteration": iteration,
                "max_iterations": max_iterations,
                "topic": topic,
                "has_previous_report": best_report is not None,
            }
        )

    iteration_state = {
        "topic": topic,
        "data_sources": json.dumps(data_sources_list),
        "focus_areas": focus_areas_str,
        "iteration_number": str(iteration),
        "max_iterations": str(max_iterations),
        "previous_best_report": best_report or "No previous research. This is the first iteration.",
        "previous_gaps": (
            session["iterations"][-1]["summary"]
            if session["iterations"]
            else "First iteration — no gaps yet."
        ),
        "enable_web_search": str(enable_web_search),
    }

    runner = InMemoryRunner(
        agent=research_iteration_pipeline,
        app_name="auto_learn",
    )
    adk_session = await runner.session_service.create_session(
        app_name="auto_learn",
        user_id="research_user",
        state=iteration_state,
    )

    # Build data sources text to include directly in the trigger
    data_sources_text = ""
    if data_sources_list:
        ds_parts = []
        for i, ds in enumerate(data_sources_list, 1):
            label = ds.get("label") or ds.get("type", "source")
            content = ds.get("content", "")
            # Truncate large content to avoid exceeding context
            if len(content) > 15000:
                content = content[:15000] + "\n... [truncated]"
            ds_parts.append(f"--- Data Source {i} ({label}) ---\n{content}")
        data_sources_text = "\n\n".join(ds_parts)

    trigger_text = (
        f"Execute research iteration {iteration} of {max_iterations} "
        f"for topic: {topic}\n\n"
        f"Focus areas: {focus_areas_str or 'general coverage'}\n"
        f"Web search enabled: {enable_web_search}\n"
        f"Data sources provided: {len(data_sources_list)}\n\n"
        f"Previous best report exists: {'Yes' if best_report else 'No'}"
    )
    if data_sources_text:
        trigger_text += (
            f"\n\n## USER-PROVIDED DATA SOURCES (use this content directly in your research)\n\n"
            f"{data_sources_text}"
        )

    trigger = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=trigger_text)],
    )

    step_names = {
        "research_planner_agent": "Planning research strategy...",
        "source_collector_agent": "Collecting sources from web...",
        "deep_researcher_agent": "Analyzing sources in depth...",
        "report_synthesizer_agent": "Synthesizing research report...",
    }

    collected_responses = []
    # Track responses by agent author for smarter fallback
    synthesizer_responses = []
    try:
        async for event in runner.run_async(
            user_id="research_user",
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
                        # Tag synthesizer outputs separately for reliable fallback
                        if author == "report_synthesizer_agent":
                            synthesizer_responses.append(part.text)
            # Update partial results so timeout handler can salvage data
            if _partial_results is not None:
                _partial_results["collected_responses"] = list(collected_responses)
    except Exception as e:
        logger.error(f"[{session_id}] Pipeline error iteration {iteration}: {e}")

    # Extract outputs from session state
    new_report = None
    iter_details = {"search_queries": [], "sources_collected": [], "total_sources": 0, "urls_fetched": 0}
    try:
        final_session = await runner.session_service.get_session(
            app_name="auto_learn",
            user_id="research_user",
            session_id=adk_session.id,
        )
        if final_session and getattr(final_session, "state", None):
            state = dict(final_session.state)
            new_report = state.get("research_report")
            if isinstance(new_report, dict):
                new_report = json.dumps(new_report, indent=2)

            plan_raw = state.get("research_plan")
            plan = _parse_state_value(plan_raw, "research_plan")
            if plan:
                iter_details["search_queries"] = plan.get("search_queries", [])[:10]

            sources_raw = state.get("collected_sources")
            sources = _parse_state_value(sources_raw, "collected_sources")
            if sources:
                src_list = sources.get("sources", [])
                iter_details["total_sources"] = sources.get("total_sources", len(src_list))
                iter_details["urls_fetched"] = sources.get("urls_fetched", 0)
                iter_details["sources_collected"] = [
                    {
                        "title": s.get("title", "")[:100],
                        "url": s.get("url", ""),
                        "type": s.get("type", ""),
                        "relevance": s.get("relevance", ""),
                    }
                    for s in src_list[:20]
                ]
    except Exception as e:
        logger.warning(f"[{session_id}] Session state read warning: {e}")

    # Fallback: extract sources from collected_responses if state extraction missed them
    if not iter_details["sources_collected"] and collected_responses:
        fallback_details = _extract_sources_from_responses(collected_responses)
        if fallback_details["sources_collected"]:
            iter_details = fallback_details
            logger.info(f"[{session_id}] Extracted {len(iter_details['sources_collected'])} sources from responses (state fallback)")

    # Validate: reject JSON objects masquerading as reports
    if new_report and _is_json_not_report(new_report):
        logger.warning(f"[{session_id}] research_report from state is JSON, not markdown — rejecting")
        new_report = None

    # Fallback: try to extract report from collected responses
    if not new_report:
        # Priority 1: synthesizer responses (most likely to be the actual report)
        new_report = _pick_best_report(synthesizer_responses)
        if new_report:
            logger.info(f"[{session_id}] Extracted report from synthesizer responses ({len(new_report)} chars)")

    if not new_report:
        # Priority 2: any non-JSON response that looks like a report
        new_report = _pick_best_report(collected_responses)
        if new_report:
            logger.info(f"[{session_id}] Extracted report from collected responses ({len(new_report)} chars)")

    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "report_length": len(new_report) if new_report else 0,
                "sources_collected": iter_details.get("total_sources", 0),
                "queries_executed": len(iter_details.get("search_queries", [])),
            }
        )

    return new_report, iter_details, collected_responses


@observe(name="quality_evaluator", as_type="generation")
async def _run_quality_evaluator(
    session_id: str,
    iteration: int,
    max_iterations: int,
    topic: str,
    focus_areas_str: str,
    new_report: str,
    best_report: Optional[str],
    best_score: float,
) -> dict:
    """Run quality evaluator. Returns evaluation dict."""

    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "iteration": iteration,
                "new_report_length": len(new_report),
                "previous_report_length": len(best_report) if best_report else 0,
            }
        )

    from tools.research_utils import count_words, calculate_coverage_score

    eval_runner = InMemoryRunner(
        agent=eval_agent,
        app_name="auto_learn",
    )

    # Pre-compute stats so the evaluator doesn't need tools
    new_stats = count_words(new_report[:30000])
    prev_stats = count_words((best_report or "")[:30000])
    new_coverage = calculate_coverage_score(new_report[:30000], focus_areas_str) if focus_areas_str else {}
    prev_coverage = calculate_coverage_score((best_report or "")[:30000], focus_areas_str) if focus_areas_str else {}

    eval_state = {
        "new_report": new_report[:30000],
        "previous_best_report": (best_report or "")[:30000],
        "topic": topic,
        "focus_areas": focus_areas_str,
        "iteration_number": str(iteration),
        "new_report_stats": json.dumps(new_stats),
        "previous_report_stats": json.dumps(prev_stats),
        "new_report_coverage": json.dumps(new_coverage),
        "previous_report_coverage": json.dumps(prev_coverage),
    }
    eval_session = await eval_runner.session_service.create_session(
        app_name="auto_learn",
        user_id="eval_user",
        state=eval_state,
    )

    eval_trigger = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(
            text=(
                f"Evaluate research iteration {iteration} for topic: {topic}\n\n"
                f"Compare the new_report against previous_best_report in session state.\n"
                f"Focus areas: {focus_areas_str or 'general'}\n"
                f"This is iteration {iteration} of {max_iterations}."
            )
        )],
    )

    eval_responses = []
    try:
        async for event in eval_runner.run_async(
            user_id="eval_user",
            session_id=eval_session.id,
            new_message=eval_trigger,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        eval_responses.append(part.text)
    except Exception as e:
        logger.error(f"[{session_id}] Evaluator error iteration {iteration}: {e}")

    # Parse evaluation from structured output (output_schema guarantees valid JSON)
    evaluation = None

    # Strategy 1: session state output_key (structured output lands here as dict)
    try:
        eval_final = await eval_runner.session_service.get_session(
            app_name="auto_learn",
            user_id="eval_user",
            session_id=eval_session.id,
        )
        if eval_final and getattr(eval_final, "state", None):
            state_dict = dict(eval_final.state)
            eval_val = state_dict.get("quality_evaluation")
            if eval_val is not None:
                logger.info(f"[{session_id}] Eval state type: {type(eval_val).__name__}, preview: {str(eval_val)[:200]}")
                if isinstance(eval_val, dict):
                    evaluation = eval_val
                elif isinstance(eval_val, str) and eval_val.strip():
                    try:
                        parsed = json.loads(eval_val)
                        if isinstance(parsed, dict):
                            evaluation = parsed.get("quality_evaluation", parsed)
                    except (json.JSONDecodeError, ValueError):
                        pass
    except Exception as e:
        logger.warning(f"[{session_id}] Eval state read error: {e}")

    # Strategy 2: parse from response text (fallback if state didn't capture it)
    if not evaluation and eval_responses:
        full_eval_text = "\n".join(eval_responses)
        logger.info(f"[{session_id}] Trying eval response text ({len(full_eval_text)} chars)")
        evaluation = extract_json_from_response(full_eval_text, "quality_evaluation")

    if evaluation:
        logger.info(f"[{session_id}] Parsed evaluation: new_score={evaluation.get('new_score')}, is_improvement={evaluation.get('is_improvement')}")
    else:
        logger.warning(f"[{session_id}] Evaluation parsing FAILED for iteration {iteration}. Responses collected: {len(eval_responses)}, total chars: {sum(len(r) for r in eval_responses)}")

    if not evaluation:
        evaluation = {
            "new_score": 50 if iteration == 1 else 0,
            "previous_score": best_score,
            "is_improvement": iteration == 1,
            "improvement_summary": "Evaluation parsing failed — defaulting",
            "remaining_gaps": [],
        }

    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "new_score": evaluation.get("new_score"),
                "previous_score": evaluation.get("previous_score"),
                "is_improvement": evaluation.get("is_improvement"),
            }
        )

    return evaluation


@observe(name="learning_session")
async def run_research_loop(session_id: str, request: ResearchRequest):
    """
    Background task: runs the iterative research ratchet loop.
    Traced by Langfuse as a top-level "learning_session".
    """
    # If the in-memory entry was lost (restart), try loading from Postgres.
    session = _research_sessions.get(session_id)
    if not session and is_db_configured():
        try:
            session = await db_get_session(session_id)
        except Exception:
            session = None
    if not session:
        logger.error(f"[{session_id}] Session not found in memory or DB; aborting loop")
        return
    _research_sessions[session_id] = session

    # Clear tool caches for fresh session (caches persist across iterations within session)
    clear_search_cache()
    clear_url_cache()

    config = request.config or ResearchConfig()
    max_iterations = config.max_iterations
    iteration_timeout = config.max_iteration_timeout

    if config.depth == "quick":
        max_iterations = min(max_iterations, 2)
    elif config.depth == "deep":
        max_iterations = max(max_iterations, 8)

    session["max_iterations"] = max_iterations

    # Build data sources metadata (type + label only, no full content)
    data_sources_meta = []
    if request.data_sources:
        for ds in request.data_sources:
            data_sources_meta.append(
                {
                    "type": ds.type,
                    "label": ds.label or "",
                    "content_preview": ds.content[:200] if ds.type == "url" else "",
                }
            )

    # Set Langfuse trace metadata (if enabled)
    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "session_id": session_id,
                "topic": request.topic,
                "max_iterations": max_iterations,
                "depth": config.depth,
                "focus_areas": config.focus_areas,
                "data_sources_count": len(request.data_sources) if request.data_sources else 0,
                "data_sources": data_sources_meta,
                "web_search_enabled": config.enable_web_search,
            },
        )

    # Build data_sources_list (full content, for pipeline use — separate from metadata)
    data_sources_list: List[Dict[str, Any]] = []
    if request.data_sources:
        for ds in request.data_sources:
            data_sources_list.append({"type": ds.type, "content": ds.content, "label": ds.label or ""})

    # Build the immutable context object for the pipeline plugin.
    # Do NOT assign these attrs to the Pydantic model — it's immutable in v2.
    pipeline_request = _ResearchContext(
        topic=request.topic,
        data_sources_list=data_sources_list,
        focus_areas_str=",".join(config.focus_areas) if config.focus_areas else "",
        enable_web_search=bool(config.enable_web_search),
    )

    async def _persist(s: dict):
        if is_db_configured():
            await db_save_session(s)

    orchestrator = RatchetOrchestrator(
        plugin=ResearchPipeline(run_iteration_fn=_run_iteration_pipeline, evaluate_fn=_run_quality_evaluator),
        persist_session=_persist,
        now_fn=_now,
        logger=logger,
    )

    try:
        await orchestrator.run(
            session_id=session_id,
            session=session,
            request=pipeline_request,
            iteration_timeout_seconds=iteration_timeout,
        )
    except Exception as e:
        logger.error(f"[{session_id}] Research loop failed: {e}")
        import traceback

        traceback.print_exc()

    logger.info(
        f"[{session_id}] Research complete. Status: {session['status']}, Best score: {session['best_score']}"
    )

    # Persist final state to Langfuse trace (observability only, if enabled)
    if _langfuse:
        try:
            _langfuse.set_current_trace_io(
                input={
                    "topic": request.topic,
                    "config": config.model_dump()
                    if hasattr(config, "model_dump")
                    else (config.dict() if hasattr(config, "dict") else {}),
                    "data_sources": data_sources_meta,
                },
                output={
                    "status": session["status"],
                    "best_score": session["best_score"],
                    "best_iteration": session.get("best_iteration", 0),
                    "iterations_count": len(session["iterations"]),
                    "iterations": session["iterations"],
                    "report": (session.get("best_report") or "")[:50000],
                },
            )
            _langfuse.update_current_span(
                metadata={
                    "session_id": session_id,
                    "topic": request.topic[:190],
                    "status": session["status"],
                    "best_score": str(session["best_score"]),
                    "iterations_count": str(len(session["iterations"])),
                    "depth": config.depth,
                },
            )
        except Exception as e:
            logger.warning(f"[{session_id}] Failed to persist to Langfuse: {e}")

        # Flush Langfuse traces
        try:
            _langfuse.flush()
        except Exception:
            pass



# ──────────────────────────────────────────────────────────────────────────────
# Generic Task Loop — dispatches to any registered pipeline
# ──────────────────────────────────────────────────────────────────────────────

@observe(name="learning_session")
async def run_task_loop(session_id: str, request: TaskRequest):
    """
    Generic background task: runs the ratchet loop for ANY registered pipeline.
    Resolves the pipeline from the registry using request.pipeline_id.
    """
    session = _research_sessions.get(session_id)
    if not session and is_db_configured():
        try:
            session = await db_get_session(session_id)
        except Exception:
            session = None
    if not session:
        logger.error(f"[{session_id}] Session not found; aborting task loop")
        return
    _research_sessions[session_id] = session

    # Resolve pipeline from registry
    try:
        pipeline = get_pipeline(request.pipeline_id)
    except KeyError:
        session["status"] = "failed"
        session["error"] = f"Unknown pipeline: '{request.pipeline_id}'. Register it first."
        session["updated_at"] = _now()
        if is_db_configured():
            await db_save_session(session)
        logger.error(f"[{session_id}] {session['error']}")
        return

    clear_search_cache()
    clear_url_cache()

    config = request.config or TaskConfig()
    max_iterations = config.max_iterations
    iteration_timeout = config.max_iteration_timeout
    if config.depth == "quick":
        max_iterations = min(max_iterations, 2)
    elif config.depth == "deep":
        max_iterations = max(max_iterations, 8)
    session["max_iterations"] = max_iterations

    inputs = request.inputs or {}

    # Build full data-sources list (with content) for pipeline use
    data_sources_list: List[Dict[str, Any]] = []
    if request.data_sources:
        for ds in request.data_sources:
            data_sources_list.append({"type": ds.type, "content": ds.content, "label": ds.label or ""})

    # Build generic context — research-compat fields extracted from inputs
    focus_areas_raw = inputs.get("focus_areas", "")
    if isinstance(focus_areas_raw, list):
        focus_areas_str = ",".join(focus_areas_raw)
    else:
        focus_areas_str = str(focus_areas_raw) if focus_areas_raw else ""

    pipeline_request = _TaskContext(
        pipeline_id=request.pipeline_id,
        label=request.label,
        inputs=inputs,
        data_sources_list=data_sources_list,
        focus_areas_str=focus_areas_str,
        enable_web_search=bool(inputs.get("enable_web_search", True)),
        config_extra=config.extra or {},
    )

    if _langfuse:
        _langfuse.update_current_span(
            metadata={
                "session_id": session_id,
                "pipeline_id": request.pipeline_id,
                "label": request.label,
                "max_iterations": max_iterations,
                "inputs": inputs,
            }
        )

    async def _persist(s: dict):
        if is_db_configured():
            await db_save_session(s)

    orchestrator = RatchetOrchestrator(
        plugin=pipeline,
        persist_session=_persist,
        now_fn=_now,
        logger=logger,
    )

    try:
        await orchestrator.run(
            session_id=session_id,
            session=session,
            request=pipeline_request,
            iteration_timeout_seconds=iteration_timeout,
        )
    except Exception as e:
        logger.error(f"[{session_id}] Task loop failed: {e}")
        import traceback
        traceback.print_exc()

    logger.info(
        f"[{session_id}] Task complete. Pipeline={request.pipeline_id}, "
        f"Status={session['status']}, Best score={session['best_score']}"
    )

    if _langfuse:
        try:
            _langfuse.set_current_trace_io(
                input={"pipeline_id": request.pipeline_id, "label": request.label, "inputs": inputs},
                output={
                    "status": session["status"],
                    "best_score": session["best_score"],
                    "iterations_count": len(session["iterations"]),
                },
            )
            _langfuse.flush()
        except Exception:
            pass



# Cache: { session_id: ResearchResponse } built from Langfuse traces
_langfuse_cache: Dict[str, Any] = {}  # sid -> ResearchResponse
_langfuse_cache_list: List[Dict] = []  # list of session summaries for sidebar
_langfuse_cache_trace_ids: Dict[str, str] = {}  # sid -> trace_id
_langfuse_cache_ts: float = 0  # last refresh timestamp
_LANGFUSE_CACHE_TTL = 60  # seconds before cache is considered stale


def _refresh_langfuse_cache(force: bool = False):
    """Fetch all learning_session traces from Langfuse and cache them locally."""
    global _langfuse_cache, _langfuse_cache_list, _langfuse_cache_trace_ids, _langfuse_cache_ts

    if not force and (time.time() - _langfuse_cache_ts) < _LANGFUSE_CACHE_TTL:
        return  # Cache is fresh

    try:
        traces = _langfuse.api.trace.list(name="learning_session", limit=50)
    except Exception as e:
        logger.warning(f"Langfuse cache refresh failed: {e}")
        return

    new_cache: Dict[str, Any] = {}
    new_list: List[Dict] = []
    new_trace_ids: Dict[str, str] = {}

    for t in traces.data:
        meta = t.metadata or {}
        output = t.output if isinstance(t.output, dict) else {}
        inp = t.input if isinstance(t.input, dict) else {}

        sid = meta.get("session_id", t.id)
        topic = meta.get("topic") or inp.get("topic") or ""
        if not topic:
            continue

        status = meta.get("status") or output.get("status") or "completed"
        try:
            best_score = float(meta.get("best_score") or output.get("best_score") or 0)
        except (ValueError, TypeError):
            best_score = 0.0
        try:
            iterations_count = int(meta.get("iterations_count") or len(output.get("iterations", [])))
        except (ValueError, TypeError):
            iterations_count = 0

        ts = t.timestamp.isoformat() + "Z" if t.timestamp else ""

        # Build full response (with report + iterations)
        iterations_raw = output.get("iterations", [])
        iterations = []
        for it in iterations_raw:
            if isinstance(it, dict):
                try:
                    iterations.append(IterationSnapshot(
                        iteration=it.get("iteration", 0),
                        quality_score=float(it.get("quality_score", 0)),
                        kept=bool(it.get("kept", False)),
                        summary=str(it.get("summary", "")),
                        timestamp=str(it.get("timestamp", "")),
                        duration_seconds=float(it.get("duration_seconds", 0)),
                        details=it.get("details"),
                    ))
                except Exception:
                    pass

        # Extract user-provided data sources from trace input
        trace_data_sources = inp.get("data_sources") or meta.get("data_sources") or []

        response = ResearchResponse(
            session_id=sid,
            status=status,
            topic=topic,
            current_iteration=len(iterations) or iterations_count,
            max_iterations=len(iterations) or iterations_count,
            best_score=best_score,
            iterations=iterations,
            report=output.get("report"),
            data_sources=trace_data_sources if trace_data_sources else None,
        )

        new_cache[sid] = response
        new_trace_ids[sid] = t.id
        new_list.append({
            "session_id": sid,
            "topic": topic,
            "status": status,
            "current_iteration": response.current_iteration,
            "max_iterations": response.max_iterations,
            "best_score": best_score,
            "created_at": ts,
            "updated_at": ts,
            "source": "langfuse",
            "trace_id": t.id,
            "total_cost": t.total_cost or 0,
            "latency": t.latency or 0,
        })

    _langfuse_cache = new_cache
    _langfuse_cache_list = new_list
    _langfuse_cache_trace_ids = new_trace_ids
    _langfuse_cache_ts = time.time()
    logger.info(f"Langfuse cache refreshed: {len(new_cache)} sessions")


def _load_session_from_langfuse(session_id: str) -> Optional[ResearchResponse]:
    """Load a session from Langfuse cache. Refreshes cache if stale."""
    _refresh_langfuse_cache()
    return _langfuse_cache.get(session_id)


# ──────────────────────────────────────────────────────────────────────────────
# Langfuse Metrics Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/research/{session_id}/metrics")
async def get_session_metrics(session_id: str):
    """Get Langfuse metrics (tokens, cost, latency) for a session. Uses cache."""
    if not LANGFUSE_ENABLED or not _langfuse:
        return {"metrics": {}, "error": "Langfuse is not configured"}
    # Get trace_id and basic metrics from cache (instant, no API call)
    _refresh_langfuse_cache()
    trace_id = _langfuse_cache_trace_ids.get(session_id)

    # Also check if session_id IS a trace_id
    if not trace_id:
        if session_id in _langfuse_cache_trace_ids.values():
            trace_id = session_id

    if not trace_id:
        return {"metrics": {}, "error": "Trace not found"}

    # Get cost/latency from cached list (no API call)
    total_cost = 0.0
    total_latency = 0.0
    for entry in _langfuse_cache_list:
        if entry.get("trace_id") == trace_id or entry.get("session_id") == session_id:
            total_cost = entry.get("total_cost", 0) or 0
            total_latency = entry.get("latency", 0) or 0
            break

    return {
        "metrics": {
            "total_cost_usd": round(total_cost, 6) if total_cost else 0,
            "total_latency_ms": round(total_latency, 0) if total_latency else 0,
        },
        "trace_id": trace_id,
    }


@app.on_event("startup")
async def _startup_cache():
    """Pre-warm the Langfuse cache on server start and initialize DB."""
    if LANGFUSE_ENABLED and _langfuse:
        try:
            _refresh_langfuse_cache(force=True)
        except Exception as e:
            logger.warning(f"Startup cache warm failed: {e}")

    if is_db_configured():
        try:
            await init_db()
            global DB_READY
            DB_READY = await check_db()
            if not DB_READY:
                logger.error("Database configured but not reachable.")
            else:
                logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            DB_READY = False

    # Register built-in pipelines (plug-and-play)
    # Each pipeline is self-contained — adding a new vertical = new file in pipelines/
    try:
        register_pipeline(
            ResearchPipeline(
                run_iteration_fn=_run_iteration_pipeline,
                evaluate_fn=_run_quality_evaluator,
            )
        )
        logger.info("Pipeline registered: research")
    except Exception as e:
        logger.warning(f"ResearchPipeline registration failed: {e}")

    try:
        register_pipeline(ContentWriterPipeline())
        logger.info("Pipeline registered: content_writer")
    except Exception as e:
        logger.warning(f"ContentWriterPipeline registration failed: {e}")


def _require_db():
    """Raise a clean HTTP error if DB is configured but not available."""
    if is_db_configured() and not DB_READY:
        raise HTTPException(
            status_code=503,
            detail="Postgres database is configured but unavailable. Check DATABASE_* settings / connectivity.",
        )


@app.get("/api/pipelines")
async def get_pipelines():
    """List all registered pipelines with full metadata and input schema."""
    result = []
    for p_meta in list_pipelines():
        pid = p_meta["id"]
        try:
            plugin = get_pipeline(pid)
        except KeyError:
            continue
        result.append({
            "id": pid,
            "name": p_meta["name"],
            "description": getattr(plugin, "description", ""),
            "output_label": getattr(plugin, "output_label", "Artifact"),
            "input_schema": plugin.get_input_schema() if callable(getattr(plugin, "get_input_schema", None)) else {},
            "display_config": plugin.get_display_config() if callable(getattr(plugin, "get_display_config", None)) else {},
        })
    return {"pipelines": result}


@app.post("/api/research/refresh-cache")
async def refresh_langfuse_cache():
    """Force refresh the Langfuse session cache."""
    if not LANGFUSE_ENABLED or not _langfuse:
        return {"cached_sessions": 0, "status": "langfuse_disabled"}
    _refresh_langfuse_cache(force=True)
    return {"cached_sessions": len(_langfuse_cache), "status": "refreshed"}


# ──────────────────────────────────────────────────────────────────────────────
# A2A Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/.well-known/agent-card.json", response_model=AgentCard)
async def get_agent_card():
    """Returns the A2A Agent Card for discovery."""
    return AgentCard(
        name="EverLearn Agent",
        description="Autonomous iterative learning agent with quality ratchet — inspired by Karpathy's autoresearch",
        version="1.0.0",
        supportedInterfaces=[
            AgentInterface(
                url="/message:send",
                protocolBinding="HTTP+JSON",
                protocolVersion="0.3",
            )
        ],
        provider=AgentProvider(
            organization="Drayvn",
            url="https://drayvn.ai",
        ),
        capabilities=AgentCapability(
            streaming=False,
            pushNotifications=False,
            extensions=[],
        ),
        defaultInputModes=["text/plain"],
        defaultOutputModes=["application/json", "text/markdown"],
    )


# A2A session storage
_a2a_runners: Dict[str, InMemoryRunner] = {}
_a2a_sessions: Dict[str, Any] = {}


async def get_or_create_runner_session(context_id: str):
    """Get or create a runner and session for A2A conversation."""
    if context_id not in _a2a_runners:
        runner = InMemoryRunner(agent=root_agent, app_name="auto_learn")
        _a2a_runners[context_id] = runner
        try:
            session = await runner.session_service.create_session(
                app_name="auto_learn",
                user_id=f"a2a_user_{context_id}",
            )
            _a2a_sessions[context_id] = session
        except Exception as e:
            logger.warning(f"A2A session creation warning: {e}")
            _a2a_sessions[context_id] = type("obj", (object,), {"id": context_id})

    return _a2a_runners[context_id], _a2a_sessions[context_id]


@app.post("/message:send", response_model=Dict[str, Any])
async def a2a_send_message(request: SendMessageRequest):
    """A2A Protocol endpoint for conversational interaction."""
    try:
        context_id = request.contextId or request.conversationId or str(uuid.uuid4())
        runner, session = await get_or_create_runner_session(context_id)

        user_text = ""
        if request.message.parts:
            for part in request.message.parts:
                if part.text:
                    user_text += part.text + " "

        if not user_text.strip():
            raise HTTPException(status_code=400, detail="Empty message")

        adk_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=user_text.strip())],
        )

        agent_response_text = ""
        async for event in runner.run_async(
            user_id=f"a2a_user_{context_id}",
            session_id=session.id,
            new_message=adk_message,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        agent_response_text += part.text

        task_id = str(uuid.uuid4())
        return {
            "task": Task(
                id=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state="completed",
                    message=Message(
                        messageId=str(uuid.uuid4()),
                        role="ROLE_AGENT",
                        parts=[Part(text=agent_response_text)],
                    ),
                ),
            ).dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"A2A error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Research API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/research/start")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start a new autonomous research session."""
    _require_db()
    session_id = str(uuid.uuid4())
    config = request.config or ResearchConfig()

    depth_iterations = {"quick": 2, "standard": 5, "deep": 10}
    max_iter = config.max_iterations or depth_iterations.get(config.depth, 5)

    # Store data sources metadata (type + label, no full content)
    session_data_sources = []
    if request.data_sources:
        for ds in request.data_sources:
            session_data_sources.append({
                "type": ds.type,
                "label": ds.label or "",
                "content": ds.content[:200] if ds.type == "url" else "",
            })

    session = {
        "session_id": session_id,
        "topic": request.topic,
        "status": "queued",
        "current_iteration": 0,
        "current_step": "Starting...",
        "max_iterations": max_iter,
        "best_iteration": 0,
        "best_score": 0.0,
        "iterations": [],
        "best_report": None,
        "created_at": _now(),
        "updated_at": _now(),
        "error": None,
        "data_sources": session_data_sources,
        "config": {
            "depth": config.depth,
            "focus_areas": config.focus_areas,
            "enable_web_search": config.enable_web_search,
            "data_sources_count": len(request.data_sources) if request.data_sources else 0,
        },
    }
    _research_sessions[session_id] = session

    # Persist initial session to DB (if configured)
    if is_db_configured():
        await db_save_session(session)

    background_tasks.add_task(run_research_loop, session_id, request)

    return {
        "session_id": session_id,
        "status": "queued",
        "topic": request.topic,
        "max_iterations": max_iter,
    }


@app.post("/api/tasks/start")
async def start_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Start a new task with any registered pipeline (generic endpoint)."""
    _require_db()
    session_id = str(uuid.uuid4())
    config = request.config or TaskConfig()

    max_iter = config.max_iterations
    if config.depth == "quick":
        max_iter = min(max_iter, 2)
    elif config.depth == "deep":
        max_iter = max(max_iter, 8)

    # Data sources metadata (label + preview only, no full content)
    session_data_sources = []
    if request.data_sources:
        for ds in request.data_sources:
            session_data_sources.append({
                "type": ds.type,
                "label": ds.label or "",
                "content": ds.content[:200] if ds.type == "url" else "",
            })

    session = {
        "session_id": session_id,
        "pipeline_id": request.pipeline_id,      # which pipeline
        "label": request.label,                   # generic task label
        "topic": request.label,                   # backward compat alias
        "task_inputs": request.inputs or {},       # pipeline-specific inputs
        "status": "queued",
        "current_iteration": 0,
        "current_step": "Starting...",
        "max_iterations": max_iter,
        "best_iteration": 0,
        "best_score": 0.0,
        "iterations": [],
        "best_report": None,
        "created_at": _now(),
        "updated_at": _now(),
        "error": None,
        "data_sources": session_data_sources,
        "config": {
            "depth": config.depth,
            "max_iterations": max_iter,
            "extra": config.extra or {},
            "data_sources_count": len(request.data_sources) if request.data_sources else 0,
        },
    }
    _research_sessions[session_id] = session

    if is_db_configured():
        await db_save_session(session)

    background_tasks.add_task(run_task_loop, session_id, request)

    return {
        "session_id": session_id,
        "pipeline_id": request.pipeline_id,
        "label": request.label,
        "status": "queued",
        "max_iterations": max_iter,
    }


@app.get("/api/research/{session_id}")
async def get_research_status(session_id: str):
    """Get the status and progress of a research session. Checks memory first, then Postgres, then Langfuse."""
    # 1. Check in-memory
    session = _research_sessions.get(session_id)
    if session:
        return ResearchResponse(
            session_id=session["session_id"],
            status=session["status"],
            topic=session["topic"],
            current_iteration=session["current_iteration"],
            max_iterations=session["max_iterations"],
            best_score=session["best_score"],
            current_step=session.get("current_step"),
            iterations=[IterationSnapshot(**s) for s in session["iterations"]],
            report=session["best_report"] if session["status"] == "completed" else None,
            data_sources=session.get("data_sources"),
        )

    # 2. Check Postgres (persistent storage)
    _require_db()
    db_session = await db_get_session(session_id)
    if db_session:
        return ResearchResponse(
            session_id=db_session["session_id"],
            status=db_session["status"],
            topic=db_session["topic"],
            current_iteration=db_session["current_iteration"],
            max_iterations=db_session["max_iterations"],
            best_score=db_session["best_score"],
            current_step=db_session.get("current_step"),
            iterations=[IterationSnapshot(**s) for s in db_session["iterations"]],
            report=db_session.get("best_report"),
            data_sources=db_session.get("data_sources"),
        )

    # 3. Optional: Langfuse (historical session)
    if LANGFUSE_ENABLED and _langfuse:
        lf_session = _load_session_from_langfuse(session_id)
        if lf_session:
            return lf_session

    raise HTTPException(status_code=404, detail="Research session not found")


@app.get("/api/research/{session_id}/report")
async def get_research_report(session_id: str):
    """Get the current best research report. Checks memory first, then Langfuse."""
    # In-memory
    session = _research_sessions.get(session_id)
    if session:
        return {
            "session_id": session_id,
            "topic": session["topic"],
            "status": session["status"],
            "best_score": session["best_score"],
            "best_iteration": session["best_iteration"],
            "report": session["best_report"],
            "iterations_completed": len(session["iterations"]),
        }

    # Postgres fallback
    _require_db()
    db_session = await db_get_session(session_id)
    if db_session:
        return {
            "session_id": session_id,
            "topic": db_session["topic"],
            "status": db_session["status"],
            "best_score": db_session["best_score"],
            "best_iteration": db_session.get("best_iteration", 0),
            "report": db_session.get("best_report"),
            "iterations_completed": len(db_session.get("iterations", [])),
        }

    # Optional Langfuse fallback
    if LANGFUSE_ENABLED and _langfuse:
        lf = _load_session_from_langfuse(session_id)
        if lf:
            return {
                "session_id": session_id,
                "topic": lf.topic,
                "status": lf.status,
                "best_score": lf.best_score,
                "best_iteration": lf.current_iteration,
                "report": lf.report,
                "iterations_completed": len(lf.iterations),
            }

    raise HTTPException(status_code=404, detail="Research session not found")


@app.get("/api/research/sessions/list")
async def list_research_sessions():
    """List all sessions: merge in-memory (active) + Postgres (historical) + Langfuse (optional)."""
    sessions = []
    seen_ids = set()

    # 1. In-memory sessions (active / recent)
    for sid, s in _research_sessions.items():
        seen_ids.add(sid)
        sessions.append({
            "session_id": s["session_id"],
            "topic": s["topic"],
            "status": s["status"],
            "current_iteration": s["current_iteration"],
            "max_iterations": s["max_iterations"],
            "best_score": s["best_score"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "source": "memory",
        })

    # 2. Postgres historical sessions
    _require_db()
    db_sessions = await db_list_sessions()
    for s in db_sessions:
        if s["session_id"] in seen_ids:
            continue
        seen_ids.add(s["session_id"])
        sessions.append(
            {
                "session_id": s["session_id"],
                "topic": s["topic"],
                "status": s["status"],
                "current_iteration": s["current_iteration"],
                "max_iterations": s["max_iterations"],
                "best_score": s["best_score"],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "source": "postgres",
            }
        )

    # 3. Optional Langfuse historical sessions (from cache — fast)
    if LANGFUSE_ENABLED and _langfuse:
        _refresh_langfuse_cache()
        for lf_session in _langfuse_cache_list:
            if lf_session["session_id"] not in seen_ids:
                seen_ids.add(lf_session["session_id"])
                sessions.append(lf_session)

    return {"sessions": sessions, "count": len(sessions)}


@app.delete("/api/research/{session_id}")
async def delete_research_session(session_id: str):
    """Cancel/delete a research session."""
    session = _research_sessions.get(session_id)
    if session:
        if session["status"] == "running":
            session["status"] = "cancelled"
        del _research_sessions[session_id]

    # Delete from Postgres (no-op if not present)
    _require_db()
    await db_delete_session(session_id)

    return {"message": f"Session {session_id} deleted (if it existed)", "status": "deleted"}


@app.post("/api/research/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file, extract its text content on the fly, and return it without storing."""
    from tools.file_reader import read_file
    import tempfile

    content = await file.read()
    ext = os.path.splitext(file.filename)[1].lower()

    # Write to a temp file for extraction, then delete immediately
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = read_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    if "error" in result:
        return {"error": result["error"], "file_name": file.filename}

    return {
        "file_name": file.filename,
        "text": result.get("text", ""),
        "char_count": result.get("char_count", 0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Utility Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "auto_learn",
        "version": "1.0.0",
        "active_sessions": len(_research_sessions),
        "running_sessions": sum(1 for s in _research_sessions.values() if s["status"] == "running"),
    }


@app.get("/api/info")
async def api_info():
    return {
        "name": "EverLearn Agent",
        "version": "1.0.0",
        "description": "Autonomous iterative learning with quality ratchet — inspired by Karpathy's autoresearch",
        "pipeline": [
            "1. Research Planner — identifies gaps and generates search strategy",
            "2. Source Collector — gathers info from web, URLs, and files",
            "3. Deep Researcher — analyzes sources, extracts findings",
            "4. Report Synthesizer — produces comprehensive markdown report",
            "5. Quality Evaluator — scores and decides keep/discard (ratchet)",
        ],
        "endpoints": {
            "GET /api/pipelines": "List all registered orchestration pipelines",
            "POST /api/research/start": "Start a new research session",
            "GET /api/research/{id}": "Get session status and progress",
            "GET /api/research/{id}/report": "Get the best research report",
            "GET /api/research/sessions/list": "List all sessions",
            "DELETE /api/research/{id}": "Delete a session",
            "POST /api/research/upload": "Upload a file for research",
            "GET /health": "Health check",
            "GET /.well-known/agent-card.json": "A2A agent discovery",
            "POST /message:send": "A2A conversational endpoint",
        },
    }


@app.get("/api/db/status")
async def db_status():
    """Quick DB connectivity check (no secrets)."""
    if not is_db_configured():
        return {"configured": False, "ready": False}
    return {
        "configured": True,
        "ready": DB_READY,
        "host": os.getenv("DATABASE_HOST"),
        "port": os.getenv("DATABASE_PORT"),
        "name": os.getenv("DATABASE_NAME"),
        "user": os.getenv("DATABASE_USER"),
        "sslmode": os.getenv("DATABASE_SSLMODE") or "",
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    html_path = os.path.join(UI_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>EverLearn</h1><p>UI not found. API available at /docs</p>"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
