"""Screening pipeline: parse -> redact -> four signals -> hybrid score, for each uploaded resume."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import datetime, timezone

from ..config import settings
from ..database import SessionLocal
from ..models import Candidate, Job
from .embeddings import semantic_similarity
from .evaluator import detect_injection, evaluate
from .parser import ParseError, parse_resume
from .redactor import redact
from .scoring import experience_fit, final_score, recommendation
from .skills import extract_skills, match_skills

log = logging.getLogger("screener.pipeline")


async def process_candidate(candidate_id: int, sem: asyncio.Semaphore | None = None) -> None:
    async with (sem or contextlib.nullcontext()):
        db = SessionLocal()
        try:
            c = db.get(Candidate, candidate_id)
            if c is None:
                return
            job: Job = c.job
            c.status, c.error = "processing", ""
            db.commit()
            t0 = time.perf_counter()

            # 1. Parse
            parsed = await asyncio.to_thread(parse_resume, c.file_path)
            text = parsed["text"]
            c.raw_text, c.sections = text, parsed["sections"]
            c.name, c.email, c.phone, c.links = parsed["name"], parsed["email"], parsed["phone"], parsed["links"]
            c.years_experience = parsed["years_experience"]
            c.skills = extract_skills(text)

            # 2. Blind mode: anonymise before any model sees the text
            if job.blind_mode:
                redacted, counts = redact(text, c.name)
            else:
                redacted, counts = text, {}
            c.redacted_text = redacted

            # 3. Signals
            req = job.requirements or {}
            sm = match_skills(text, c.skills, req.get("must_have_skills", []), req.get("nice_to_have_skills", []))
            raw_sem, sem_score, sem_backend = await asyncio.to_thread(semantic_similarity, job.description,
                                                                       redacted, db)
            redacted_sections = {k: redact(v, c.name)[0] if job.blind_mode else v for k, v in c.sections.items()}
            evaluation, evaluated_by, tokens = await evaluate(
                resume_text=redacted, sections=redacted_sections, requirements=req, jd_text=job.description,
                skill_match=sm, years=c.years_experience, semantic=sem_score, db=db,
            )
            exp = experience_fit(c.years_experience, float(req.get("min_years_experience") or 0))

            # 4. Hybrid score
            signals = {"llm": evaluation.overall_score / 100, "skills": sm["coverage"],
                       "semantic": sem_score, "experience": exp}
            score = final_score(signals, job.weights)
            band, guard = recommendation(score, sm["must_coverage"])

            flags = list(dict.fromkeys(detect_injection(text) + evaluation.red_flags + guard))
            c.llm_score, c.skill_score, c.semantic_score = signals["llm"], signals["skills"], sem_score
            c.semantic_raw, c.experience_score = raw_sem, exp
            c.final_score, c.recommendation, c.flags = score, band, flags
            c.skill_match = sm
            c.evaluation = {**evaluation.model_dump(), "redaction": counts, "semantic_backend": sem_backend,
                            "tokens": tokens}
            c.evaluated_by = evaluated_by
            c.processing_ms = int((time.perf_counter() - t0) * 1000)
            c.processed_at = datetime.now(timezone.utc)
            c.status = "done"
            db.commit()
            log.info("candidate %s scored %.1f (%s) in %d ms", c.id, score, band, c.processing_ms)
        except ParseError as exc:
            _fail(db, candidate_id, str(exc))
        except Exception as exc:  # never leave a candidate stuck in "processing"
            log.exception("candidate %s failed", candidate_id)
            _fail(db, candidate_id, f"{type(exc).__name__}: {exc}")
        finally:
            db.close()


def _fail(db, candidate_id: int, message: str) -> None:
    db.rollback()
    c = db.get(Candidate, candidate_id)
    if c:
        c.status, c.error = "failed", message[:500]
        db.commit()


async def process_batch(candidate_ids: list[int]) -> None:
    sem = asyncio.Semaphore(max(1, settings.MAX_CONCURRENCY))
    await asyncio.gather(*(process_candidate(cid, sem) for cid in candidate_ids))


def rescore_job(db, job: Job) -> int:
    """Re-apply the job's weights to already-computed signals (no new LLM calls)."""
    n = 0
    for c in job.candidates:
        if c.status != "done":
            continue
        signals = {"llm": c.llm_score, "skills": c.skill_score, "semantic": c.semantic_score,
                   "experience": c.experience_score}
        c.final_score = final_score(signals, job.weights)
        band, guard = recommendation(c.final_score, (c.skill_match or {}).get("must_coverage", 1.0))
        c.recommendation = band
        others = [f for f in (c.flags or []) if not f.startswith("Capped at")]
        c.flags = others + guard
        n += 1
    db.commit()
    return n
