# EverLearn — Learning Protocol

> Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) `program.md`.
> This file is the unified specification that governs how the EverLearn Agent operates.

---

## 1. Overview

EverLearn is an EverLearn Agent. Given a topic, optional data sources, and configuration, it runs a ratcheted learning loop: each iteration builds on the previous best, and only improvements survive.

### Core Loop

```
for each iteration (1..max_iterations):
    1. PLAN    — Research Planner identifies gaps, generates search queries
    2. COLLECT — Source Collector executes web searches, fetches URLs, reads files
    3. ANALYZE — Deep Researcher extracts findings, patterns, contradictions
    4. SYNTHESIZE — Report Synthesizer produces a markdown research report
    5. EVALUATE — Quality Evaluator scores new vs previous best (10 dimensions)
    6. RATCHET — If score improved: KEEP new report. If not: DISCARD, keep previous.
```

Early termination triggers:
- Quality score reaches 90+ (excellent)
- 3 consecutive iterations discarded (converged)

---

## 2. Constraints

### 2.1 What Gets Modified
Only the **research report** changes between iterations. The pipeline agents, tools, and evaluation criteria are immutable (like Karpathy's `prepare.py`).

### 2.2 Data Sources
- **User-provided**: URLs, uploaded files, raw text (available from iteration 1)
- **Web search**: DuckDuckGo (fallback) or Google Custom Search (if configured)
- **Previous research**: The best report from prior iterations is injected as context

### 2.3 Evaluation Must Be Objective
The Quality Evaluator scores on 10 dimensions (each 1-10, total 0-100):

| Dimension | What It Measures |
|---|---|
| Comprehensiveness | How thoroughly the topic is covered |
| Accuracy | Are claims supported by cited sources? |
| Depth | Beyond surface-level analysis? |
| Clarity | Well-written, easy to understand? |
| Source Quality | Credible, diverse sources? |
| Focus Coverage | Addresses user-specified focus areas? |
| Structure | Well-organized, logical flow? |
| Novelty | Non-obvious insights surfaced? |
| Evidence | Claims backed by specific evidence? |
| Actionability | Useful, actionable conclusions? |

Rules:
- Score strictly: 5 is average, 7 is good, 9+ is exceptional
- A new report is NOT always better — sometimes iteration degrades quality
- If the new report lost important content from the previous version, penalize it
- `is_improvement` is true ONLY if `new_score > previous_score`

### 2.4 Report Format
Every research report must follow this structure:

```markdown
# [Topic]: Comprehensive Analysis

## Executive Summary
## 1. Introduction
## 2. Key Findings
### 2.1 [Category]
### 2.2 [Category]
## 3. Analysis & Discussion
## 4. Data & Statistics
## 5. Expert Perspectives
## 6. Gaps and Limitations
## 7. Conclusions
## Sources
```

### 2.5 Iteration Strategy
- **Iteration 1**: Broad foundational research — cover the topic widely
- **Iterations 2-3**: Fill specific gaps identified in evaluation
- **Iterations 4+**: Deep dives into weak areas, find primary sources, verify claims

---

## 3. Architecture

### Files (mirroring Karpathy's autoresearch)

| File | Role | Karpathy Equivalent |
|---|---|---|
| `research_protocol.md` | This spec — governs the loop | `program.md` |
| `prepare.py` | Orchestration, evaluation, API server | `prepare.py` |
| `train.py` | Agent pipeline definitions | `train.py` |
| `sub_agents/` | Specialist agents (planner, collector, researcher, synthesizer, evaluator) | *(single agent in Karpathy's)* |
| `tools/` | Web search, URL fetch, file reader, text utilities | *(PyTorch/tokenizer in Karpathy's)* |
| `ui/` | Web interface for input, progress tracking, results | *(CLI in Karpathy's)* |
| `a2a_models.py` | A2A protocol models for agent discovery | *(N/A)* |

### Agent Pipeline (defined in train.py)

```
research_iteration_pipeline (SequentialAgent)
  |-- research_planner_agent     → output_key: "research_plan"
  |-- source_collector_agent     → output_key: "collected_sources"
  |-- deep_researcher_agent      → output_key: "research_analysis"
  |-- report_synthesizer_agent   → output_key: "research_report"

quality_evaluator_agent (standalone) → output_key: "quality_evaluation"
```

### Ratchet Loop (implemented in prepare.py)

```python
for iteration in range(1, max_iterations + 1):
    # Run pipeline → produces new_report
    # Run evaluator → produces quality_evaluation
    # If is_improvement or first iteration:
    #     best_report = new_report (KEEP)
    # Else:
    #     discard new_report (REVERT to previous best)
```

---

## 4. Configuration

| Parameter | Default | Description |
|---|---|---|
| `topic` | *(required)* | What to research |
| `max_iterations` | 5 | Maximum research iterations |
| `depth` | standard | quick (2), standard (5), deep (10) |
| `focus_areas` | *(optional)* | Comma-separated subtopics to prioritize |
| `enable_web_search` | true | Allow web search during collection |
| `data_sources` | *(optional)* | URLs, files, or raw text to include |

---

## 5. The Ratchet Principle

> "Only improvements survive."

This is the core design principle borrowed from Karpathy's autoresearch:

1. Each iteration starts from the **current best** — not from scratch
2. The evaluator compares **new vs previous best** — not new vs nothing
3. If the new version is worse, it is **discarded entirely** — the best is preserved
4. Over N iterations, quality can only go up or stay the same — never down
5. This creates a monotonically improving research document

The ratchet prevents:
- Regression (losing good content from earlier iterations)
- Drift (wandering away from the topic)
- Inflation (scoring higher without actually improving)
