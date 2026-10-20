"""Candidate endpoints: profile, recruiter decision/notes, re-processing, original file."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import recruiter_user
from ..database import get_db
from ..models import User
from ..schemas import CandidateDetail, CandidateUpdate
from ..services.pipeline import process_batch
from .common import candidate_detail, get_candidate_or_404, ranked

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _rank_of(c) -> int | None:
    return next((r for r, x in ranked(c.job) if x.id == c.id), None)


@router.get("/{cid}", response_model=CandidateDetail)
def get_candidate(cid: int, reveal: bool = False, db: Session = Depends(get_db),
                  user: User = Depends(recruiter_user)):
    c = get_candidate_or_404(db, cid, user)
    return candidate_detail(c, c.job, _rank_of(c), reveal)


@router.patch("/{cid}", response_model=CandidateDetail)
def update_candidate(cid: int, body: CandidateUpdate, db: Session = Depends(get_db),
                     user: User = Depends(recruiter_user)):
    c = get_candidate_or_404(db, cid, user)
    if body.decision is not None:
        c.decision = body.decision
    if body.notes is not None:
        c.notes = body.notes[:5000]
    db.commit()
    return candidate_detail(c, c.job, _rank_of(c), False)


@router.post("/{cid}/reprocess", response_model=CandidateDetail)
def reprocess(cid: int, background: BackgroundTasks, db: Session = Depends(get_db),
              user: User = Depends(recruiter_user)):
    c = get_candidate_or_404(db, cid, user)
    c.status = "queued"
    db.commit()
    background.add_task(process_batch, [c.id])
    return candidate_detail(c, c.job, None, False)


@router.delete("/{cid}", status_code=204)
def delete_candidate(cid: int, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    c = get_candidate_or_404(db, cid, user)
    path = Path(c.file_path)
    db.delete(c)
    db.commit()
    path.unlink(missing_ok=True)


@router.get("/{cid}/file")
def download_file(cid: int, db: Session = Depends(get_db), user: User = Depends(recruiter_user)):
    c = get_candidate_or_404(db, cid, user)
    if c.job.blind_mode:
        raise HTTPException(403, "Original files are hidden while blind screening is on for this job")
    if not Path(c.file_path).exists():
        raise HTTPException(404, "File missing on server")
    return FileResponse(c.file_path, filename=c.filename)
