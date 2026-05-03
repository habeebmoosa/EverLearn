# EverLearn: Enterprise Agentic Platform

EverLearn is a modern, enterprise-grade autonomous AI agent platform. Originally inspired by automated research loops, it has evolved into a generic, highly-scalable Agentic Architecture powered by Google ADK, Gemini, FastAPI, and a modern React frontend.

## The Problem It Solves

As AI agents become more prevalent, developers face several challenges:
1. **Agent Orchestration:** How do you manage long-running, iterative tasks without losing context?
2. **Quality Assurance:** How do you prevent agents from hallucinating or regressing in quality over time?
3. **Extensibility:** How do you build a platform where new specialized agents can be plugged in seamlessly?
4. **User Experience:** How do you expose complex agentic workflows in a clean, intuitive, ChatGPT-like interface?

## How EverLearn Solves It

EverLearn provides a robust ecosystem for building, running, and observing autonomous agents. 

### 1. The Quality Ratchet Mechanism
The core of EverLearn's processing is the **Quality Ratchet**. Agents don't just generate text; they iteratively refine their output. Each iteration is evaluated by a Quality Evaluator against a 10-dimension rubric. If the new output is better, the ratchet moves forward. If not, it discards the output and tries again. This guarantees monotonic quality improvement.

### 2. Plug-and-Play Agent Architecture
EverLearn uses a dynamic pipeline discovery system. You can create a new agent (e.g., `Code Reviewer`, `Content Writer`, `Deep Researcher`) by dropping a pipeline definition into the `pipelines/` directory. The system automatically registers the agent, exposes its configuration schema via the API, and dynamically renders the appropriate UI forms in the React frontend.

### 3. Modern React + Vite Frontend
The entire frontend has been rebuilt from the ground up as a decoupled React Single Page Application (SPA), utilizing Tailwind CSS for beautiful, modern styling. 
- **Agent-Centric Workflow:** A Claude/ChatGPT-inspired sidebar lets you easily switch between different specialized agents.
- **Dynamic Task Forms:** The UI automatically builds input forms based on the selected agent's JSON Schema.
- **Iteration Analysis:** Real-time dashboards and interactive charts (using Recharts) visualize the agent's iterative progress and Quality Ratchet scores.

### 4. A2A (Agent-to-Agent) Protocol
EverLearn implements an A2A discovery and messaging protocol, allowing external agents and orchestrators to discover its capabilities and communicate with it programmatically.

### 5. Enterprise Observability
Deep integration with **Langfuse** provides full telemetry. Every agent step, tool call, latency metric, and token cost is traced and persisted, allowing for deep debugging and performance optimization.

---

## Tech Stack

- **Frontend:** React, Vite, Tailwind CSS, Recharts, React-Markdown
- **Backend:** Python, FastAPI, Google ADK (Agent Development Kit)
- **AI/LLM:** Google Gemini 2.5 Flash / Pro
- **Database/State:** PostgreSQL (Persistence), In-Memory Cache
- **Observability:** Langfuse, OpenTelemetry
- **Infrastructure:** Docker, Docker Compose, Nginx

---

## Getting Started (Local Development)

The architecture is cleanly separated into a FastAPI backend and a React frontend.

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional, for containerized running)
- Google Gemini API Key

### Backend Setup
1. Navigate to the root directory.
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and add your API keys.
6. Run the server: 
   ```bash
   uvicorn prepare:app --reload --port 8000
   ```
   The backend API will be available at `http://localhost:8000`.

### Frontend Setup
1. Navigate to the `ui/` directory: `cd ui`
2. Install dependencies: `npm install`
3. Start the development server:
   ```bash
   npm run dev
   ```
   The Vite dev server will start at `http://localhost:5173`. It automatically proxies `/api` requests to the FastAPI backend.

---

## Docker Deployment (Production)

EverLearn includes a robust, production-ready `docker-compose.yml` that orchestrates:
- The FastAPI Backend
- A PostgreSQL Database
- An Nginx reverse-proxy serving the built React static files and routing API requests.

```bash
docker-compose up --build -d
```
The application will be accessible at `http://localhost:3000`.

---

## Creating a New Agent

EverLearn makes it incredibly simple to add new capabilities. 

1. Create a new file in the `pipelines/` directory (e.g., `my_agent.py`).
2. Define a class that inherits from the base ADK pipeline.
3. Expose a `get_schema()` method describing the inputs your agent needs.
4. Restart the backend.

The platform will automatically discover your agent, register it in the database, and the React frontend will immediately display it in the sidebar and dynamically generate the required input forms!
