"""Pydantic schemas: API request/response bodies and the JSON contracts the LLM must follow."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Recommendation = Literal["Strong Fit", "Good Fit", "Consider", "Not a Fit"]


class JDRequirements(BaseModel):
    role_title: str = ""
    seniority: str = ""
    min_years_experience: float = 0
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    education: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    summary: str = ""

    @field_validator("min_years_experience", mode="before")
    @classmethod
    def _years(cls, v):
        try:
            return max(0.0, float(v or 0))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("must_have_skills", "nice_to_have_skills", "responsibilities", mode="before")
    @classmethod
    def _list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return [str(s).strip() for s in v if str(s).strip()]


def _clamp100(v) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(v)))))
    except (TypeError, ValueError):
        return 0


class ResumeEvaluation(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    skills_score: int = Field(ge=0, le=100)
    experience_score: int = Field(ge=0, le=100)
    education_score: int = Field(ge=0, le=100)
    projects_score: int = Field(ge=0, le=100)
    recommendation: Recommendation = "Consider"
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    interview_questions: list[str] = Field(default_factory=list)

    @field_validator("overall_score", "skills_score", "experience_score",
                     "education_score", "projects_score", mode="before")
    @classmethod
    def _score(cls, v):
        return _clamp100(v)

    @field_validator("recommendation", mode="before")
    @classmethod
    def _rec(cls, v):
        s = str(v or "").strip().lower()
        if "strong" in s:
            return "Strong Fit"
        if "not" in s or "reject" in s or "poor" in s:
            return "Not a Fit"
        if "good" in s:
            return "Good Fit"
        return "Consider"

    @field_validator("strengths", "gaps", "red_flags", "interview_questions", mode="before")
    @classmethod
    def _list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(s).strip() for s in v if str(s).strip()][:8]


class QAAnswer(BaseModel):
    answer: str
    cited: list[str] = Field(default_factory=list)


class Weights(BaseModel):
    llm: float = 0.45
    skills: float = 0.25
    semantic: float = 0.20
    experience: float = 0.10


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=30)
    blind_mode: bool = True
    weights: Weights | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    blind_mode: bool | None = None
    weights: Weights | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    requirements: dict
    weights: dict
    blind_mode: bool
    analysed_by: str
    created_at: datetime
    stats: dict = Field(default_factory=dict)


class CandidateSummary(BaseModel):
    id: int
    job_id: int
    seq: int
    display_name: str
    filename: str
    status: str
    error: str = ""
    final_score: float
    llm_score: float
    skill_score: float
    semantic_score: float
    experience_score: float
    years_experience: float
    recommendation: str
    decision: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    summary: str = ""
    flags: list[str] = Field(default_factory=list)
    rank: int | None = None


class CandidateDetail(CandidateSummary):
    email: str = ""
    phone: str = ""
    links: list[str] = Field(default_factory=list)
    identity_hidden: bool = False
    skills: list[str] = Field(default_factory=list)
    sections: dict = Field(default_factory=dict)
    skill_match: dict = Field(default_factory=dict)
    evaluation: dict = Field(default_factory=dict)
    resume_text: str = ""
    notes: str = ""
    evaluated_by: str = ""
    processing_ms: int = 0
    processed_at: datetime | None = None


class CandidateUpdate(BaseModel):
    decision: Literal["pending", "shortlisted", "on_hold", "rejected"] | None = None
    notes: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskSource(BaseModel):
    candidate_id: int
    label: str
    display_name: str
    snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSource]
    answered_by: str
    tokens: int = 0


def _clean_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
        raise ValueError("enter a valid email address")
    return v


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return _clean_email(v)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return " ".join(v.split())


class LoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        return (v or "").strip().lower()


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: datetime


# Admin console. Every field is listed on purpose: no candidate, resume or score data ever goes here.
class ActionBody(BaseModel):
    reason: str = Field(default="", max_length=500)
    confirm: bool = False

    @field_validator("reason")
    @classmethod
    def _reason(cls, v):
        return " ".join(v.split())


class AdminAccount(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    status_reason: str
    registered_at: datetime
    status_changed_at: datetime | None
    last_login_at: datetime | None
    purge_on: datetime | None = None


class AdminRecruiter(AdminAccount):
    job_count: int
    job_titles: list[str]
    resume_count: int
    resumes_7d: int
    logins_7d: int
    open_flags: int


class AdminEvent(BaseModel):
    id: int
    created_at: datetime
    category: str
    action: str
    actor: str
    target: str
    target_id: int | None
    reason: str
    outcome: str
    detail: dict
    flagged: bool
    reviewed: bool
