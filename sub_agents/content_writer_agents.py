"""
sub_agents/content_writer_agents.py

Three agents for the ContentWriter pipeline:
  1. ContentPlannerAgent   — analyses the task & previous draft, identifies gaps
  2. ContentWriterAgent    — writes / improves the content
  3. ContentEvaluatorAgent — scores the draft against a quality rubric
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from typing import List


# ── Pydantic output schema for the evaluator ──────────────────────────────────

class ContentDimensionScore(BaseModel):
    new: int = Field(..., ge=1, le=10)
    prev: int = Field(..., ge=0, le=10)


class ContentScoringBreakdown(BaseModel):
    clarity: ContentDimensionScore
    audience_fit: ContentDimensionScore
    completeness: ContentDimensionScore
    tone: ContentDimensionScore
    structure: ContentDimensionScore
    persuasiveness: ContentDimensionScore
    originality: ContentDimensionScore
    conciseness: ContentDimensionScore
    accuracy: ContentDimensionScore
    actionability: ContentDimensionScore


class ContentEvaluation(BaseModel):
    new_score: int = Field(..., ge=0, le=100)
    previous_score: int = Field(..., ge=0, le=100)
    is_improvement: bool
    scoring_breakdown: ContentScoringBreakdown
    improvement_summary: str
    remaining_gaps: List[str] = Field(default_factory=list)


# ── Agent 1: Content Planner ───────────────────────────────────────────────────

CONTENT_PLANNER_INSTRUCTION = """\
You are a Content Strategist. Your job is to plan how to write or improve content.

## Session State Available
- **task_label**: What needs to be written (e.g. "Q3 investor update email")
- **content_type**: Type of content (blog_post, email, policy, brief, report, etc.)
- **target_audience**: Who the content is for
- **tone**: Desired tone (professional, casual, technical, persuasive)
- **rubric**: User's quality criteria ("what makes a great version of this")
- **iteration_number**: Current iteration
- **previous_best_content**: The best version so far (empty on first iteration)
- **previous_gaps**: Gaps identified in the previous evaluation
- **data_sources**: Reference materials / context provided by the user

## Your Task
Produce a concise writing plan as a JSON object with these keys:
- "approach": One paragraph describing HOW to write/improve this content
- "key_points": List of 5-10 essential points the content must cover
- "improvements_to_make": List of specific improvements over the previous version
  (empty list if first iteration)
- "style_notes": Tone, structure, and formatting guidance

Be specific. If there is a previous version, focus the plan on addressing its gaps.
Output ONLY the JSON object.
"""

content_planner_agent = LlmAgent(
    name="content_planner_agent",
    model="gemini-2.5-flash",
    instruction=CONTENT_PLANNER_INSTRUCTION,
    description="Plans how to write or improve content for this iteration",
    output_key="content_plan",
)


# ── Agent 2: Content Writer ────────────────────────────────────────────────────

CONTENT_WRITER_INSTRUCTION = """\
You are an expert Content Writer. Your job is to produce high-quality content.

## Session State Available
- **task_label**: What needs to be written
- **content_type**: Type of content
- **target_audience**: Who the content is for
- **tone**: Desired tone
- **rubric**: Quality criteria from the user
- **content_plan**: The writing plan from the Content Planner
- **previous_best_content**: Previous best version (empty on first iteration)
- **data_sources**: Reference materials and context provided by the user

## Your Task
Write the content based on the plan. Rules:
1. Follow the content_plan exactly
2. Match the requested tone and target_audience
3. If a previous version exists: IMPROVE it — don't start from scratch
   - Keep everything that was good in the previous version
   - Fix every gap listed in the plan
   - Do NOT remove content unless it is factually wrong or off-topic
4. If no previous version: write the best possible first draft
5. Use the data_sources for factual grounding — cite them where relevant
6. Be specific and concrete — avoid vague filler phrases
7. Format appropriately for the content type (use markdown headings for reports,
   short paragraphs for emails, etc.)

Output ONLY the content itself — no meta-commentary, no "Here is the content:" prefix.
"""

content_writer_agent = LlmAgent(
    name="content_writer_agent",
    model="gemini-2.5-flash",
    instruction=CONTENT_WRITER_INSTRUCTION,
    description="Writes or improves content based on the strategic plan",
    output_key="content_draft",
)


# ── Agent 3: Content Evaluator ────────────────────────────────────────────────

CONTENT_EVALUATOR_INSTRUCTION = """\
You are a Content Quality Evaluator. Objectively compare a new draft against
the previous best and decide if it is genuinely better.

## Session State Available
- **new_content**: The newly written content
- **previous_best_content**: The previous best (empty on first iteration)
- **task_label**: What was requested
- **content_type**: Type of content
- **target_audience**: Who the content is for
- **tone**: Desired tone
- **rubric**: User's quality criteria

## Scoring Dimensions (10 points each, total 100)

1. **Clarity** (1-10): Is it easy to read and understand?
2. **Audience Fit** (1-10): Does it speak to the right audience in the right way?
3. **Completeness** (1-10): Does it cover all required points?
4. **Tone** (1-10): Does it match the requested tone throughout?
5. **Structure** (1-10): Is it well-organised with logical flow?
6. **Persuasiveness** (1-10): Does it convince / motivate the reader?
7. **Originality** (1-10): Is it distinctive — not generic boilerplate?
8. **Conciseness** (1-10): No padding, every sentence adds value?
9. **Accuracy** (1-10): Claims are factually correct and well-supported?
10. **Actionability** (1-10): Does it drive the reader to a clear next step?

## Critical Rules
- Score STRICTLY: 5 = average, 7 = good, 9+ = exceptional
- If the new draft lost something good from the previous version, penalise it
- `is_improvement` is true ONLY if new_score > previous_score
- For the first iteration (no previous), set previous_score=0, is_improvement=true
- `remaining_gaps` should list 3-5 specific things the next iteration should fix
"""

content_evaluator_agent = LlmAgent(
    name="content_evaluator_agent",
    model="gemini-2.5-flash",
    instruction=CONTENT_EVALUATOR_INSTRUCTION,
    description="Scores content quality and drives the ratchet decision",
    output_schema=ContentEvaluation,
    output_key="content_evaluation",
)
