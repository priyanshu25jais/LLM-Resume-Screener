"""Admin console API: recruiter accounts, aggregate counts and security events. No candidate data, ever."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import admin_user
from ..config import settings
from ..database import get_db
from ..models import AuditEvent, Candidate, Job, User, utcnow
from ..schemas import ActionBody, AdminAccount, AdminEvent, AdminRecruiter
from ..services import accounts

router = APIRouter(prefix="/api/admin", tags=["admin"])
STATUSES = ("pending", "active", "suspended", "deleted")


def _account(u: User) -> dict:
    purge_on = None
    if u.status == "deleted" and u.deleted_at and not u.purged_at:
        purge_on = u.deleted_at + timedelta(days=settings.DELETION_GRACE_DAYS)
    return dict(id=u.id, name=u.name, email=u.email, role=u.role, status=u.status, status_reason=u.status_reason,
                registered_at=u.created_at, status_changed_at=u.status_changed_at, last_login_at=u.last_login_at,
                purge_on=purge_on)


def _counts_by_user(db, action: str, since) -> dict[int, int]:
    rows = (db.query(AuditEvent.target_user_id, func.count(AuditEvent.id))
            .filter(AuditEvent.action == action, AuditEvent.created_at >= since)
            .group_by(AuditEvent.target_user_id).all())
    return {uid: n for uid, n in rows if uid is not None}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    accounts.purge_due(db)
    week = utcnow() - timedelta(days=7)
    by_status = dict.fromkeys(STATUSES, 0)
    for status, n in (db.query(User.status, func.count(User.id)).filter(User.role == "recruiter")
                      .group_by(User.status).all()):
        by_status[status] = n

    def events_since(action: str) -> int:
        return db.query(AuditEvent).filter(AuditEvent.action == action, AuditEvent.created_at >= week).count()

    return {
        "recruiters": by_status,
        "admins_active": accounts.active_admins(db),
        "jobs": db.query(func.count(Job.id)).scalar(),
        "resumes": db.query(func.count(Candidate.id)).scalar(),
        "resumes_7d": db.query(func.count(Candidate.id)).filter(Candidate.created_at >= week).scalar(),
        "logins_7d": events_since("login"),
        "failed_logins_7d": events_since("login_failed") + events_since("login_locked"),
        "open_flags": db.query(AuditEvent).filter(AuditEvent.flagged, AuditEvent.reviewed_at.is_(None)).count(),
        "policy": {"deletion_grace_days": settings.DELETION_GRACE_DAYS,
                   "audit_retention_days": settings.AUDIT_RETENTION_DAYS,
                   "require_approval": settings.REQUIRE_APPROVAL},
    }


@router.get("/recruiters", response_model=list[AdminRecruiter])
def recruiters(status: Literal["pending", "active", "suspended", "deleted"] | None = None,
               q: str = Query(default="", max_length=100),
               db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    query = db.query(User).filter(User.role == "recruiter", User.purged_at.is_(None))
    if status:
        query = query.filter(User.status == status)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(func.lower(User.name).like(like) | func.lower(User.email).like(like))
    users = query.order_by(User.created_at.desc()).all()

    # Only titles and counts are read here, never candidate rows
    titles: dict[int, list[str]] = {}
    for owner, title in db.query(Job.owner_id, Job.title).order_by(Job.created_at.desc()).all():
        titles.setdefault(owner, []).append(title)
    resumes = accounts.resume_counts(db)
    week = utcnow() - timedelta(days=7)
    recent = dict(db.query(Job.owner_id, func.count(Candidate.id)).join(Candidate, Candidate.job_id == Job.id)
                  .filter(Candidate.created_at >= week).group_by(Job.owner_id).all())
    logins = _counts_by_user(db, "login", week)
    flags = dict(db.query(AuditEvent.target_user_id, func.count(AuditEvent.id))
                 .filter(AuditEvent.flagged, AuditEvent.reviewed_at.is_(None))
                 .group_by(AuditEvent.target_user_id).all())
    return [AdminRecruiter(**_account(u), job_count=len(titles.get(u.id, [])), job_titles=titles.get(u.id, []),
                           resume_count=resumes.get(u.id, 0), resumes_7d=recent.get(u.id, 0),
                           logins_7d=logins.get(u.id, 0), open_flags=flags.get(u.id, 0)) for u in users]


@router.get("/admins", response_model=list[AdminAccount])
def admins(db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    return [AdminAccount(**_account(u)) for u in
            db.query(User).filter(User.role == "admin", User.purged_at.is_(None)).order_by(User.created_at).all()]


ACTIONS = {
    "approve": (accounts.approve, False),
    "reactivate": (accounts.reactivate, False),
    "suspend": (accounts.suspend, True),
    "delete": (accounts.delete, True),
    "demote": (accounts.demote, True),
}


@router.post("/accounts/{uid}/{action}", response_model=AdminAccount)
def account_action(uid: int, action: Literal["approve", "reactivate", "suspend", "delete", "demote"],
                   body: ActionBody, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    fn, serious = ACTIONS[action]
    try:
        if serious and (len(body.reason) < 5 or not body.confirm):
            raise HTTPException(400, "Give a reason (at least 5 characters) and confirm this action")
        return AdminAccount(**_account(fn(db, admin, uid, body.reason)))
    except HTTPException as exc:
        db.rollback()
        accounts.record(db, "admin", action, actor=admin, target_id=uid, reason=body.reason, outcome="denied",
                        detail={"error": str(exc.detail)[:120]})
        db.commit()
        raise


def _name(users: dict[int, User], uid: int | None, category: str = "") -> str:
    if uid is None:
        return "system" if category == "admin" else "-"
    u = users.get(uid)
    return u.name if u else f"account {uid}"


def _events_out(db, rows: list[AuditEvent]) -> list[AdminEvent]:
    ids = [i for r in rows for i in (r.actor_id, r.target_user_id) if i is not None]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    return [AdminEvent(id=r.id, created_at=r.created_at, category=r.category, action=r.action,
                       actor=_name(users, r.actor_id, r.category),
                       target=_name(users, r.target_user_id) if r.target_user_id else "-",
                       target_id=r.target_user_id, reason=r.reason, outcome=r.outcome, detail=r.detail or {},
                       flagged=r.flagged, reviewed=r.reviewed_at is not None) for r in rows]


@router.get("/events", response_model=list[AdminEvent])
def events(kind: Literal["all", "flagged", "admin", "security", "account"] = "all",
           target_id: int | None = None, limit: int = Query(default=100, ge=1, le=500),
           db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    query = db.query(AuditEvent)
    if kind == "flagged":
        query = query.filter(AuditEvent.flagged)
    elif kind != "all":
        query = query.filter(AuditEvent.category == kind)
    if target_id is not None:
        query = query.filter(AuditEvent.target_user_id == target_id)
    return _events_out(db, query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).all())


@router.post("/events/{eid}/review", response_model=AdminEvent)
def review_event(eid: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    ev = db.get(AuditEvent, eid)
    if not ev or not ev.flagged:
        raise HTTPException(404, "Flag not found")
    if ev.reviewed_at is None:
        ev.reviewed_at, ev.reviewed_by = utcnow(), admin.id
        accounts.record(db, "admin", "review_flag", actor=admin, target_id=ev.target_user_id, detail={"event": ev.id})
        db.commit()
    return _events_out(db, [ev])[0]
