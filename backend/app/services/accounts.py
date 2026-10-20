"""Account lifecycle (pending, active, suspended, deleted), the audit log and the retention purge."""
from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func

from ..auth import hash_password, revoke_sessions
from ..config import settings
from ..models import AuditEvent, Candidate, Job, User, utcnow

log = logging.getLogger("screener.accounts")


def record(db, category: str, action: str, *, actor: User | None = None, target_id: int | None = None,
           reason: str = "", outcome: str = "success", detail: dict | None = None, flagged: bool = False) -> AuditEvent:
    ev = AuditEvent(category=category, action=action, actor_id=actor.id if actor else None, target_user_id=target_id,
                    reason=(reason or "")[:500], outcome=outcome, detail=detail or {}, flagged=flagged)
    db.add(ev)
    return ev


def email_ref(email: str) -> str:
    # Lets the admin group failed logins for an unknown email without storing the email itself
    return hashlib.sha256(f"screener|{email}".encode()).hexdigest()[:12]


def recent_count(db, action: str, minutes: int, *, target_id: int | None = None, detail_key: str = "",
                 detail_value: str = "") -> int:
    since = utcnow() - timedelta(minutes=minutes)
    q = db.query(AuditEvent).filter(AuditEvent.action == action, AuditEvent.created_at >= since)
    if target_id is not None:
        q = q.filter(AuditEvent.target_user_id == target_id)
    rows = q.all()
    if detail_key:
        rows = [r for r in rows if (r.detail or {}).get(detail_key) == detail_value]
    return len(rows)


def active_admins(db) -> int:
    return db.query(User).filter(User.role == "admin", User.status == "active").count()


def create_admin(db, name: str, email: str, password: str) -> User:
    """Used by scripts/create_admin.py: the only way to make an admin."""
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise ValueError("an account with this email already exists")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    user = User(name=" ".join(name.split()), email=email, password_hash=hash_password(password), role="admin",
                status="active", status_changed_at=utcnow())
    db.add(user)
    db.flush()
    record(db, "admin", "admin_created", target_id=user.id, reason="Created with the setup script")
    db.commit()
    return user


def _target(db, uid: int) -> User:
    user = db.get(User, uid)
    if not user or user.purged_at:
        raise HTTPException(404, "Account not found")
    return user


def _guard_last_admin(db, admin: User, target: User) -> None:
    if target.role == "admin" and target.status == "active" and active_admins(db) <= 1:
        raise HTTPException(400, "There must always be at least one active admin")
    if target.id == admin.id:
        raise HTTPException(400, "You cannot do this to your own account")


def _set_status(target: User, status: str, reason: str) -> None:
    target.status, target.status_reason, target.status_changed_at = status, reason[:500], utcnow()


def approve(db, admin: User, uid: int, reason: str = "") -> User:
    target = _target(db, uid)
    if target.status != "pending":
        raise HTTPException(400, "Only pending accounts can be approved")
    _set_status(target, "active", reason)
    record(db, "admin", "approve", actor=admin, target_id=target.id, reason=reason)
    _give_orphan_jobs(db, target)
    db.commit()
    return target


def suspend(db, admin: User, uid: int, reason: str) -> User:
    target = _target(db, uid)
    if target.status not in ("active", "pending"):
        raise HTTPException(400, "Only active or pending accounts can be suspended")
    _guard_last_admin(db, admin, target)
    _set_status(target, "suspended", reason)
    n = revoke_sessions(db, target.id)
    record(db, "admin", "suspend", actor=admin, target_id=target.id, reason=reason, detail={"sessions_ended": n})
    db.commit()
    return target


def reactivate(db, admin: User, uid: int, reason: str = "") -> User:
    target = _target(db, uid)
    if target.status not in ("suspended", "deleted"):
        raise HTTPException(400, "Only suspended or deleted (not yet purged) accounts can be reactivated")
    _set_status(target, "active", reason)
    target.deleted_at = None
    record(db, "admin", "reactivate", actor=admin, target_id=target.id, reason=reason)
    db.commit()
    return target


def delete(db, admin: User, uid: int, reason: str) -> User:
    target = _target(db, uid)
    if target.status == "deleted":
        raise HTTPException(400, "This account is already deleted")
    _guard_last_admin(db, admin, target)
    _set_status(target, "deleted", reason)
    target.deleted_at = utcnow()
    n = revoke_sessions(db, target.id)
    record(db, "admin", "delete", actor=admin, target_id=target.id, reason=reason,
           detail={"sessions_ended": n, "purge_after_days": settings.DELETION_GRACE_DAYS})
    db.commit()
    if settings.DELETION_GRACE_DAYS <= 0:
        purge_due(db)
    return target


def demote(db, admin: User, uid: int, reason: str) -> User:
    target = _target(db, uid)
    if target.role != "admin":
        raise HTTPException(400, "This account is not an admin")
    _guard_last_admin(db, admin, target)
    target.role = "recruiter"
    revoke_sessions(db, target.id)
    record(db, "admin", "demote", actor=admin, target_id=target.id, reason=reason)
    db.commit()
    return target


def _give_orphan_jobs(db, user: User) -> None:
    # Jobs made before accounts existed go to the first recruiter who is approved
    if user.role != "recruiter":
        return
    n = db.query(Job).filter(Job.owner_id.is_(None)).update({"owner_id": user.id})
    if n:
        record(db, "admin", "orphan_jobs_assigned", target_id=user.id, detail={"jobs": n})


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def purge_due(db) -> int:
    """Permanently remove deleted recruiters' data once the grace period is over, and old audit rows."""
    now = utcnow()
    cutoff = now - timedelta(days=max(0, settings.DELETION_GRACE_DAYS))
    purged = 0
    for user in db.query(User).filter(User.status == "deleted", User.purged_at.is_(None)).all():
        if _aware(user.deleted_at) and _aware(user.deleted_at) > cutoff:
            continue
        jobs = db.query(Job).filter(Job.owner_id == user.id).all()
        resumes = sum(len(j.candidates) for j in jobs)
        for job in jobs:
            shutil.rmtree(settings.UPLOAD_DIR / f"job_{job.id}", ignore_errors=True)
            db.delete(job)  # candidates go with it
        revoke_sessions(db, user.id)
        # Keep an anonymous row so audit entries still point at a real id
        user.name, user.email = f"Deleted user {user.id}", f"deleted-{user.id}@invalid"
        user.password_hash, user.status_reason, user.purged_at = "!", "", now
        record(db, "admin", "purge", target_id=user.id, detail={"jobs": len(jobs), "resumes": resumes})
        purged += 1
    old = now - timedelta(days=max(1, settings.AUDIT_RETENTION_DAYS))
    db.query(AuditEvent).filter(AuditEvent.created_at < old).delete()
    db.commit()
    if purged:
        log.info("purged %d deleted account(s)", purged)
    return purged


def resume_counts(db) -> dict[int, int]:
    rows = (db.query(Job.owner_id, func.count(Candidate.id)).join(Candidate, Candidate.job_id == Job.id)
            .group_by(Job.owner_id).all())
    return {owner: n for owner, n in rows if owner is not None}
