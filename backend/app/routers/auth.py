"""Sign up (as a pending recruiter), log in, log out, and the one-click demo recruiter."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import (MAX_TRIES, check_not_locked, clear_failures, current_user, end_session, failures,
                    hash_password, note_failure, start_session, verify_password)
from ..config import settings
from ..database import get_db
from ..models import User, utcnow
from ..schemas import LoginBody, RegisterBody, UserOut
from ..services.accounts import email_ref, record

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEMO_EMAIL = "demo@shortlist.local"
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, name=user.name, email=user.email, role=user.role, status=user.status,
                   created_at=user.created_at)


@router.get("/options")
def options():
    # What the login page should offer
    return {"allow_registration": settings.ALLOW_REGISTRATION, "require_approval": settings.REQUIRE_APPROVAL,
            "demo_login": settings.DEMO_LOGIN}


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterBody, response: Response, db: Session = Depends(get_db)):
    # Sign-up only ever makes recruiters; admins come from scripts/create_admin.py
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(403, "Sign-up is turned off. Ask an admin for an account.")
    if body.email == DEMO_EMAIL or db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "An account with this email already exists")
    status = "pending" if settings.REQUIRE_APPROVAL else "active"
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role="recruiter",
                status=status, status_changed_at=utcnow())
    db.add(user)
    db.flush()
    record(db, "account", "register", actor=user, target_id=user.id, detail={"status": status})
    db.commit()
    if status == "active":
        start_session(db, user, response)
    return user_out(user)


def _failed_login(db, email: str, user: User | None) -> None:
    note_failure(email)
    locked = failures(email) >= MAX_TRIES
    detail = {} if user else {"email_ref": email_ref(email)}
    record(db, "security", "login_locked" if locked else "login_failed", target_id=user.id if user else None,
           outcome="denied", detail=detail, flagged=locked)
    db.commit()


@router.post("/login", response_model=UserOut)
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    check_not_locked(body.email)
    user = db.query(User).filter(User.email == body.email).first()
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)  # same time either way
    if not user or not ok or user.email == DEMO_EMAIL or user.status == "deleted":
        _failed_login(db, body.email, user)
        raise HTTPException(401, "Wrong email or password")
    clear_failures(body.email)
    if user.status != "active":
        record(db, "security", "blocked_login", target_id=user.id, outcome="denied", detail={"status": user.status})
        db.commit()
        if user.status == "pending":
            raise HTTPException(403, "Your account is waiting for an admin to approve it.")
        raise HTTPException(403, "This account is suspended. Contact the admin.")
    user.last_login_at = utcnow()
    record(db, "account", "login", actor=user, target_id=user.id)
    start_session(db, user, response)
    return user_out(user)


@router.post("/demo", response_model=UserOut)
def demo_login(response: Response, db: Session = Depends(get_db)):
    if not settings.DEMO_LOGIN:
        raise HTTPException(404, "The demo account is turned off")
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if not user:
        user = User(name="Demo Recruiter", email=DEMO_EMAIL, password_hash=hash_password(secrets.token_hex(16)),
                    role="recruiter", status="active", status_changed_at=utcnow())
        db.add(user)
        db.flush()
        record(db, "account", "register", actor=user, target_id=user.id, detail={"status": "active", "demo": True})
    if user.status != "active":
        db.commit()
        raise HTTPException(403, "The demo account is not available")
    user.last_login_at = utcnow()
    record(db, "account", "login", actor=user, target_id=user.id)
    start_session(db, user, response)
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(db, request, response)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)
