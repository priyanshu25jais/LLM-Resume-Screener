from datetime import date

from app.services.parser import estimate_years_experience, extract_contacts, guess_name, parse_resume, split_sections
from conftest import SAMPLES

RESUME = """Amit Verma
amit.v@example.com | +91 98765 43210 | github.com/amitv

EXPERIENCE
Software Engineer, Acme | Jan 2022 - Present
Intern, Beta Labs | Jun 2021 - Dec 2021

EDUCATION
B.Tech CSE, 2017 - 2021

SKILLS
Python, Django
"""


def test_sections_found():
    s = split_sections(RESUME)
    assert {"experience", "education", "skills"} <= set(s)
    assert "Django" in s["skills"]


def test_contacts_and_name():
    c = extract_contacts(RESUME)
    assert c["email"] == "amit.v@example.com"
    assert "98765" in c["phone"]
    assert any("github.com" in link for link in c["links"])
    assert guess_name(RESUME) == "Amit Verma"


def test_years_ignore_education_and_merge_overlaps():
    years = estimate_years_experience(RESUME, today=date(2026, 1, 1))
    assert 4.4 <= years <= 4.7  # Jun 2021 -> Jan 2026, education dates ignored


def test_all_sample_formats_parse():
    for f in (SAMPLES / "resumes").iterdir():
        r = parse_resume(f)
        assert len(r["text"]) > 200, f.name
        assert r["name"], f.name
