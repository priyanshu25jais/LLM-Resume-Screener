"""Resume evaluation: LLM rubric scoring (with cache) and a rule-based evaluator for offline mode."""
from __future__ import annotations

import hashlib
import json
import logging
import re

from ..schemas import ResumeEvaluation
from .llm import LLMError, get_llm
from .llm.base import start_usage
from .llm.prompts import EVAL_SYSTEM, PROMPT_VERSION, eval_user
from .scoring import recommendation
from .skills import base_skill, extract_skills

log = logging.getLogger("screener.eval")

INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|prompts?)|"
    r"disregard (?:all |the )?(?:previous|prior|above)|you are now|system prompt|"
    r"(?:rank|rate|score) (?:me|this (?:candidate|resume|applicant)) (?:as )?(?:first|highest|top|100)|"
    r"give (?:me|this (?:candidate|resume|applicant)) (?:a )?(?:score|rating) of|"
    r"(?:assistant|ai|llm|chatgpt|gemini)[,:]? (?:please )?(?:recommend|select|shortlist) (?:me|this)",
    re.I,
)


def detect_injection(text: str) -> list[str]:
    hits = [m.group(0) for m in INJECTION_RE.finditer(text or "")]
    return [f"Resume contains instructions aimed at the AI screener ('{hits[0][:60]}')"] if hits else []


async def evaluate_with_llm(resume_text: str, requirements: dict, jd_text: str, signals: dict,
                            db=None) -> tuple[ResumeEvaluation, str, dict]:
    llm = get_llm()
    key = hashlib.sha256(
        f"{PROMPT_VERSION}|{llm.label}|{json.dumps(requirements, sort_keys=True)}|{resume_text}".encode()
    ).hexdigest()
    if db is not None:
        from ..models import LLMCache
        hit = db.get(LLMCache, key)
        if hit:
            # Same resume and same requirements were screened before: reuse the answer, no tokens spent
            data = json.loads(hit.response)
            saved = (data.pop("_tokens", None) or {}).get("total", 0)
            return ResumeEvaluation.model_validate(data), f"{hit.provider} (cached)", {"cached": True, "saved": saved}

    usage = start_usage()
    prompt = eval_user(requirements, jd_text, resume_text, signals)
    result = await llm.complete_json(EVAL_SYSTEM, prompt, ResumeEvaluation)
    used = llm.last_label
    tokens = {**usage, "cached": False}
    if db is not None:
        from ..models import LLMCache
        db.merge(LLMCache(key=key, provider=used, response=json.dumps({**result.model_dump(), "_tokens": usage})))
        db.commit()
    return result, used, tokens


# Rule-based evaluator, used when no LLM is configured or every provider fails
_DEGREE = re.compile(r"\b(b\.?\s?tech|b\.?\s?e\b|bachelor|bca|b\.?sc|bs\b|m\.?\s?tech|mca|master|m\.?sc|ms\b|"
                     r"mba|ph\.?d|diploma)", re.I)
_RELEVANT_FIELD = re.compile(r"computer|information technology|\bit\b|software|data science|statistics|"
                             r"mathematics|electronics|engineering|artificial intelligence", re.I)
_METRIC = re.compile(r"\d+\s?(%|x\b|k\+?\b|users|customers|requests|ms\b|million|lakh|crore)", re.I)


def evaluate_rule_based(sections: dict, requirements: dict, skill_match: dict,
                        years: float, semantic: float) -> ResumeEvaluation:
    must = skill_match["matched_must"]
    m_total = len(must) + len(skill_match["partial_must"]) + len(skill_match["missing_must"])
    n_total = len(skill_match["matched_nice"]) + len(skill_match["partial_nice"]) + len(skill_match["missing_nice"])
    must_cov = skill_match["must_coverage"]
    nice_cov = (len(skill_match["matched_nice"]) + 0.5 * len(skill_match["partial_nice"])) / n_total if n_total else 0.5
    work = "\n".join(sections.get(k, "") for k in ("experience", "projects"))
    exp_text = sections.get("experience", "")
    proj = sections.get("projects", "")
    work_sk, exp_sk, proj_sk = set(extract_skills(work)), set(extract_skills(exp_text)), set(extract_skills(proj))
    evidenced = [s for s in must if base_skill(s) in work_sk]
    evidence_ratio = len(evidenced) / len(must) if must else 0.0

    skills_score = 100 * (0.6 * must_cov + 0.2 * nice_cov + 0.2 * evidence_ratio * must_cov)

    req_years = float(requirements.get("min_years_experience") or 0)
    exp_fit = min(1.0, years / req_years) if req_years else min(1.0, 0.5 + years / 4)
    relevance = (sum(base_skill(s) in exp_sk for s in must) / len(must)) if (must and exp_text) else 0.0
    experience_score = 100 * (0.7 * exp_fit + 0.3 * relevance) if (years or exp_text) else 15.0

    edu = sections.get("education", "") or ""
    if _DEGREE.search(edu or ""):
        education_score = 80 + (10 if _RELEVANT_FIELD.search(edu) else 0)
        if re.search(r"m\.?\s?tech|mca|master|m\.?sc|ph\.?d", edu, re.I):
            education_score = min(100, education_score + 5)
    else:
        education_score = 45 if requirements.get("education") else 60

    wanted = {base_skill(s) for s in must + skill_match["matched_nice"]}
    proj_hits = len(wanted & proj_sk)
    if proj:
        projects_score = min(100, 35 + 13 * proj_hits + (10 if _METRIC.search(proj) else 0))
    else:
        projects_score = 55 if relevance > 0.5 else 30

    overall = 0.4 * skills_score + 0.3 * experience_score + 0.2 * projects_score + 0.1 * education_score
    overall = 0.85 * overall + 15 * semantic  # a little credit for overall topical fit
    if m_total and must_cov < 0.5:
        overall *= 0.8
    overall = max(0, min(100, overall))
    band, _ = recommendation(overall, must_cov)
    role = requirements.get("role_title") or "this role"

    strengths, gaps, questions = [], [], []
    names = [base_skill(s) for s in must]
    shown = [base_skill(s) for s in evidenced]
    if must:
        strengths.append(f"Has {len(must)} of {m_total} must-have skills: {', '.join(names[:6])}")
    if evidenced:
        strengths.append(f"Shows hands-on use of {', '.join(shown[:4])} in work or projects")
    if req_years and years >= req_years:
        strengths.append(f"About {years:g} years of experience (job asks for {req_years:g}+)")
    elif not req_years and years:
        strengths.append(f"About {years:g} years of professional or internship experience")
    for p in skill_match["partial_must"][:2]:
        strengths.append(f"Transferable experience with {', '.join(p['via'])} (job asks for {p['skill']})")
    if skill_match["matched_nice"]:
        strengths.append(f"Bonus skills: {', '.join(base_skill(x) for x in skill_match['matched_nice'][:5])}")
    if proj and _METRIC.search(proj):
        strengths.append("Projects report measurable results")

    if skill_match["missing_must"]:
        gaps.append(f"Missing must-have skills: {', '.join(skill_match['missing_must'][:6])}")
    listed_only = [base_skill(s) for s in must if s not in evidenced]
    if listed_only and work:
        gaps.append(f"Listed but not shown in work or projects: {', '.join(listed_only[:4])}")
    if req_years and years < req_years:
        gaps.append(f"Experience below requirement: about {years:g} of {req_years:g} years")
    if not proj:
        gaps.append("No projects section to show applied skills")
    if skill_match["missing_nice"] and len(gaps) < 4:
        gaps.append(f"Nice-to-have skills not found: {', '.join(skill_match['missing_nice'][:4])}")

    for s in (shown or names)[:2]:
        questions.append(f"Walk us through a real problem you solved with {s}. What would you do differently now?")
    for s in skill_match["missing_must"][:1]:
        questions.append(f"This role needs {s}. How would you get productive with it in your first month?")
    for p in skill_match["partial_must"][:1]:
        questions.append(f"How does your {p['via'][0]} experience carry over to {p['skill']}?")
    questions.append(f"Which of your past roles or projects best prepares you for {role}, and why?")

    summary = (f"Matches {len(must)} of {m_total or 0} must-have skills for {role} with about {years:g} years of "
               f"experience. " + (f"Main gap: {gaps[0][0].lower() + gaps[0][1:]}." if gaps else "No major gaps detected."))
    return ResumeEvaluation(
        overall_score=round(overall), skills_score=round(skills_score), experience_score=round(experience_score),
        education_score=round(education_score), projects_score=round(projects_score),
        recommendation=band, summary=summary, strengths=strengths[:5], gaps=gaps[:5],
        red_flags=[], interview_questions=questions[:4],
    )


async def evaluate(*, resume_text: str, sections: dict, requirements: dict, jd_text: str,
                   skill_match: dict, years: float, semantic: float, db=None) -> tuple[ResumeEvaluation, str, dict]:
    """Returns (evaluation, who evaluated it, token usage). Uses the LLM if one is set up, else the rules."""
    llm = get_llm()
    if llm.available:
        signals = {
            "matched_must_have": skill_match["matched_must"],
            "related_skills_for_missing": [f"{p['skill']} via {', '.join(p['via'])}" for p in skill_match["partial_must"]],
            "missing_must_have": skill_match["missing_must"],
            "matched_nice_to_have": skill_match["matched_nice"],
            "estimated_years_experience": years,
        }
        try:
            return await evaluate_with_llm(resume_text, requirements, jd_text, signals, db)
        except LLMError as exc:
            log.warning("LLM evaluation failed, falling back to rules: %s", exc)
            res = evaluate_rule_based(sections, requirements, skill_match, years, semantic)
            reason = "all LLM providers failed or are out of quota" if "all providers" in str(exc) \
                else f"LLM error: {str(exc)[:80]}"
            return res, f"rule-based ({reason})", {}
    return evaluate_rule_based(sections, requirements, skill_match, years, semantic), "rule-based", {}
