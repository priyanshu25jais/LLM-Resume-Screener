import os
import sys
import tempfile
from pathlib import Path

# Isolated database and offline mode for every test run
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="screener_test_")
os.environ["LLM_PROVIDER"] = "offline"
os.environ["EMBEDDING_PROVIDER"] = "tfidf"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def make_admin(email="admin@example.com", name="Site Admin", password="admin-pass-1"):
    # Admins can only be made by the setup script's function, never through sign-up
    from app.database import SessionLocal, init_db
    from app.models import User
    from app.services.accounts import create_admin
    init_db()
    with SessionLocal() as db:
        if not db.query(User).filter(User.email == email).first():
            create_admin(db, name, email, password)
    return {"email": email, "password": password}


def activate(email):
    from app.database import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        db.query(User).filter(User.email == email).update({"status": "active"})
        db.commit()


def login(client, email="hr@example.com", name="HR Recruiter", password="password123"):
    # Sign up as a recruiter, get approved, log in (or just log in if the account exists)
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert r.status_code in (201, 409), r.text
    activate(email)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def login_admin(client, **kw):
    creds = make_admin(**kw)
    r = client.post("/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return r.json()
