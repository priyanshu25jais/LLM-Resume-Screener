"""Job endpoints: create/analyse a JD, upload resumes, list ranked candidates, ask, export."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import recruiter_user
from ..config import settings
from ..database import get_db
from ..models import AuditEvent, Candidate, Job, User, utcnow
from ..schemas import (AskRequest, AskResponse, CandidateSummary, JDRequirements, JobCreate, JobOut,
                       JobUpdate)
from ..services import qa
from ..services.accounts import record
from ..services.jd_analyzer import analyze_jd
from ..services.parser import SUPPORTED_EXTENSIONS
from ..services.pipeline import process_batch, rescore_job
from ..services.scoring import normalize_weights
from .common import candidate_summary, get_job_or_404, job_out, ranked

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobOut, status_code=201)
async def create_job(body: JobCreate, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    req, by = await analyze_jd(body.title, body.description)
    job = Job(title=body.title.strip(), description=body.description.strip(), requirements=req.model_dump(),
              weights=normalize_weights(body.weights.model_dump() if body.weights else None),
              blind_mode=body.blind_mode, analysed_by=by, owner_id=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    jobs = db.query(Job).filter(Job.owner_id == user.id).order_by(Job.created_at.desc()).all()
    return [job_out(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    return job_out(get_job_or_404(db, job_id, user))


@router.patch("/{job_id}", response_model=JobOut)
def update_job(job_id: int, body: JobUpdate, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    if body.title:
        job.title = body.title.strip()
    if body.blind_mode is not None:
        job.blind_mode = body.blind_mode
    if body.weights:
        job.weights = normalize_weights(body.weights.model_dump())
        db.commit()
        rescore_job(db, job)
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.put("/{job_id}/requirements", response_model=JobOut)
def update_requirements(job_id: int, body: JDRequirements, db: Session = Depends(get_db),
                        user: User = Depends(recruiter_user)):
    """Let the recruiter correct the extracted requirements. Call /rescreen afterwards."""
    job = get_job_or_404(db, job_id, user)
    job.requirements = body.model_dump()
    job.analysed_by = f"{job.analysed_by} + edited" if "edited" not in job.analysed_by else job.analysed_by
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.post("/{job_id}/rescreen", response_model=JobOut)
def rescreen(job_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
             user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    ids = []
    for c in job.candidates:
        c.status = "queued"
        ids.append(c.id)
    db.commit()
    background.add_task(process_batch, ids)
    return job_out(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    folder = settings.UPLOAD_DIR / f"job_{job.id}"
    db.delete(job)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)


def _recent_total(db, action: str, minutes: int, user_id: int) -> int:
    since = utcnow() - timedelta(minutes=minutes)
    rows = db.query(AuditEvent).filter(AuditEvent.action == action, AuditEvent.target_user_id == user_id,
                                       AuditEvent.created_at >= since).all()
    return sum((r.detail or {}).get("count", 0) for r in rows)


def note_upload(db, user: User, added: list, skipped: list) -> None:
    """Log upload counts (never file names or content) and flag unusual patterns for the admin to review."""
    before = _recent_total(db, "upload", 60, user.id)
    if added:
        crossed = before < settings.FLAG_UPLOADS_PER_HOUR <= before + len(added)
        record(db, "account", "upload", actor=user, target_id=user.id, detail={"count": len(added)})
        if crossed:
            record(db, "security", "upload_burst", actor=user, target_id=user.id, flagged=True,
                   detail={"count": before + len(added), "minutes": 60})
    dups = sum(1 for s in skipped if s["reason"].startswith("duplicate"))
    if dups:
        prev = _recent_total(db, "duplicate_upload", 1440, user.id)
        record(db, "security", "duplicate_upload", actor=user, target_id=user.id,
               detail={"count": dups, "last_24h": prev + dups},
               flagged=prev < settings.FLAG_DUPLICATES_PER_DAY <= prev + dups)
    db.commit()


def store_resume_files(db, job: Job, items: list[tuple[str, bytes]]) -> tuple[list, list, list[int]]:
    """Validate, de-duplicate and save uploaded files; create queued candidates."""
    folder = settings.UPLOAD_DIR / f"job_{job.id}"
    folder.mkdir(parents=True, exist_ok=True)
    known = {c.file_hash for c in job.candidates}
    next_seq = max((c.seq for c in job.candidates), default=0) + 1
    added, skipped, new_ids = [], [], []
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    for raw_name, data in items:
        name = Path(raw_name or "resume").name
        ext = Path(name).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            skipped.append({"filename": name, "reason": "unsupported file type (use PDF, DOCX or TXT)"})
            continue
        if len(data) > limit:
            skipped.append({"filename": name, "reason": f"larger than {settings.MAX_UPLOAD_MB} MB"})
            continue
        if not data:
            skipped.append({"filename": name, "reason": "empty file"})
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in known:
            skipped.append({"filename": name, "reason": "duplicate of a resume already uploaded"})
            continue
        known.add(digest)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]
        path = folder / f"{uuid.uuid4().hex[:8]}_{safe}"
        path.write_bytes(data)
        c = Candidate(job_id=job.id, seq=next_seq, filename=name, file_path=str(path), file_hash=digest)
        next_seq += 1
        db.add(c)
        db.flush()
        new_ids.append(c.id)
        added.append({"id": c.id, "filename": name})
    db.commit()
    return added, skipped, new_ids


@router.post("/{job_id}/resumes", status_code=202)
async def upload_resumes(job_id: int, background: BackgroundTasks, files: list[UploadFile] = File(...),
                         db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    if not files:
        raise HTTPException(400, "No files uploaded")
    items = [(f.filename or "resume", await f.read()) for f in files]
    added, skipped, new_ids = store_resume_files(db, job, items)
    note_upload(db, user, added, skipped)
    if new_ids:
        background.add_task(process_batch, new_ids)
    return {"added": added, "skipped": skipped}


@router.get("/{job_id}/candidates", response_model=list[CandidateSummary])
def list_candidates(job_id: int, recommendation: str | None = None, decision: str | None = None,
                    q: str | None = None, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    out = []
    for rank, c in ranked(job):
        if recommendation and c.recommendation != recommendation:
            continue
        if decision and c.decision != decision:
            continue
        if q:
            ql = q.lower()
            hay = " ".join([c.filename, " ".join(c.skills or []), "" if job.blind_mode else c.name]).lower()
            if ql not in hay:
                continue
        out.append(candidate_summary(c, job, rank))
    return out


@router.post("/{job_id}/ask", response_model=AskResponse)
async def ask_pool(job_id: int, body: AskRequest, db: Session = Depends(get_db),
                   user: User = Depends(recruiter_user)):
    return await qa.ask(db, get_job_or_404(db, job_id, user), body.question)


@router.get("/{job_id}/export.csv")
def export_csv(job_id: int, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    job = get_job_or_404(db, job_id, user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "candidate", "file", "final_score", "recommendation", "decision", "llm_score",
                "skill_coverage", "semantic_match", "experience_fit", "years_experience", "matched_must_have",
                "missing_must_have", "summary", "flags"])
    for rank, c in ranked(job):
        if c.status != "done":
            continue
        sm = c.skill_match or {}
        w.writerow([rank, qa.display_name(c, job), c.filename, c.final_score, c.recommendation, c.decision,
                    round(c.llm_score * 100), round(c.skill_score * 100), round(c.semantic_score * 100),
                    round(c.experience_score * 100), c.years_experience, "; ".join(sm.get("matched_must", [])),
                    "; ".join(sm.get("missing_must", [])), (c.evaluation or {}).get("summary", ""),
                    " | ".join(c.flags or [])])
    buf.seek(0)
    fname = re.sub(r"[^A-Za-z0-9]+", "_", job.title).strip("_") or "job"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}_ranking.csv"'})
