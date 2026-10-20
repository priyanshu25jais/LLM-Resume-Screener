from app.services.skills import extract_skills, match_skills, normalize_skill, split_alternatives


def test_aliases_normalise():
    assert normalize_skill("ReactJS") == "React"
    assert normalize_skill("postgres") == "PostgreSQL"
    assert normalize_skill("k8s") == "Kubernetes"


def test_no_false_positives_from_common_words():
    skills = extract_skills("I excel at the rest of the work in 7th sem at the R&D centre. Let's go!")
    assert not {"Excel", "REST APIs", "Digital Marketing", "R", "Go"} & set(skills)


def test_implied_skills():
    assert {"Python", "Django"} <= set(extract_skills("Built APIs in Django"))


def test_either_or_requirement_and_partial_credit():
    assert split_alternatives("FastAPI or Django") == ("FastAPI", "Django")
    assert split_alternatives("CI/CD") == ("CI/CD",)
    text = "Python, Flask, MySQL"
    m = match_skills(text, extract_skills(text), ["Python", "FastAPI or Django", "PostgreSQL"], ["Docker"])
    assert m["matched_must"] == ["Python"]
    assert {p["skill"] for p in m["partial_must"]} == {"FastAPI or Django", "PostgreSQL"}
    assert m["missing_nice"] == ["Docker"]
    assert 0 < m["coverage"] < 1


def test_extra_skills_exclude_matched_alternatives():
    text = "Python, FastAPI, Redis, Docker, Jira"
    m = match_skills(text, extract_skills(text), ["Python", "FastAPI or Django"], ["Redis or Celery"])
    assert "FastAPI" not in m["extra_skills"] and "Redis" not in m["extra_skills"]
    assert {"Docker", "Jira"} <= set(m["extra_skills"])
