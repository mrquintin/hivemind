import logging
import os
import time
from logging.handlers import RotatingFileHandler

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.runtime_paths import logs_dir, uploads_root

_LOG_DIR = logs_dir()
_LOG_FILE = _LOG_DIR / "cloud.log"


def _configure_logging() -> logging.Logger:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not any(
        getattr(handler, "baseFilename", None) == str(_LOG_FILE)
        for handler in root_logger.handlers
    ):
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=2_000_000,
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(
        isinstance(handler, logging.StreamHandler)
        and getattr(handler, "baseFilename", None) is None
        for handler in root_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    logging.captureWarnings(True)

    app_logger = logging.getLogger("hivemind.cloud")
    app_logger.setLevel(logging.INFO)
    return app_logger


logger = _configure_logging()

# Jinja2 template directory
_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
import app.models.user  # noqa: F401 — register User model for create_all
from app.db.base import Base
from app.db.session import engine
from app.deps import get_current_user
from app.routers import (
    agents,
    auth,
    clients,
    knowledge_bases,
    scraped_sources,
    simulations,
    sync,
)
from app.routers import (
    analysis as analysis_router,
)
from app.routers import (
    client_data as client_data_router,
)
from app.routers import (
    settings as settings_router,
)
from app.ws import router as ws_router

app = FastAPI(
    title="Hivemind Cloud Services",
    description="Multi-agent AI strategic analysis platform",
    version="0.1.0",
)

# Configure CORS - parse comma-separated origins or allow any origin by echoing
# it back explicitly. This is more reliable for Tauri's custom origins than
# responding with a literal "*".
if settings.CORS_ORIGINS == "*":
    cors_origins: list[str] = []
    cors_origin_regex = r".*"
else:
    cors_origins = [
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]
    cors_origin_regex = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=bool(cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

_CONNECTION_LOG_PATHS = {
    "/health",
    "/health/detailed",
    "/admin/ping",
    "/admin/ping-status",
}

# Track ping events from admin
_last_ping_time: float = 0
_server_start_time: float = time.time()


@app.middleware("http")
async def log_connection_traffic(request: Request, call_next):
    should_log = request.url.path in _CONNECTION_LOG_PATHS
    origin = request.headers.get("origin", "-")
    client_host = request.client.host if request.client else "-"

    if should_log:
        logger.info(
            "Incoming %s %s origin=%s client=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
        )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error during %s %s origin=%s client=%s",
            request.method,
            request.url.path,
            origin,
            client_host,
        )
        raise

    if should_log:
        logger.info(
            "Completed %s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
        )

    return response


@app.on_event("startup")
def on_startup():
    """Startup event - seal API key file and create tables if needed."""
    logger.info("Server logging to %s", _LOG_FILE)
    logger.info("Configured CORS origins: %s", settings.CORS_ORIGINS)
    logger.info("Configured vector database URL: %s", settings.VECTOR_DB_URL)

    # If .api_key contains a plaintext key, encrypt it in place
    from app.secrets import seal_api_key_file

    if seal_api_key_file():
        logger.info(".api_key: plaintext key encrypted and sealed.")
    if settings.AUTO_CREATE_TABLES:
        try:
            Base.metadata.create_all(bind=engine)
        except Exception as e:
            import sys

            logger.error("Database connection failed on startup: %s", e)
            print(f"ERROR: Database connection failed: {e}", file=sys.stderr)
            raise RuntimeError("Cannot create tables; database unreachable. Check DATABASE_URL.") from e

        # Seed default users if the users table is empty
        from app.seed import seed_default_users

        seed_default_users(engine)


def _check_readiness() -> tuple[bool, str]:
    """Verify database and Qdrant are reachable. Returns (ok, message)."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        return False, f"database: {str(e)[:100]}"
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"{settings.VECTOR_DB_URL.rstrip('/')}/healthz", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                return False, f"qdrant: HTTP {resp.status}"
    except Exception as e:
        return False, f"qdrant: {str(e)[:80]}"
    return True, "ok"


@app.get("/health")
def health_check():
    """Health check for AWS load balancers and monitoring. Returns 503 when DB or Qdrant are unreachable."""
    from fastapi.responses import JSONResponse

    ok, _ = _check_readiness()
    payload = {
        "status": "healthy" if ok else "degraded",
        "version": "0.1.0",
        "service": "hivemind-cloud",
    }
    if not ok:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/health/detailed")
def detailed_health_check():
    """Detailed health check that tests the app dependencies used on AWS."""
    from sqlalchemy import text

    from app.db.session import SessionLocal

    results = {
        "api": {"status": "online", "message": "FastAPI running"},
        "database": {"status": "unknown", "message": "Not checked"},
        "qdrant": {"status": "unknown", "message": "Not checked"},
    }

    # Check Database — use engine.connect() directly for a clean, isolated check
    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        results["database"] = {"status": "online", "message": "PostgreSQL connected"}
    except Exception as e:
        results["database"] = {"status": "offline", "message": str(e)[:200]}
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass

    # Check Qdrant
    try:
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"{settings.VECTOR_DB_URL.rstrip('/')}/healthz", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                results["qdrant"] = {"status": "online", "message": "Qdrant responding"}
            else:
                results["qdrant"] = {"status": "offline", "message": f"HTTP {resp.status}"}
    except urllib.error.URLError as e:
        results["qdrant"] = {"status": "offline", "message": f"Connection failed: {str(e.reason)[:50]}"}
    except Exception as e:
        results["qdrant"] = {"status": "offline", "message": str(e)[:100]}

    # Overall status
    all_online = all(r["status"] == "online" for r in results.values())

    return {
        "overall": "healthy" if all_online else "degraded",
        "services": results,
        "uptime_seconds": int(time.time() - _server_start_time),
    }


@app.post("/admin/ping")
def admin_ping(request: Request):
    """Receive a ping from admin to verify connection."""
    global _last_ping_time
    _last_ping_time = time.time()
    origin = request.headers.get("origin", "-")
    client_host = request.client.host if request.client else "-"
    logger.info("Admin ping received origin=%s client=%s", origin, client_host)
    return {"status": "pong", "timestamp": _last_ping_time}


@app.get("/admin/ping-status")
def ping_status():
    """Get the last ping time (for dashboard polling)."""
    return {
        "last_ping": _last_ping_time,
        "seconds_ago": time.time() - _last_ping_time if _last_ping_time > 0 else None,
    }


@app.get("/dashboard")
def server_dashboard(request: Request):
    """Server dashboard UI showing status and connection info."""
    uptime_seconds = int(time.time() - _server_start_time)
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "uptime_str": uptime_str},
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/knowledge-browser")
def knowledge_browser(request: Request, _user: dict = Depends(get_current_user)):
    """Browsable UI showing all bases stored on this server: knowledge, simulations, practicality."""
    from app.db.session import SessionLocal
    from app.models.knowledge_base import KnowledgeBase
    from app.models.knowledge_document import KnowledgeDocument
    from app.models.simulation_formula import SimulationFormula
    from app.models.text_chunk import TextChunk

    db = SessionLocal()
    try:
        # --- Knowledge Bases with documents ---
        kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()
        kb_data = []
        for kb in kbs:
            docs = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.knowledge_base_id == kb.id
            ).order_by(KnowledgeDocument.upload_timestamp.desc()).all()
            framework_docs = []
            practicality_docs = []
            simulation_docs = []
            for doc in docs:
                chunk_count = db.query(TextChunk).filter(
                    TextChunk.document_id == doc.id
                ).count()
                doc_entry = {
                    "id": doc.id,
                    "filename": doc.filename,
                    "content_type": doc.content_type,
                    "document_type": doc.document_type or "framework",
                    "s3_path": doc.s3_path or "",
                    "chunk_count": chunk_count,
                    "uploaded": doc.upload_timestamp.strftime("%Y-%m-%d %H:%M") if doc.upload_timestamp else "unknown",
                    "text_preview": (doc.extracted_text[:300] + "...") if doc.extracted_text and len(doc.extracted_text) > 300 else (doc.extracted_text or ""),
                }
                if doc.document_type == "practicality":
                    practicality_docs.append(doc_entry)
                elif doc.document_type in ("simulation_program", "simulation_description"):
                    simulation_docs.append(doc_entry)
                else:
                    framework_docs.append(doc_entry)

            kb_data.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description or "",
                "document_count": kb.document_count or 0,
                "chunk_count": kb.chunk_count or 0,
                "total_tokens": kb.total_tokens or 0,
                "embedding_model": kb.embedding_model or "all-MiniLM-L6-v2",
                "created": kb.created_at.strftime("%Y-%m-%d %H:%M") if kb.created_at else "unknown",
                "framework_docs": framework_docs,
                "practicality_docs": practicality_docs,
                "simulation_docs": simulation_docs,
            })

        # --- Simulation Formulas (standalone, not KB-attached) ---
        sim_formulas = db.query(SimulationFormula).order_by(SimulationFormula.created_at.desc()).all()
        sim_data = []
        for sf in sim_formulas:
            sim_data.append({
                "id": sf.id,
                "name": sf.name,
                "description": sf.description or "",
                "simulation_type": sf.simulation_type or "formula",
                "inputs": sf.inputs or [],
                "outputs": sf.outputs or [],
                "tags": sf.tags or [],
                "has_code": bool(sf.code),
                "created": sf.created_at.strftime("%Y-%m-%d %H:%M") if sf.created_at else "unknown",
            })
    finally:
        db.close()

    # Count documents by type across all KBs
    total_framework_docs = sum(len(kb["framework_docs"]) for kb in kb_data)
    total_sim_docs = sum(len(kb["simulation_docs"]) for kb in kb_data)
    total_prac_docs = sum(len(kb["practicality_docs"]) for kb in kb_data)

    storage_path = str(uploads_root())
    return templates.TemplateResponse(
        "knowledge_browser.html",
        {
            "request": request,
            "kb_data": kb_data,
            "sim_data": sim_data,
            "kb_count": len(kb_data),
            "doc_count": sum(kb["document_count"] for kb in kb_data),
            "chunk_count": sum(kb["chunk_count"] for kb in kb_data),
            "token_count": f"{sum(kb['total_tokens'] for kb in kb_data):,}",
            "sim_count": len(sim_data),
            "framework_doc_count": total_framework_docs,
            "sim_doc_count": total_sim_docs,
            "prac_doc_count": total_prac_docs,
            "storage_path": storage_path,
        },
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# REST API routers
app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(knowledge_bases.router)
app.include_router(clients.router)
app.include_router(client_data_router.router)
app.include_router(sync.router)
app.include_router(analysis_router.router)
app.include_router(scraped_sources.router)
app.include_router(simulations.router)
app.include_router(settings_router.router)

# WebSocket router
app.include_router(ws_router)
