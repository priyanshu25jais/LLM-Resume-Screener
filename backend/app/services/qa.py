"""Ask questions about the candidate pool (retrieval-augmented generation over resumes)."""
from __future__ import annotations

import asyncio
import logging
import re

from ..models import Job
from ..schemas import AskResponse, AskSource, QAAnswer
from .embeddings import chunk_text, rank_passages
from .llm import LLMError, get_llm
from .llm.base import start_usage
from .llm.prompts import QA_SYSTEM, qa_user
from .skills import extract_skills, find_skill_spans

log = logging.getLogger("screener.qa")
TOP_K = 8


def label_of(c) -> str:
    return f"C{c.seq}"


def display_name(c, job: Job, reveal: bool = False) -> str:
    if job.blind_mode and not reveal:
        return f"Candidate {c.seq}"
    return c.name or f"Candidate {c.seq}"


async def ask(db, job: Job, question: str) -> AskResponse:
    done = [c for c in job.candidates if c.status == "done"]
    if not done:
        return AskResponse(answer="No screened resumes yet for this job.", sources=[], answered_by="-")

    passages: list[tuple[object, str]] = []
    for c in done:
        text = c.redacted_text if job.blind_mode else c.raw_text
        for chunk in chunk_text(text):
            passages.append((c, chunk))

    scores = await asyncio.to_thread(rank_passages, question, [p for _, p in passages], db)
    q_skills = set(extract_skills(question))
    ranked = []
    for (c, chunk), s in zip(passages, scores):
        if q_skills:
            s += 0.15 * len(q_skills & set(extract_skills(chunk)))
        ranked.append((s, c, chunk))
    ranked.sort(key=lambda t: t[0], reverse=True)

    picked, per_cand = [], {}
    for s, c, chunk in ranked:
        if per_cand.get(c.id, 0) >= 2:
            continue
        per_cand[c.id] = per_cand.get(c.id, 0) + 1
        picked.append((s, c, chunk))
        if len(picked) >= TOP_K:
            break

    if q_skills:
        with_skill = [t for t in picked if q_skills & set(extract_skills(t[2]))]
        picked = with_skill or picked

    sources = [AskSource(candidate_id=c.id, label=label_of(c), display_name=display_name(c, job),
                         snippet=_snippet(chunk, q_skills), score=round(s, 3)) for s, c, chunk in picked]

    llm = get_llm()
    if llm.available:
        usage = start_usage()
        try:
            res = await llm.complete_json(
                QA_SYSTEM, qa_user(question, job.title, [(label_of(c), chunk) for _, c, chunk in picked]), QAAnswer)
            cited = {x.strip("[] ").upper() for x in res.cited}
            if cited:
                sources = [s for s in sources if s.label in cited] + [s for s in sources if s.label not in cited]
            return AskResponse(answer=res.answer, sources=sources[:6], answered_by=llm.last_label,
                               tokens=usage["total"])
        except LLMError as exc:
            log.warning("Q&A LLM call failed: %s", exc)

    if q_skills:
        have = [c for c in done if q_skills & set(c.skills or [])]
        if have:
            names = ", ".join(display_name(c, job) if job.blind_mode else f"{display_name(c, job)} ({label_of(c)})"
                              for c in have[:8])
            answer = f"{len(have)} candidate(s) mention {', '.join(sorted(q_skills))}: {names}. See the excerpts below."
        else:
            answer = f"No screened resume mentions {', '.join(sorted(q_skills))}."
    else:
        answer = "Most relevant resume excerpts for your question are listed below (offline mode, no LLM summary)."
    return AskResponse(answer=answer, sources=sources[:6], answered_by="retrieval only")


def _snippet(text: str, skills: set[str] | None = None, n: int = 260) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    start = 0
    if skills:
        hit = next((sp for sp in find_skill_spans(text) if sp[2] in skills), None)
        if hit:
            start = max(0, hit[0] - n // 3)
            while start > 0 and text[start - 1] != " ":
                start -= 1
    piece = text[start:start + n]
    if start + n < len(text):
        piece = piece.rsplit(" ", 1)[0] + " \u2026"
    return ("\u2026 " if start > 0 else "") + piece
