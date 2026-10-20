from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from conftest import login, login_admin


def signup(cl, name, email, password="secret-pass-1"):
    return cl.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def test_everything_needs_login():
    with TestClient(app) as cl:
        assert cl.get("/api/jobs").status_code == 401
        assert cl.get("/api/auth/me").status_code == 401
        assert cl.get("/api/admin/overview").status_code == 401
        assert cl.post("/api/demo/backend").status_code == 401
        assert cl.get("/api/health").status_code == 200  # status pill works before login


def test_signup_never_makes_an_admin():
    with TestClient(app) as cl:
        with SessionLocal() as db:
            db.query(User).filter(User.role == "admin").update({"status": "suspended"})  # as if no admin exists
            db.commit()
        r = signup(cl, "First Person", "first@x.com").json()
        assert r["role"] == "recruiter" and r["status"] == "pending"
        assert "shortlist_session" not in cl.cookies  # no login until approved
        assert cl.get("/api/auth/me").status_code == 401
        assert signup(cl, "Copy", "FIRST@x.com ").status_code == 409
        with SessionLocal() as db:
            db.query(User).filter(User.role == "admin").update({"status": "active"})
            db.commit()


def test_passwords_are_hashed_and_logout_works():
    with TestClient(app) as cl:
        login(cl, "hash@x.com", "Hash Check", "my-long-password")
        with SessionLocal() as db:
            stored = db.query(User).filter(User.email == "hash@x.com").one().password_hash
        assert stored.startswith("pbkdf2_sha256$") and "my-long-password" not in stored
        assert cl.post("/api/auth/logout").status_code == 204
        assert cl.get("/api/auth/me").status_code == 401
        assert cl.post("/api/auth/login", json={"email": "HASH@x.com", "password": "my-long-password"}).status_code == 200
        assert signup(cl, "Short", "short@x.com", "1234").status_code == 422


def test_wrong_passwords_lock_the_account_and_raise_a_flag():
    with TestClient(app) as cl:
        login(cl, "lock@x.com", "Lock Me", "right-password")
        for _ in range(5):
            assert cl.post("/api/auth/login", json={"email": "lock@x.com", "password": "nope"}).status_code == 401
        r = cl.post("/api/auth/login", json={"email": "lock@x.com", "password": "right-password"})
        assert r.status_code == 429 and "minute" in r.json()["detail"]
        for _ in range(5):
            cl.post("/api/auth/login", json={"email": "ghost@x.com", "password": "nope"})
    with SessionLocal() as db:
        flags = db.query(AuditEvent).filter(AuditEvent.action == "login_locked").all()
        assert len(flags) == 2 and all(f.flagged for f in flags)
        ghost = [f for f in flags if f.target_user_id is None][0]
        assert "email_ref" in ghost.detail and "ghost" not in str(ghost.detail)  # email is not stored


def test_demo_account_is_an_active_recruiter():
    with TestClient(app) as cl:
        assert cl.get("/api/auth/options").json()["demo_login"] is True
        me = cl.post("/api/auth/demo").json()
        assert me["role"] == "recruiter" and me["status"] == "active" and me["name"] == "Demo Recruiter"
        assert cl.get("/api/admin/overview").status_code == 403
        assert cl.post("/api/auth/login", json={"email": "demo@shortlist.local", "password": ""}).status_code == 401


def test_admin_login_works():
    with TestClient(app) as cl:
        assert login_admin(cl)["role"] == "admin"
        assert cl.get("/api/admin/overview").status_code == 200
