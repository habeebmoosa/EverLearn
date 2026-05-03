# EverLearn Agent

An enterprise-grade autonomous research system inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch). It autonomously learns about any topic through iterative refinement, powered by a **quality ratchet mechanism** that guarantees research quality can only improve — never regress. Built with Google ADK + Gemini, FastAPI, and Langfuse observability.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Features](#features)
- [Architecture](#architecture)
- [The Quality Ratchet](#the-quality-ratchet)
- [Agent Pipeline](#agent-pipeline)
- [Tools](#tools)
- [Web Interface](#web-interface)
- [API Reference](#api-reference)
- [A2A Protocol](#a2a-agent-to-agent-protocol)
- [Observability](#observability)
- [Local Setup](#local-setup)
- [Docker Deployment](#docker-deployment)
- [Cloud Run Deployment](#cloud-run-deployment)
- [Configuration](#configuration)
- [Tech Stack](#tech-stack)

---

## How It Works

You provide a **topic**, optional **focus areas**, and optional **data sources** (URLs, files, or raw text). The agent then runs an iterative research loop:

```
For each iteration (1 to max):
  1. Plan    → Identify gaps, generate search strategy
  2. Collect → Fetch sources from web + user data
  3. Analyze → Extract findings, themes, contradictions
  4. Write   → Synthesize a comprehensive research report
  5. Evaluate → Score the new report against the previous best

  If improved → Keep the new report (ratchet forward)
  If not      → Discard and try again from the best version

  Stop early if score >= 90 or 3 consecutive discards
```

The result is a high-quality, well-structured research report that gets better with each iteration.

---

## Features

### Iterative Research with Quality Ratchet
The core innovation. Each iteration produces a new report that is scored against the previous best on **10 dimensions**. Only improvements are kept — the system never regresses. This guarantees monotonic quality improvement across iterations.

### Multi-Source Data Collection
- **Web Search** — Cascading fallback: Google Custom Search → SerpAPI → DuckDuckGo
- **URL Fetching** — Scrape any URL with intelligent HTML cleanup (strips nav, headers, scripts)
- **File Upload** — PDF (up to 50 pages), DOCX, TXT, MD, CSV, JSON, HTML
- **Raw Text** — Paste content directly into the session

### Configurable Research Depth
| Mode | Iterations | Best For |
|------|-----------|----------|
| Quick | 2 | Fast overviews, simple topics |
| Standard | 5 | Balanced research, most use cases |
| Deep | 10 | Thorough investigation, complex topics |

Custom iteration limits (1–20) are also supported.

### 10-Dimension Quality Scoring
Every report is evaluated on:

| Dimension | What It Measures |
|-----------|-----------------|
| Comprehensiveness | Breadth of topic coverage |
| Accuracy | Factual correctness and source backing |
| Depth | Level of detail and nuance |
| Clarity | Readability and organization |
| Source Quality | Credibility and diversity of sources |
| Focus Coverage | How well focus areas are addressed |
| Structure | Report organization and flow |
| Novelty | Unique insights beyond surface-level info |
| Evidence | Data, statistics, and expert citations |
| Actionability | Practical takeaways and recommendations |

Each dimension is scored 0–10 (strict scale: 5 = average, 7 = good, 9+ = exceptional), yielding a total quality score of 0–100.

### Structured Report Output
Every report follows a consistent format:
- Executive Summary
- Introduction
- Key Findings (categorized subsections)
- Analysis & Discussion (patterns, contradictions, implications)
- Data & Statistics
- Expert Perspectives
- Gaps and Limitations
- Conclusions
- Sources (numbered references)

Reports target 2,000–5,000 words and can be exported as **PDF** or **Markdown**.

### Real-Time Web UI
A full-featured web interface with:
- Live progress tracking with activity feed
- Quality score chart showing improvement over iterations
- Session management (start, view, delete)
- File upload with instant text extraction
- Report viewing with markdown rendering
- PDF and Markdown download

### Full Observability
Every agent call, iteration, and evaluation is traced via Langfuse + OpenTelemetry. View token usage, latency, cost, and the full trace hierarchy for any session.

### A2A Protocol Support
Implements the Agent-to-Agent (A2A) discovery and messaging protocol, allowing other agents to discover and interact with this agent programmatically.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Server                        │
│                        (prepare.py)                          │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   REST API   │  │   Web UI     │  │   A2A Endpoint    │  │
│  │  /api/...    │  │   /static    │  │  /message:send    │  │
│  └──────┬───────┘  └──────────────┘  └───────────────────┘  │
│         │                                                    │
│  ┌──────▼──────────────────────────────────────────────┐     │
│  │            Orchestration Loop                        │     │
│  │   for each iteration:                                │     │
│  │     run_iteration_pipeline()                         │     │
│  │     run_quality_evaluator()                          │     │
│  │     apply_ratchet_decision()                         │     │
│  └──────┬──────────────────────────────────────────────┘     │
│         │                                                    │
└─────────┼────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Agent Pipeline (train.py)                        │
│              SequentialAgent                                  │
│                                                              │
│  ┌────────────────┐    ┌────────────────┐                    │
│  │ Research        │───▶│ Source          │                    │
│  │ Planner         │    │ Collector       │                    │
│  │                 │    │                 │                    │
│  │ Identifies gaps │    │ web_search()    │                    │
│  │ Plans queries   │    │ fetch_url()     │                    │
│  └────────────────┘    └───────┬────────┘                    │
│                                │                              │
│  ┌────────────────┐    ┌──────▼─────────┐                    │
│  │ Report          │◀───│ Deep            │                    │
│  │ Synthesizer     │    │ Researcher      │                    │
│  │                 │    │                 │                    │
│  │ Markdown report │    │ Analyzes sources│                    │
│  │ 2000-5000 words │    │ Extracts themes │                    │
│  └────────────────┘    └────────────────┘                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────┐
│ Quality Evaluator │
│                   │
│ 10-dim scoring    │
│ Ratchet decision  │
│ Gap identification│
└──────────────────┘
```

---

## The Quality Ratchet

The ratchet mechanism is inspired by the principle that research quality should only move forward. Here's how it works:

1. **Iteration N** produces a new research report
2. The **Quality Evaluator** scores both the new report and the current best on 10 dimensions
3. If `new_score > best_score` → the new report becomes the best (ratchet forward)
4. If `new_score <= best_score` → the new report is discarded; the best remains unchanged
5. The next iteration always builds on the **best** version, never a discarded one

**Early termination** triggers when:
- The best score reaches **90 or above** (excellent quality achieved)
- **3 consecutive iterations** are discarded (diminishing returns)

This ensures the system converges toward high quality without wasting compute on unproductive iterations.

---

## Agent Pipeline

### 1. Research Planner Agent
**Role:** Strategic planning for the current iteration.

Analyzes the topic, focus areas, and any gaps identified in previous evaluations. Generates 3–7 targeted search queries that evolve with each iteration:
- **Iteration 1:** Broad foundational queries
- **Iterations 2–3:** Gap-filling and targeted follow-up
- **Iterations 4+:** Deep dives, primary sources, verification

Always includes user-provided URLs and file content in the plan.

### 2. Source Collector Agent
**Role:** Gather research materials from all available sources.

Executes the search queries and URL fetches from the plan. Never fabricates content — always calls tools to retrieve real data. Outputs a structured collection with source metadata (title, URL, content, relevance, type).

### 3. Deep Researcher Agent
**Role:** Rigorous analysis of collected sources.

Pure analysis agent (no tool access). Processes all collected sources and extracts:
- Key findings with evidence and confidence levels
- Cross-source themes and patterns
- Contradictions between sources
- Statistics with context
- Expert opinions
- New questions for further exploration

### 4. Report Synthesizer Agent
**Role:** Produce the final research report.

Takes the analysis and synthesizes a comprehensive, well-structured markdown report. If a previous report exists, it incorporates new findings, fills identified gaps, and strengthens weak sections rather than starting from scratch.

### 5. Quality Evaluator Agent
**Role:** Objective quality assessment and ratchet decision.

Scores the new report against the previous best on 10 dimensions using Pydantic-enforced structured output. Returns a clear `is_improvement` boolean that drives the ratchet mechanism, along with specific remaining gaps to guide the next iteration.

---

## Tools

### Web Search (`tools/web_search.py`)
Multi-engine search with cascading fallback:
1. **Google Custom Search** (if `GOOGLE_SEARCH_CX` configured)
2. **SerpAPI** (if `SERPAPI_API_KEY` configured)
3. **DuckDuckGo** (always available, with 3s rate-limit protection)

Returns up to 8 results per query with titles, URLs, and snippets.

### URL Fetcher (`tools/web_fetch.py`)
Fetches and cleans web page content:
- Strips scripts, styles, navigation, headers, footers
- Decodes HTML entities
- Rate limited to 40 requests per 60 seconds
- Truncates to 15,000 characters per page

### File Reader (`tools/file_reader.py`)
Extracts text from uploaded files:
- **PDF** — Via PyPDF2 (up to 50 pages)
- **DOCX** — Via python-docx
- **Text** — TXT, MD, CSV, JSON, HTML (UTF-8 with latin-1 fallback)

### Research Utilities (`tools/research_utils.py`)
Helper functions for report analysis:
- Word/sentence/paragraph counting
- Focus area coverage scoring (keyword frequency analysis, 0–100 per area)
- Citation extraction (URLs, markdown refs, numbered refs)
- Text chunking with overlap for large documents

---

## Web Interface

### Session Management
The left sidebar shows all research sessions with their status, topic, iteration count, and best score. Click any session to view its details.

### New Session Form
- **Topic** — What to research (required, up to 500 characters)
- **Focus Areas** — Comma-separated subtopics to prioritize (e.g., "security, performance, cost")
- **Depth** — Quick (2), Standard (5), or Deep (10) iterations
- **Max Iterations** — Fine-grained control (1–20)
- **Web Search** — Toggle on/off
- **Data Sources** — Add URLs, paste text, or upload files

### Live Progress
While a session runs, the UI shows:
- Status indicator (running / completed / failed)
- Metrics bar: best score, iterations, kept/discarded, sources, duration
- Progress bar with percentage
- Current step description
- Activity feed with per-iteration details (score, kept/discarded, sources, queries, duration)
- Quality score chart plotting improvement over iterations

### Report View
Once complete, the full report renders as formatted markdown. Download as PDF (via html2pdf.js) or Markdown.

---

## API Reference

### Research Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/research/start` | Start a new research session |
| `GET` | `/api/research/{session_id}` | Get session status and progress |
| `GET` | `/api/research/{session_id}/report` | Get the final research report |
| `GET` | `/api/research/sessions/list` | List all sessions |
| `DELETE` | `/api/research/{session_id}` | Cancel or delete a session |
| `POST` | `/api/research/upload` | Upload a file and extract text |

### Start Session Request
```json
{
  "topic": "Autonomous AI Agents",
  "focus_areas": ["architecture", "safety", "real-world applications"],
  "max_iterations": 5,
  "depth": "standard",
  "enable_web_search": true,
  "data_sources": [
    {"type": "url", "value": "https://example.com/article"},
    {"type": "text", "value": "Relevant context or notes..."},
    {"type": "file", "value": "extracted file text...", "filename": "paper.pdf"}
  ]
}
```

### Observability Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/research/{session_id}/metrics` | Langfuse metrics (tokens, cost, latency) |
| `POST` | `/api/research/refresh-cache` | Force refresh Langfuse cache |

### Utility Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check (returns active/running session counts) |
| `GET` | `/api/info` | API info and pipeline description |

---

## A2A (Agent-to-Agent) Protocol

The agent implements the A2A discovery and messaging protocol (v0.3):

- **Discovery:** `GET /.well-known/agent-card.json` returns the agent card with capabilities, supported input/output modes, and endpoint info.
- **Messaging:** `POST /message:send` accepts conversational messages. The agent maintains session state per `context_id`, enabling multi-turn research conversations.

This allows other agents or orchestrators to discover and interact with this agent programmatically without the web UI.

---

## Observability

All agent calls are traced via **Langfuse + OpenTelemetry**:

```
learning_session (top-level trace)
├── learning_iteration_pipeline (per iteration)
│   ├── research_planner_agent
│   ├── source_collector_agent
│   ├── deep_researcher_agent
│   └── report_synthesizer_agent
└── quality_evaluator (per iteration)
```

Each trace captures:
- Token usage (input/output per agent)
- Latency per step
- Cost estimation
- Session metadata (topic, config, scores)
- Iteration details (sources collected, queries executed, kept/discarded)

Sessions are stored both in-memory (active) and in Langfuse (historical), with a 60-second cache TTL.

---

## Local Setup

### Prerequisites
- Python 3.9+
- A Google API key ([get one here](https://aistudio.google.com/apikey))
- Langfuse instance (for observability — optional but recommended)

### Installation

```bash
# Clone and navigate to the agent directory
cd AutonomousLearningAgent

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google AI / Gemini API key |
| `GEMINI_MODEL` | No | Model to use (default: `gemini-2.5-flash`) |
| `GOOGLE_SEARCH_CX` | No | Google Custom Search engine ID |
| `SERPAPI_API_KEY` | No | SerpAPI key for fast search |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | Use Vertex AI instead of AI Studio (default: `false`) |
| `GOOGLE_CLOUD_PROJECT` | No | GCP project ID (only if using Vertex AI) |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret key for tracing |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse public key for tracing |
| `LANGFUSE_HOST` | No | Langfuse host URL |

### Run

```bash
uvicorn AutonomousLearningAgent.prepare:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Docker Deployment

### Build and run locally

```bash
cd AutonomousLearningAgent
docker-compose up --build
```

The agent will be available at [http://localhost:8000](http://localhost:8000).

### Build only

```bash
docker build -t autonomous-learning-agent .
docker run -p 8000:8000 --env-file .env autonomous-learning-agent
```

---

## Configuration

### Research Depth Modes

| Mode | Max Iterations | Use Case |
|------|---------------|----------|
| `quick` | 2 | Fast overviews, time-sensitive queries |
| `standard` | 5 | General research, balanced depth vs. speed |
| `deep` | 10 | Academic-level research, complex multi-faceted topics |

### Search Engine Priority

The agent tries search engines in order and uses the first available:

1. **Google Custom Search** — Best quality, requires `GOOGLE_SEARCH_CX`
2. **SerpAPI** — Fast and reliable, requires `SERPAPI_API_KEY`
3. **DuckDuckGo** — Always available, rate-limited to 1 request per 3 seconds

For best results, configure at least one of Google Custom Search or SerpAPI.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | Google ADK |
| LLM | Gemini 2.5 Flash |
| Backend | FastAPI + Uvicorn |
| Frontend | Vanilla JS, Chart.js, marked.js, html2pdf.js |
| Observability | Langfuse + OpenTelemetry |
| File Parsing | PyPDF2, python-docx |
| Search | Google Custom Search, SerpAPI, DuckDuckGo |
| Deployment | Docker, Google Cloud Run |
| Language | Python 3.11 |
