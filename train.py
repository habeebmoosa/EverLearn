"""
EverLearn Agent — train.py

Mirrors Karpathy's autoresearch train.py: this is the "experiment" file
that defines the agent pipeline executed each iteration. prepare.py runs
this pipeline repeatedly, evaluates quality, and keeps only improvements.

Architecture:
- learning_iteration_pipeline (SequentialAgent): runs one iteration
  - Learning Planner → Source Collector → Deep Analyzer → Report Synthesizer
- root_agent (LlmAgent): conversational A2A interface

The iterative ratchet loop is orchestrated in prepare.py.
"""

from google.adk.agents import LlmAgent, SequentialAgent

from sub_agents import (
    research_planner_agent,
    source_collector_agent,
    deep_researcher_agent,
    report_synthesizer_agent,
)

# Single-iteration pipeline: Plan → Collect → Analyze → Synthesize
# Quality evaluation runs SEPARATELY (needs both new and previous report)
research_iteration_pipeline = SequentialAgent(
    name="learning_iteration_pipeline",
    description="""
    Runs one iteration of the autonomous learning loop:
    1. Learning Planner - identifies gaps and generates search strategy
    2. Source Collector - gathers information from web, URLs, and files
    3. Deep Analyzer - analyzes sources and extracts findings
    4. Report Synthesizer - produces comprehensive markdown report
    """,
    sub_agents=[
        research_planner_agent,
        source_collector_agent,
        deep_researcher_agent,
        report_synthesizer_agent,
    ],
)

ROOT_AGENT_INSTRUCTION = """You are EverLearn — an EverLearn Agent inspired by Karpathy's autoresearch concept.

## Your Capabilities
1. **Deep Learning**: Conduct multi-iteration autonomous learning on any topic
2. **Source Analysis**: Analyze web pages, documents, and raw data
3. **Quality Ratchet**: Each iteration improves upon the previous — only improvements are kept

## Conversation Flow

### Phase 1: Learning Setup
Collect the following from the user:
1. **Topic** (required): What should be learned about?
2. **Data Sources** (optional): Any URLs, files, or text to include
3. **Focus Areas** (optional): Specific subtopics to prioritize
4. **Depth** (optional): quick (2 iterations), standard (5), or deep (10)

### Phase 2: Confirmation
Summarize the learning configuration and ask for confirmation.

### Phase 3: Learning Execution
Once confirmed, delegate to `learning_iteration_pipeline` to begin autonomous learning.

## Guidelines
- Ask one question at a time
- Be helpful in suggesting focus areas if the topic is broad
- Explain the iterative process if asked
- For quick learning, recommend 2-3 iterations
- For comprehensive learning, recommend 5-10 iterations
"""

root_agent = LlmAgent(
    name="auto_learn",
    model="gemini-2.5-flash",
    instruction=ROOT_AGENT_INSTRUCTION,
    description="EverLearn Agent - Iterative deep learning with quality ratchet mechanism",
    sub_agents=[research_iteration_pipeline],
)

__all__ = ["root_agent", "research_iteration_pipeline"]
