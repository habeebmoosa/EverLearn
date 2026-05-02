"""
Quality Evaluator Agent

Compares the new research report against the previous best. Scores both
on multiple dimensions and decides whether the new version is an improvement.
This is the "ratchet mechanism" — only improvements are kept.

Uses Pydantic output_schema for guaranteed structured JSON output.
"""

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from typing import List, Optional


class DimensionScore(BaseModel):
    new: int = Field(..., ge=1, le=10)
    prev: int = Field(..., ge=0, le=10)


class ScoringBreakdown(BaseModel):
    comprehensiveness: DimensionScore
    accuracy: DimensionScore
    depth: DimensionScore
    clarity: DimensionScore
    source_quality: DimensionScore
    focus_coverage: DimensionScore
    structure: DimensionScore
    novelty: DimensionScore
    evidence: DimensionScore
    actionability: DimensionScore


class QualityEvaluation(BaseModel):
    new_score: int = Field(..., ge=0, le=100, description="Total score for new report (sum of 10 dimensions)")
    previous_score: int = Field(..., ge=0, le=100, description="Total score for previous report (0 if first iteration)")
    is_improvement: bool = Field(..., description="True only if new_score > previous_score")
    scoring_breakdown: ScoringBreakdown
    improvement_summary: str = Field(..., description="Brief description of what improved or degraded")
    remaining_gaps: List[str] = Field(default_factory=list, description="Specific gaps for future iterations to address")


QUALITY_EVALUATOR_INSTRUCTION = """You are a Research Quality Evaluator. Your critical job is to objectively compare a new research report against the previous best version and determine which is superior.

## Available Context
Review the session state for:
- **new_report**: The newly generated research report
- **previous_best_report**: The previous best report (empty string if first iteration)
- **topic**: The research topic
- **focus_areas**: User-specified focus areas (comma-separated)
- **iteration_number**: Current iteration number
- **new_report_stats**: Pre-computed word/sentence/section counts for the new report
- **previous_report_stats**: Pre-computed word/sentence/section counts for the previous report
- **new_report_coverage**: Pre-computed focus area coverage score for the new report
- **previous_report_coverage**: Pre-computed focus area coverage score for the previous report

## Your Task

### If this is the FIRST iteration (no previous report):
Score the new report on its own merits. Set `is_improvement` to true and `previous_score` to 0.

### If there IS a previous report:
1. Review the pre-computed stats and coverage scores in session state
2. Score BOTH reports on all 10 dimensions
3. Determine if the new report is genuinely better

## Scoring Dimensions (10 points each, total 100)

Rate each dimension 1-10:

1. **Comprehensiveness** (1-10): How thoroughly does it cover the topic?
2. **Accuracy** (1-10): Are claims well-supported by cited sources?
3. **Depth** (1-10): Does it go beyond surface-level analysis?
4. **Clarity** (1-10): Is it well-written and easy to understand?
5. **Source Quality** (1-10): Are sources credible and diverse?
6. **Focus Coverage** (1-10): Does it address user-specified focus areas?
7. **Structure** (1-10): Is the report well-organized with logical flow?
8. **Novelty** (1-10): Does it surface non-obvious insights?
9. **Evidence** (1-10): Are claims backed by specific evidence?
10. **Actionability** (1-10): Does it provide useful, actionable conclusions?

## Critical Rules
- Be OBJECTIVE. Do not inflate scores to show improvement.
- A new report is NOT always better — sometimes iteration degrades quality.
- If the new report lost important content from the previous version, penalize it.
- Score strictly: 5 is average, 7 is good, 9+ is exceptional.
- `is_improvement` should be true ONLY if `new_score > previous_score`.
- For first iteration, set `previous_score` to 0 and `is_improvement` to true.
- The `remaining_gaps` field guides future iterations — be specific.
"""

quality_evaluator_agent = LlmAgent(
    name="quality_evaluator_agent",
    model="gemini-2.5-flash",
    instruction=QUALITY_EVALUATOR_INSTRUCTION,
    description="Evaluates research quality by comparing iterations and scoring on 10 dimensions",
    output_schema=QualityEvaluation,
    output_key="quality_evaluation",
)
