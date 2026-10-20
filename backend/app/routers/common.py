"""Shared helpers for routers: lookups and model -> schema conversion."""
from __future__ import annotations

from fastapi import HTTPException

from ..config import settings
from ..models import Candidate, Job, User
from ..schemas import CandidateDetail, CandidateSummary, JobOut
from ..services.accounts import recent_count, record
from ..services.qa import display_name
from ..services.redactor import redact


def _note_foreign_access(db, user: User, kind: str, obj_id: int) -> None:
    # Asking for another recruiter's data is logged; repeated tries raise a flag for the admin
    tries = recent_count(db, "foreign_access", 10, target_id=user.id) + 1
    record(db, "security", "foreign_access", actor=user, target_id=user.id, outcome="denied",
           detail={"kind": kind, "id": obj_id}, flagged=tries == settings.FLAG_FOREIGN_ACCESS)
    db.commit()


def get_job_or_404(db, job_id: int, user: User) -> Job:
    # Someone else's job gives the same 404 as a missing one
    job = db.get(Job, job_id)
    if job and job.owner_id != user.id:
        _note_foreign_access(db, user, "job", job_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(404, "Job not found")
    return job


def get_candidate_or_404(db, cid: int, user: User) -> Candidate:
    c = db.get(Candidate, cid)
    if c and c.job.owner_id != user.id:
        _note_foreign_access(db, user, "candidate", cid)
    if not c or c.job.owner_id != user.id:
        raise HTTPException(404, "Candidate not found")
    return c


def job_stats(job: Job) -> dict:
    cs = job.candidates
    done = [c for c in cs if c.status == "done"]
    by_rec: dict[str, int] = {}
    for c in done:
        by_rec[c.recommendation] = by_rec.get(c.recommendation, 0) + 1
    return {
        "total": len(cs),
        "done": len(done),
        "processing": sum(c.status in ("queued", "processing") for c in cs),
        "failed": sum(c.status == "failed" for c in cs),
        "shortlisted": sum(c.decision == "shortlisted" for c in cs),
        "by_recommendation": by_rec,
        "avg_score": round(sum(c.final_score for c in done) / len(done), 1) if done else 0,
        "top_score": max((c.final_score for c in done), default=0),
        "tokens": token_stats(done),
    }


def token_stats(done: list[Candidate]) -> dict:
    # Add up the token usage saved with each screened resume
    used = saved = calls = cached = fresh = 0
    for c in done:
        t = (c.evaluation or {}).get("tokens") or {}
        if t.get("cached"):
            cached += 1
            saved += t.get("saved", 0)
        elif t.get("total"):
            fresh += 1
            used += t["total"]
            calls += t.get("calls", 0)
    return {"used": used, "saved": saved, "calls": calls, "cached_resumes": cached,
            "avg_per_resume": round(used / fresh) if fresh else 0}


def job_out(job: Job) -> JobOut:
    out = JobOut.model_validate(job)
    out.owner_name = job.owner.name if job.owner else ""
    out.stats = job_stats(job)
    return out


def candidate_summary(c: Candidate, job: Job, rank: int | None = None) -> CandidateSummary:
    sm = c.skill_match or {}
    return CandidateSummary(
        id=c.id, job_id=c.job_id, seq=c.seq, display_name=display_name(c, job), filename=c.filename,
        status=c.status, error=c.error or "", final_score=c.final_score, llm_score=c.llm_score,
        skill_score=c.skill_score, semantic_score=c.semantic_score, experience_score=c.experience_score,
        years_experience=c.years_experience, recommendation=c.recommendation or "", decision=c.decision,
        matched_skills=(sm.get("matched_must", []) + sm.get("matched_nice", []))[:12],
        missing_skills=sm.get("missing_must", [])[:8],
        summary=(c.evaluation or {}).get("summary", ""), flags=c.flags or [], rank=rank,
    )


def candidate_detail(c: Candidate, job: Job, rank: int | None, reveal: bool) -> CandidateDetail:
    hidden = job.blind_mode and not reveal
    base = candidate_summary(c, job, rank).model_dump()
    base["display_name"] = display_name(c, job, reveal)
    return CandidateDetail(
        **base,
        email="" if hidden else c.email, phone="" if hidden else c.phone,
        links=[] if hidden else (c.links or []), identity_hidden=hidden,
        skills=c.skills or [],
        sections={k: redact(v, c.name)[0] for k, v in (c.sections or {}).items()} if hidden else (c.sections or {}),
        skill_match=c.skill_match or {},
        evaluation=c.evaluation or {}, resume_text=c.redacted_text if hidden else c.raw_text,
        notes=c.notes or "", evaluated_by=c.evaluated_by, processing_ms=c.processing_ms,
        processed_at=c.processed_at,
    )


def ranked(job: Job) -> list[tuple[int | None, Candidate]]:
    done = sorted([c for c in job.candidates if c.status == "done"], key=lambda c: (-c.final_score, c.id))
    rest = [c for c in job.candidates if c.status != "done"]
    return [(i + 1, c) for i, c in enumerate(done)] + [(None, c) for c in rest]
