"""Health/config info and a one-click demo loader."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import recruiter_user
from ..config import BASE_DIR, settings
from ..database import get_db
from ..models import Job, User
from ..schemas import JobOut
from ..services.embeddings import get_embedder
from ..services.jd_analyzer import analyze_jd
from ..services.llm import get_llm
from ..services.pipeline import process_batch
from ..services.scoring import DEFAULT_WEIGHTS
from .common import job_out
from .jobs import note_upload, store_resume_files

router = APIRouter(prefix="/api", tags=["system"])
SAMPLE_DIR = BASE_DIR.parent / "sample_data"
DEMO_JOBS = {
    "backend": ("Python Backend Developer", "python_backend_developer.txt"),
    "frontend": ("React Frontend Developer", "react_frontend_developer.txt"),
    "data": ("Data Scientist", "data_scientist.txt"),
}


@router.get("/health")
def health():
    llm, emb = get_llm(), get_embedder()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "llm_provider": llm.name,
        "llm_model": llm.model,
        "llm_available": llm.available,
        "llm_chain": llm.chain if llm.available else [],
        "llm_status": llm.status() if hasattr(llm, "status") else [],
        "embedding_backend": emb.label,
        "default_weights": DEFAULT_WEIGHTS,
    }


@router.get("/demo")
def demo_options():
    return [{"key": k, "title": t, "available": (SAMPLE_DIR / "job_descriptions" / f).exists()}
            for k, (t, f) in DEMO_JOBS.items()]


@router.post("/demo/{key}", response_model=JobOut, status_code=201)
async def load_demo(key: str, background: BackgroundTasks, db: Session = Depends(get_db),
                    user: User = Depends(recruiter_user)):
    """Create a job from a sample JD and screen all sample resumes against it."""
    if key not in DEMO_JOBS:
        raise HTTPException(404, f"Unknown demo '{key}'")
    title, fname = DEMO_JOBS[key]
    jd_path = SAMPLE_DIR / "job_descriptions" / fname
    res_dir = SAMPLE_DIR / "resumes"
    if not jd_path.exists() or not res_dir.exists():
        raise HTTPException(404, "sample_data folder not found next to backend/")
    description = jd_path.read_text(encoding="utf-8")
    req, by = await analyze_jd(title, description)
    job = Job(title=f"{title} (demo)", description=description, requirements=req.model_dump(),
              weights=dict(DEFAULT_WEIGHTS), blind_mode=True, analysed_by=by, owner_id=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    items = [(p.name, p.read_bytes()) for p in sorted(res_dir.iterdir()) if p.is_file()]
    added, skipped, ids = store_resume_files(db, job, items)
    note_upload(db, user, added, skipped)
    background.add_task(process_batch, ids)
    db.refresh(job)
    return job_out(job)
