"""Passwords, login sessions and the "who is logged in" check used by every protected route."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response

from .config import settings
from .database import get_db
from .models import User, UserSession

COOKIE = "shortlist_session"
ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS)
    return f"pbkdf2_sha256${ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(check, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.query(UserSession).filter(UserSession.expires_at < now).delete()
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id,
                       expires_at=now + settings.SESSION_DAYS * 86400))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=settings.SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", path="/", secure=settings.COOKIE_SECURE)


def end_session(db, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.query(UserSession).filter(UserSession.token_hash == _token_hash(token)).delete()
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def revoke_sessions(db, user_id: int) -> int:
    return db.query(UserSession).filter(UserSession.user_id == user_id).delete()


def current_user(request: Request, db=Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if token:
        s = db.get(UserSession, _token_hash(token))
        if s and s.expires_at > time.time():
            if s.user.status == "active":
                return s.user
            # Suspended or deleted since this login: end every session of that account
            revoke_sessions(db, s.user_id)
            db.commit()
    raise HTTPException(401, "Please log in")


def recruiter_user(user: User = Depends(current_user)) -> User:
    if user.role != "recruiter":
        raise HTTPException(403, "Not allowed")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Not allowed")
    return user


# Slow down password guessing: 5 wrong tries for an email locks it for 10 minutes
_failed: dict[str, list[float]] = {}
MAX_TRIES, LOCK_SECONDS = 5, 600


def check_not_locked(email: str) -> None:
    now = time.time()
    recent = [t for t in _failed.get(email, []) if now - t < LOCK_SECONDS]
    _failed[email] = recent
    if len(recent) >= MAX_TRIES:
        wait = int((LOCK_SECONDS - (now - recent[0])) / 60) + 1
        raise HTTPException(429, f"Too many wrong tries. Try again in {wait} minute(s).")


def note_failure(email: str) -> None:
    _failed.setdefault(email, []).append(time.time())


def failures(email: str) -> int:
    return len(_failed.get(email, []))


def clear_failures(email: str) -> None:
    _failed.pop(email, None)
