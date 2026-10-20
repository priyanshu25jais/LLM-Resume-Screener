"""Resume parsing: text extraction, section splitting, contact details and years of experience."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class ParseError(Exception):
    pass


# Text extraction
def extract_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        text = _pdf_text(path)
    elif ext == ".docx":
        text = _docx_text(path)
    elif ext in (".txt", ".md"):
        raw = path.read_bytes()
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        raise ParseError(f"Unsupported file type '{ext}'. Use PDF, DOCX or TXT.")
    text = clean_text(text)
    if len(text) < 50:
        raise ParseError("Could not read enough text from this file (is it a scanned image?).")
    return text


def _pdf_text(path: Path) -> str:
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = [(p.extract_text(x_tolerance=1.5, y_tolerance=3) or "") for p in pdf.pages]
        text = "\n".join(pages)
    except Exception:  # fall through to pypdf
        text = ""
    if len(text.strip()) < 50:
        try:
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        except Exception as exc:
            raise ParseError(f"Could not open PDF: {exc}") from exc
    return text


def _docx_text(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:
        raise ParseError("python-docx is not installed") from exc
    try:
        d = docx.Document(str(path))
    except Exception as exc:
        raise ParseError(f"Could not open DOCX: {exc}") from exc
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(parts)


_BULLETS = re.compile(r"^[\s]*[•●▪◦‣⁃∙➢►–—*]+\s*", re.M)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").replace("\t", " ")
    text = re.sub(r"[​‌‍﻿]", "", text)
    text = re.sub(r"\(cid:\d+\)\s*", "- ", text)  # unmapped PDF glyphs (usually bullet symbols)
    text = _BULLETS.sub("- ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Sections
SECTION_ALIASES: dict[str, list[str]] = {
    "summary": ["summary", "professional summary", "profile", "profile summary", "career objective",
                "objective", "about me", "about", "career summary", "overview"],
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "work history", "employment", "internships", "internship", "internship experience",
                   "experience and internships", "relevant experience"],
    "education": ["education", "academic background", "academics", "educational qualification",
                  "educational qualifications", "qualifications", "academic qualifications", "education details"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack",
               "skill set", "skills summary", "technical proficiency", "tools and technologies", "competencies"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "project experience",
                 "major projects", "selected projects"],
    "certifications": ["certifications", "certification", "certificates", "courses", "licenses",
                       "licenses and certifications", "training", "trainings"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards and achievements"],
    "other": ["languages", "interests", "hobbies", "personal details", "personal information", "declaration",
              "extracurricular activities", "extra curricular activities", "positions of responsibility",
              "publications", "volunteering", "references"],
}
_HEADER_LOOKUP = {alias: name for name, aliases in SECTION_ALIASES.items() for alias in aliases}


def _header_name(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 45 or len(s.split()) > 5:
        return None
    key = re.sub(r"[^a-z& ]", "", s.lower().replace("&", "and")).strip()
    key = re.sub(r"\s+", " ", key)
    return _HEADER_LOOKUP.get(key)


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.split("\n"):
        name = _header_name(line)
        if name:
            current = name
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


# Contacts & name
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?<![\d/])(?:\+?91[\s\-]?|0)?[6-9]\d{4}[\s\-]?\d{5}(?![\d/])"  # Indian mobile
    r"|(?<![\d/])\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}(?![\d/])"  # international
    r"|(?<![\d/])\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}(?![\d/])"  # US style
)
URL_RE = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin\.com|github\.com|gitlab\.com|behance\.net)/\S+",
                    re.IGNORECASE)


def extract_contacts(text: str) -> dict:
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))
    phones = list(dict.fromkeys(m.group(0).strip() for m in PHONE_RE.finditer(text)))
    links = list(dict.fromkeys(u.rstrip(".,;)|") for u in URL_RE.findall(text)))
    return {"email": emails[0] if emails else "", "phone": phones[0] if phones else "", "links": links[:6]}


_NOT_NAME = re.compile(r"resume|curriculum|vitae|\bcv\b|@|http|www\.|\d{3,}|address|phone|email|mobile",
                       re.IGNORECASE)


def guess_name(text: str) -> str:
    m = re.search(r"^\s*name\s*[:\-]\s*([A-Za-z][A-Za-z .']{2,40})$", text, re.IGNORECASE | re.M)
    if m:
        return _title(m.group(1))
    for line in [ln.strip() for ln in text.split("\n") if ln.strip()][:6]:
        if _NOT_NAME.search(line) or _header_name(line):
            continue
        candidate = re.split(r"\s[|•\-–]\s", line)[0].strip()
        words = candidate.replace(".", ". ").split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.']*", w) for w in words):
            if len(candidate) <= 40:
                return _title(candidate)
    return ""


def _title(s: str) -> str:
    return " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize() for w in s.split())


# Years of experience
_MONTHS = {m: i for i, names in enumerate([
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
    ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
    ("oct", "october"), ("nov", "november"), ("dec", "december")], start=1) for m in names}
_MONTH_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_POINT = rf"(?:{_MONTH_RE}\.?,?\s*(?:'|’)?\d{{2,4}}|\d{{1,2}}\s*[/\-.]\s*\d{{4}}|(?:19|20)\d{{2}})"
_RANGE_RE = re.compile(
    rf"(?P<s>{_POINT})\s*(?:-|–|—|to|till|until|~)\s*(?P<e>{_POINT}|present|current|now|till date|ongoing|today)",
    re.IGNORECASE,
)
_EXPLICIT_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs|year)\s*(?:of\s+)?(?:professional\s+|industry\s+|work\s+|"
    r"hands[\s-]on\s+|total\s+|relevant\s+)?(?:experience|exp\b)", re.IGNORECASE)


def _to_month_index(point: str, is_end: bool, today: date) -> int | None:
    p = point.strip().lower()
    if p in ("present", "current", "now", "till date", "ongoing", "today"):
        return today.year * 12 + today.month
    m = re.match(rf"({_MONTH_RE})\.?,?\s*(?:'|’)?(\d{{2,4}})", p)
    if m:
        month = _MONTHS[m.group(1)[:4] if m.group(1)[:4] in _MONTHS else m.group(1)[:3]]
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return year * 12 + month
    m = re.match(r"(\d{1,2})\s*[/\-.]\s*(\d{4})", p)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)) * 12 + int(m.group(1))
    m = re.match(r"((?:19|20)\d{2})", p)
    if m:
        return int(m.group(1)) * 12 + 1  # year only: count from January
    return None


def estimate_years_experience(text: str, sections: dict[str, str] | None = None,
                              today: date | None = None) -> float:
    """Merge the date ranges in the experience section into total years (overlaps counted once)."""
    today = today or date.today()
    sections = sections or split_sections(text)
    scope = sections.get("experience")
    if not scope:  # no experience heading: use everything except education
        scope = "\n".join(v for k, v in sections.items()
                          if k not in ("education", "certifications", "projects", "achievements"))
    intervals = []
    for m in _RANGE_RE.finditer(scope):
        s = _to_month_index(m.group("s"), False, today)
        e = _to_month_index(m.group("e"), True, today)
        if s is None or e is None or e < s or s < 1970 * 12:
            continue
        e = min(e, today.year * 12 + today.month)
        intervals.append((s, max(e, s + 1)))
    months = 0
    for s, e in _merge(intervals):
        months += e - s
    computed = round(months / 12, 1)
    explicit = [float(x) for x in _EXPLICIT_RE.findall(text) if float(x) <= 40]
    return round(max([computed, *explicit]), 1)


def _merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


# One call to parse a resume
def parse_resume(path: str | Path) -> dict:
    text = extract_text(path)
    sections = split_sections(text)
    contacts = extract_contacts(text)
    return {
        "text": text,
        "sections": sections,
        "name": guess_name(text),
        **contacts,
        "years_experience": estimate_years_experience(text, sections),
    }
