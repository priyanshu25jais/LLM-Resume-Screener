# FastAPI app. Run from backend/:  uvicorn app.main:app --reload --port 8000
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .database import init_db
from .database import SessionLocal
from .models import User
from .routers import admin, auth, candidates, jobs, system
from .services.accounts import create_admin, purge_due
from .services.embeddings import get_embedder
from .services.llm import get_llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("screener")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        purge_due(db)
        if not db.query(User).filter(User.role == "admin", User.status == "active").first():
            if settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
                try:
                    create_admin(db, settings.ADMIN_NAME, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD)
                except ValueError as exc:
                    log.error("Could not create the admin from ADMIN_EMAIL: %s", exc)
            else:
                log.warning("No admin account yet. Create one from the backend folder: python scripts/create_admin.py")
    get_llm()
    get_embedder()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Screens resumes against a job description with an LLM and explains every score.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(jobs.router)
app.include_router(candidates.router)

# Serve the built React app (frontend/dist) from the same server, if it exists.
DIST = BASE_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = DIST / full_path
        if full_path and target.is_file() and Path(target).resolve().is_relative_to(DIST.resolve()):
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
