"""Job description analyser: free-text JD -> structured requirements (LLM first, rules as fallback)."""
from __future__ import annotations

import logging
import re

from ..schemas import JDRequirements
from .llm import LLMError, get_llm
from .llm.prompts import JD_SYSTEM, jd_user
from .skills import SKILL_TAXONOMY, find_skill_spans, split_alternatives

log = logging.getLogger("screener.jd")

_NICE_MARKERS = re.compile(
    r"nice[\s-]to[\s-]have|good[\s-]to[\s-]have|preferred|is a plus|a plus|bonus|desirable|added advantage|"
    r"would be great|optional|familiarity with|exposure to", re.I)
_NICE_HEADER = re.compile(r"^\s*(nice|good)[\s-]to[\s-]have|^\s*preferred|^\s*bonus|^\s*desirable", re.I)
_MUST_HEADER = re.compile(r"^\s*(requirements|required|must[\s-]have|qualifications|mandatory|what you need|"
                          r"skills required|key skills|who you are)", re.I)
_YEARS = re.compile(r"(\d{1,2})(?:\.\d)?\s*(?:\+|plus)?\s*(?:-|to|–)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs?)",
                    re.I)
_SENIORITY = [("Lead", r"\b(lead|principal|staff|architect|head)\b"), ("Senior", r"\bsenior|sr\.?\b"),
              ("Intern", r"\bintern(ship)?\b"), ("Junior", r"\b(junior|jr\.?|fresher|entry[\s-]level|graduate)\b")]


def _line_skills(line: str) -> list[str]:
    """Skills named on one JD line; 'FastAPI or Django' becomes a single either-or requirement."""
    spans = find_skill_spans(line)
    used, out = set(), []
    for m in re.finditer(r"\s+or\s+", line, re.I):
        before = [sp for sp in spans if 0 <= m.start() - sp[1] <= 2]
        after = [sp for sp in spans if 0 <= sp[0] - m.end() <= 2]
        if before and after and before[-1][2] != after[0][2]:
            out.append(f"{before[-1][2]} or {after[0][2]}")
            used.update({before[-1], after[0]})
    out.extend(sp[2] for sp in spans if sp not in used)
    return list(dict.fromkeys(out))


_EDU_LINE = re.compile(r"^.*\b(B\.?\s?Tech|B\.E\.?|Bachelor|BCA|B\.?Sc|M\.?\s?Tech|MCA|Master|M\.?Sc|MBA|Ph\.?D)\b.*$",
                       re.I | re.M)


_INTRO_HEADER = re.compile(r"^\s*(responsibilities|what you(?:'ll| will) do|the role|about the role|about us|"
                           r"role overview|job description|key responsibilities|your role|day to day)", re.I)


def analyze_rule_based(title: str, description: str) -> JDRequirements:
    must: list[str] = []
    nice: list[str] = []
    intro: list[str] = []  # skills mentioned outside any requirements list
    mode = "intro"
    edu_line = ""
    for line in description.split("\n"):
        if _NICE_HEADER.search(line):
            mode = "nice"
        elif _MUST_HEADER.search(line):
            mode = "must"
        elif _INTRO_HEADER.search(line):
            mode = "intro"
        if not edu_line and mode != "nice" and _EDU_LINE.search(line):
            edu_line = line
        skills = _line_skills(line)
        if not skills:
            continue
        if mode == "nice" or _NICE_MARKERS.search(line):
            target = nice
        else:
            target = must if mode == "must" else intro
        target.extend(s for s in skills if s not in target)
    must = list(dict.fromkeys(must))
    if not must:  # JD without an explicit requirements list
        must = list(dict.fromkeys(intro))
    else:  # skills only named in the role description count as nice-to-have
        nice = nice + [s for s in intro if s not in must and s not in nice]
    # Very generic implied skills ("JavaScript" from "React") should not dominate must-haves
    must = must[:14]
    nice = [s for s in dict.fromkeys(nice) if s not in must][:12]

    years = 0.0
    for m in _YEARS.finditer(description):
        ctx = description[m.start(): m.end() + 40].lower()
        if "experience" in ctx or "exp" in ctx:
            years = float(m.group(1))
            break
    edu = _EDU_LINE.search(edu_line) if edu_line else None
    blob = f"{title}\n{description}"
    seniority = next((lvl for lvl, pat in _SENIORITY if re.search(pat, title, re.I)), "")
    if not seniority:
        seniority = next((lvl for lvl, pat in _SENIORITY if re.search(pat, blob, re.I)), "Mid")
    resp = [ln.lstrip("-* ").strip() for ln in description.split("\n")
            if ln.strip().startswith(("-", "*")) and 20 < len(ln) < 160][:6]
    return JDRequirements(
        role_title=title, seniority=seniority, min_years_experience=years,
        must_have_skills=must, nice_to_have_skills=nice,
        education=edu.group(0).strip().lstrip("-* ").strip()[:150] if edu else "",
        responsibilities=resp,
        summary=f"{seniority} {title} with {', '.join(must[:5]) or 'relevant skills'}"
                + (f" and {years:g}+ years of experience." if years else "."),
    )


def _tidy(req: JDRequirements) -> JDRequirements:
    """Normalise skill names to the taxonomy and remove duplicates between the two lists."""
    def norm(s: str) -> str:
        return " or ".join(split_alternatives(s))
    must = list(dict.fromkeys(norm(s) for s in req.must_have_skills if norm(s)))
    nice = [s for s in dict.fromkeys(norm(x) for x in req.nice_to_have_skills if norm(x)) if s not in must]
    return req.model_copy(update={"must_have_skills": must[:15], "nice_to_have_skills": nice[:12]})


async def analyze_jd(title: str, description: str) -> tuple[JDRequirements, str]:
    """Return (requirements, analysed_by)."""
    llm = get_llm()
    if llm.available:
        try:
            req = await llm.complete_json(JD_SYSTEM, jd_user(title, description), JDRequirements)
            req = _tidy(req)
            if req.must_have_skills:
                return req, llm.last_label
        except LLMError as exc:
            log.warning("JD analysis by LLM failed, using rules: %s", exc)
    return _tidy(analyze_rule_based(title, description)), "rule-based"


__all__ = ["analyze_jd", "analyze_rule_based", "SKILL_TAXONOMY"]
