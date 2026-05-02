import os
import ssl
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Text,
    JSON,
    select,
)
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker


Base = declarative_base()

DB_SSLMODE = (os.getenv("DATABASE_SSLMODE") or "").strip().lower()


def _build_database_url() -> Optional[URL]:
    host = (os.getenv("DATABASE_HOST") or "").strip()
    port = os.getenv("DATABASE_PORT", "5432")
    name = (os.getenv("DATABASE_NAME") or "").strip()
    user = (os.getenv("DATABASE_USER") or "").strip()
    password = (os.getenv("DATABASE_PASSWORD") or "").strip()

    if not all([host, name, user, password]):
        return None

    # IMPORTANT: Use SQLAlchemy URL builder so special characters
    # (like '@' in passwords) are escaped safely.
    return URL.create(
        drivername="postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=int(port) if str(port).strip().isdigit() else 5432,
        database=name,
    )


DATABASE_URL: Optional[URL] = _build_database_url()

_connect_args: Optional[dict] = None
if DB_SSLMODE in {"require", "verify-ca", "verify-full"}:
    # asyncpg expects an SSLContext
    _connect_args = {"ssl": ssl.create_default_context()}

if DATABASE_URL:
    if _connect_args:
        engine = create_async_engine(DATABASE_URL, echo=False, connect_args=_connect_args)
    else:
        engine = create_async_engine(DATABASE_URL, echo=False)
else:
    engine = None
AsyncSessionLocal = (
    sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    if engine is not None
    else None
)


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    session_id = Column(String, primary_key=True, index=True)
    pipeline_id = Column(String, nullable=False, default="research")  # which pipeline ran
    topic = Column(Text, nullable=False)          # label / topic (shared naming)
    status = Column(String, nullable=False)
    current_iteration = Column(Integer, nullable=False, default=0)
    max_iterations = Column(Integer, nullable=False, default=0)
    best_iteration = Column(Integer, nullable=False, default=0)
    best_score = Column(Float, nullable=False, default=0.0)
    iterations = Column(JSON, nullable=False, default=list)
    best_report = Column(Text, nullable=True)
    task_inputs = Column(JSON, nullable=True)     # pipeline-specific input fields
    data_sources = Column(JSON, nullable=True)
    config = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


def is_db_configured() -> bool:
    return engine is not None and AsyncSessionLocal is not None


async def init_db() -> None:
    if not engine:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db() -> bool:
    """Return True if DB is reachable and usable."""
    if not engine:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        return True
    except Exception:
        return False


async def _get_session() -> AsyncSession:
    if not AsyncSessionLocal:
        raise RuntimeError("Database is not configured. Please set DATABASE_* env vars.")
    return AsyncSessionLocal()


def _session_dict_to_model(data: Dict[str, Any]) -> ResearchSession:
    # Support both "label" (generic) and "topic" (research compat)
    label = data.get("label") or data.get("topic", "")
    return ResearchSession(
        session_id=data["session_id"],
        pipeline_id=data.get("pipeline_id", "research"),
        topic=label,
        status=data["status"],
        current_iteration=data.get("current_iteration", 0),
        max_iterations=data.get("max_iterations", 0),
        best_iteration=data.get("best_iteration", 0),
        best_score=float(data.get("best_score", 0.0)),
        iterations=data.get("iterations", []),
        best_report=data.get("best_report"),
        task_inputs=data.get("task_inputs") or data.get("inputs"),
        data_sources=data.get("data_sources"),
        config=data.get("config"),
        error=data.get("error"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def _model_to_session_dict(model: ResearchSession) -> Dict[str, Any]:
    return {
        "session_id": model.session_id,
        "pipeline_id": model.pipeline_id or "research",
        "topic": model.topic,          # backward compat
        "label": model.topic,          # generic alias
        "status": model.status,
        "current_iteration": model.current_iteration,
        "max_iterations": model.max_iterations,
        "best_iteration": model.best_iteration,
        "best_score": float(model.best_score or 0.0),
        "iterations": model.iterations or [],
        "best_report": model.best_report,
        "task_inputs": model.task_inputs or {},
        "data_sources": model.data_sources or [],
        "config": model.config or {},
        "error": model.error,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


async def save_session(session_data: Dict[str, Any]) -> None:
    if not is_db_configured():
        return

    db = await _get_session()
    async with db:
        existing = await db.get(ResearchSession, session_data["session_id"])
        label = session_data.get("label") or session_data.get("topic", "")
        if existing:
            existing.pipeline_id = session_data.get("pipeline_id", "research")
            existing.topic = label
            existing.status = session_data["status"]
            existing.current_iteration = session_data.get("current_iteration", 0)
            existing.max_iterations = session_data.get("max_iterations", 0)
            existing.best_iteration = session_data.get("best_iteration", 0)
            existing.best_score = float(session_data.get("best_score", 0.0))
            existing.iterations = session_data.get("iterations", [])
            existing.best_report = session_data.get("best_report")
            existing.task_inputs = session_data.get("task_inputs") or session_data.get("inputs")
            existing.data_sources = session_data.get("data_sources")
            existing.config = session_data.get("config")
            existing.error = session_data.get("error")
            existing.created_at = session_data.get("created_at", existing.created_at)
            existing.updated_at = session_data.get("updated_at", existing.updated_at)
        else:
            model = _session_dict_to_model(session_data)
            db.add(model)
        await db.commit()


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not is_db_configured():
        return None

    db = await _get_session()
    async with db:
        model = await db.get(ResearchSession, session_id)
        if not model:
            return None
        return _model_to_session_dict(model)


async def list_sessions() -> List[Dict[str, Any]]:
    if not is_db_configured():
        return []

    db = await _get_session()
    async with db:
        result = await db.execute(
            select(ResearchSession).order_by(ResearchSession.created_at.desc())
        )
        models = result.scalars().all()
        return [_model_to_session_dict(m) for m in models]


async def delete_session(session_id: str) -> None:
    if not is_db_configured():
        return

    db = await _get_session()
    async with db:
        model = await db.get(ResearchSession, session_id)
        if model:
            await db.delete(model)
            await db.commit()

