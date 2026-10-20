# Blind screening: hide name, contacts, age, gender etc. before the resume goes to the LLM
from __future__ import annotations

import re

from .parser import EMAIL_RE, PHONE_RE, URL_RE

_PERSONAL_FIELD = re.compile(
    r"^\s*(?:-\s*)?(date of birth|d\.?o\.?b\.?|birth ?date|age|gender|sex|marital status|nationality|"
    r"religion|caste|father'?s name|mother'?s name|husband'?s name|spouse|passport(?: no\.?)?|"
    r"aadhaa?r(?: no\.?)?|pan no\.?|pan card|permanent address|current address|address|blood group)\s*[:\-–]\s*.*$",
    re.IGNORECASE | re.MULTILINE,
)
_GENDER_WORDS = [
    (re.compile(r"\b(he|she)\b", re.I), "they"),
    (re.compile(r"\b(him)\b", re.I), "them"),
    (re.compile(r"\b(his|hers)\b", re.I), "their"),
    (re.compile(r"\b(her)\b", re.I), "their"),
    (re.compile(r"\b(himself|herself)\b", re.I), "themselves"),
    (re.compile(r"\b(male|female|man|woman|boy|girl)\b", re.I), "[REDACTED]"),
]
_TITLES = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Shri|Smt|Kumari)\.?\s+(?=[A-Z][a-z])")
_AGE = re.compile(r"\b\d{2}\s*(?:years? old|yrs? old|y/o)\b", re.I)
_DOB = re.compile(r"\b(?:born on|born in)\s+[^\n,;]+", re.I)
_PHOTO = re.compile(r"\[?(?:photo|photograph|profile picture)\]?", re.I)


def redact(text: str, name: str = "") -> tuple[str, dict]:
    """Return (redacted_text, counts) where counts says how many items of each kind were removed."""
    counts: dict[str, int] = {}

    def sub(pattern, repl, s, label):
        new, n = pattern.subn(repl, s)
        if n:
            counts[label] = counts.get(label, 0) + n
        return new

    out = text
    out = sub(_PERSONAL_FIELD, lambda m: f"{m.group(1).title()}: [REDACTED]", out, "personal_fields")
    out = sub(EMAIL_RE, "[EMAIL]", out, "email")
    out = sub(URL_RE, "[LINK]", out, "link")
    out = sub(PHONE_RE, "[PHONE]", out, "phone")
    out = sub(_DOB, "[REDACTED]", out, "dob")
    out = sub(_AGE, "[REDACTED]", out, "age")
    out = sub(_PHOTO, "", out, "photo")
    out = sub(_TITLES, "", out, "gender_terms")

    if name:
        parts = [p for p in re.split(r"\s+", name.strip()) if len(p) > 1]
        full = re.compile(r"\b" + r"\s+".join(map(re.escape, parts)) + r"\b", re.I) if parts else None
        if full:
            out = sub(full, "[CANDIDATE]", out, "name")
        for p in parts:  # stray first/last name mentions
            if len(p) >= 3:
                out = sub(re.compile(r"\b" + re.escape(p) + r"\b", re.I), "[CANDIDATE]", out, "name")

    for pattern, repl in _GENDER_WORDS:
        out = sub(pattern, lambda m, r=repl: r.capitalize() if m.group(0)[0].isupper() and r[0] != "[" else r,
                  out, "gender_terms")

    out = re.sub(r"(\[CANDIDATE\]\s*){2,}", "[CANDIDATE] ", out)
    return out, counts
