# ── EverLearn Agent — Docker Image ──────────────────────
FROM python:3.11-slim

LABEL maintainer="Drayvn Platform"
LABEL description="EverLearn Agent — Autonomous iterative learning with quality ratchet using Google ADK + Gemini"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code
COPY . /app/AutonomousLearningAgent/

# Port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# Start FastAPI
CMD ["uvicorn", "AutonomousLearningAgent.prepare:app", "--host", "0.0.0.0", "--port", "8000"]
