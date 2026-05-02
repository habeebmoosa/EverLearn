"""
sub_agents/code_reviewer_agents.py

Three agents for the CodeReviewer pipeline:
  1. CodePlannerAgent    — analyses the code/diff and plans what to review
  2. CodeReviewAgent     — writes detailed review comments
  3. ReviewEvaluatorAgent — scores the review against quality dimensions
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field
from typing import List


# ── Pydantic output schema for the review evaluator ───────────────────────────

class ReviewDimensionScore(BaseModel):
    new: int = Field(..., ge=1, le=10)
    prev: int = Field(..., ge=0, le=10)


class ReviewScoringBreakdown(BaseModel):
    correctness: ReviewDimensionScore        # Issues flagged are real, not false positives
    actionability: ReviewDimensionScore      # Comments give specific, actionable fixes
    coverage: ReviewDimensionScore           # All important areas are checked
    severity_accuracy: ReviewDimensionScore  # Severity labels match actual impact
    clarity: ReviewDimensionScore            # Comments are clear and constructive
    completeness: ReviewDimensionScore       # No important issues missed
    context_awareness: ReviewDimensionScore  # Understands the intent of the code
    no_false_positives: ReviewDimensionScore # No nitpicks presented as critical bugs
    priority: ReviewDimensionScore           # Critical issues highlighted first
    constructiveness: ReviewDimensionScore   # Suggests fixes, not just criticizes


class ReviewEvaluation(BaseModel):
    new_score: int = Field(..., ge=0, le=100)
    previous_score: int = Field(..., ge=0, le=100)
    is_improvement: bool
    scoring_breakdown: ReviewScoringBreakdown
    improvement_summary: str
    remaining_gaps: List[str] = Field(default_factory=list)


# ── Agent 1: Code Planner ──────────────────────────────────────────────────────

CODE_PLANNER_INSTRUCTION = """\
You are a Senior Code Review Strategist. Your job is to plan a thorough code review.

## Session State Available
- **task_label**: Description of what the code/PR is doing
- **language**: Programming language (e.g. Python, TypeScript, Java)
- **focus**: Review focus areas (security, performance, correctness, style, etc.)
- **review_level**: Depth of review (quick/thorough/exhaustive)
- **code_content**: The code, diff, or PR description to review
- **iteration_number**: Current iteration
- **previous_best_review**: Best review from previous iterations (empty on first)
- **previous_gaps**: Gaps identified in the previous evaluation

## Your Task
Produce a JSON review plan with these keys:
- "areas_to_check": List of specific areas to examine (e.g. "input validation", "error handling", "SQL injection", "race conditions")
- "approach": One paragraph describing the review strategy for this iteration
- "improvements_over_last": List of gaps from previous review to specifically address (empty on first iteration)
- "severity_framework": Brief note on how to classify Critical/High/Medium/Low/Info issues for this codebase

Focus on what was MISSED in the previous review. If no previous review, do a comprehensive scan.
Output ONLY the JSON object.
"""

code_planner_agent = LlmAgent(
    name="code_planner_agent",
    model="gemini-2.5-flash",
    instruction=CODE_PLANNER_INSTRUCTION,
    description="Plans the review strategy — what areas to check and how deeply",
    output_key="review_plan",
)


# ── Agent 2: Code Reviewer ────────────────────────────────────────────────────

CODE_REVIEWER_INSTRUCTION = """\
You are an Expert Code Reviewer. Write precise, actionable, constructive review comments.

## Session State Available
- **task_label**: What the code/PR is trying to do
- **language**: Programming language
- **focus**: Review focus areas
- **review_level**: Depth (quick/thorough/exhaustive)
- **code_content**: The code, diff, or PR description
- **review_plan**: Strategic plan from the Code Planner
- **previous_best_review**: Best previous review (empty on first iteration)

## Your Task
Write a structured code review. Format:

### Summary
Brief overview of the code quality and main findings.

### Issues Found

For each issue, use this format:
**[SEVERITY] Short title**
- **Location**: file/function/line if identifiable, or "General"
- **Issue**: What exactly is wrong and why it matters
- **Fix**: Specific code or approach to fix it

Severity levels: 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ℹ️ Info

### What's Good
Briefly note patterns, decisions, or code that is well done.

### Recommended Next Steps
Ordered list of the 3-5 most important things to address first.

## Rules
1. If a previous review exists: IMPROVE it — add what was missed, correct wrong assessments, refine
2. Never remove a valid issue from the previous review unless it was a false positive
3. Be specific — "line 42: unvalidated user input passed to SQL query" not "check for SQL injection"
4. For Critical/High issues always provide a fix example
5. Be constructive — assume the developer is competent, just missed something
6. Focus on the areas specified in the review_plan
"""

code_reviewer_agent = LlmAgent(
    name="code_reviewer_agent",
    model="gemini-2.5-flash",
    instruction=CODE_REVIEWER_INSTRUCTION,
    description="Writes detailed, actionable code review comments",
    output_key="code_review",
)


# ── Agent 3: Review Quality Evaluator ────────────────────────────────────────

REVIEW_EVALUATOR_INSTRUCTION = """\
You are a Code Review Quality Auditor. Objectively score a code review and determine
if it's better than the previous best.

## Session State Available
- **new_review**: The newly written code review
- **previous_best_review**: The previous best review (empty on first iteration)
- **task_label**: What the code/PR does
- **language**: Programming language
- **focus**: Review focus areas
- **code_content**: The original code/diff being reviewed

## Scoring Dimensions (10 points each, total 100)

1. **Correctness** (1-10): Issues flagged are real — not false positives
2. **Actionability** (1-10): Every comment has a specific, implementable fix
3. **Coverage** (1-10): All important areas are checked (security, perf, logic, etc.)
4. **Severity Accuracy** (1-10): Critical/High/Medium/Low labels are appropriate
5. **Clarity** (1-10): Comments are clear, jargon-free, easy to act on
6. **Completeness** (1-10): No obvious important issues left unchecked
7. **Context Awareness** (1-10): Reviewer understands what the code is trying to do
8. **No False Positives** (1-10): No nitpicks labeled as bugs; style issues labeled correctly
9. **Priority** (1-10): Most critical issues are prominently highlighted
10. **Constructiveness** (1-10): Tone is helpful; suggests improvements, not just criticizes

## Critical Rules
- Score STRICTLY: 5 = average, 7 = good, 9+ = exceptional
- `is_improvement` is true ONLY if new_score > previous_score
- First iteration (no previous): set previous_score=0, is_improvement=true
- `remaining_gaps` should list 3-5 specific review areas or issue types still missing
- If the new review removed a valid finding from the previous one, penalise it
"""

review_evaluator_agent = LlmAgent(
    name="review_evaluator_agent",
    model="gemini-2.5-flash",
    instruction=REVIEW_EVALUATOR_INSTRUCTION,
    description="Scores code review quality on 10 professional dimensions",
    output_schema=ReviewEvaluation,
    output_key="review_evaluation",
)
