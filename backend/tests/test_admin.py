# Acceptance tests for the admin / recruiter separation (numbers match the change request)
import json
from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, Candidate, Job, User, UserSession, utcnow
from app.services.accounts import create_admin, purge_due
from conftest import SAMPLES, login, login_admin

JD = (SAMPLES / "job_descriptions" / "python_backend_developer.txt").read_text()
RESUME = SAMPLES / "resumes" / "arjun_reddy.txt"
SERIOUS = {"reason": "Policy check for the test", "confirm": True}


def recruiter_with_job(cl, email):
    me = login(cl, email, email.split("@")[0].title())
    job = cl.post("/api/jobs", json={"title": f"Backend role {me['id']}", "description": JD}).json()
    cl.post(f"/api/jobs/{job['id']}/resumes", files=[("files", (RESUME.name, RESUME.read_bytes()))])
    cid = cl.get(f"/api/jobs/{job['id']}/candidates").json()[0]["id"]
    return me, job, cid


def recruiter_urls(jid, cid):
    return [("get", "/api/jobs"), ("get", f"/api/jobs/{jid}"), ("get", f"/api/jobs/{jid}/candidates"),
            ("get", f"/api/jobs/{jid}/export.csv"), ("post", f"/api/jobs/{jid}/ask"),
            ("post", f"/api/jobs/{jid}/rescreen"), ("get", f"/api/candidates/{cid}"),
            ("get", f"/api/candidates/{cid}/file"), ("post", f"/api/candidates/{cid}/reprocess"),
            ("post", "/api/demo/backend")]


def call(cl, method, url):
    if method == "get":
        return cl.get(url)
    return cl.post(url, json={"question": "Who knows Docker?"} if url.endswith("/ask") else None)


def test_1_admin_cannot_read_candidates_resumes_rankings_or_results():
    with TestClient(app) as rec, TestClient(app) as adm:
        _, job, cid = recruiter_with_job(rec, "r1@x.com")
        login_admin(adm)
        for method, url in recruiter_urls(job["id"], cid):
            assert call(adm, method, url).status_code == 403, url


def test_2_admin_cannot_create_change_or_delete_jobs():
    with TestClient(app) as rec, TestClient(app) as adm:
        _, job, _ = recruiter_with_job(rec, "r2@x.com")
        login_admin(adm)
        jid = job["id"]
        assert adm.post("/api/jobs", json={"title": "Admin job", "description": JD}).status_code == 403
        assert adm.patch(f"/api/jobs/{jid}", json={"title": "Changed"}).status_code == 403
        assert adm.put(f"/api/jobs/{jid}/requirements", json={"must_have_skills": []}).status_code == 403
        assert adm.post(f"/api/jobs/{jid}/resumes", files=[("files", ("a.txt", b"x" * 50))]).status_code == 403
        assert adm.delete(f"/api/jobs/{jid}").status_code == 403
        assert rec.get(f"/api/jobs/{jid}").json()["title"] == job["title"]  # untouched


def test_3_admin_sees_allowlisted_metadata_and_counts_only():
    with TestClient(app) as rec, TestClient(app) as adm:
        me, job, cid = recruiter_with_job(rec, "r3@x.com")
        candidate = rec.get(f"/api/candidates/{cid}?reveal=true").json()
        login_admin(adm)
        rows = adm.get("/api/admin/recruiters", params={"q": "r3@x"}).json()
        assert len(rows) == 1
        row = rows[0]
        assert set(row) == {"id", "name", "email", "role", "status", "status_reason", "registered_at",
                            "status_changed_at", "last_login_at", "purge_on", "job_count", "job_titles",
                            "resume_count", "resumes_7d", "logins_7d", "open_flags"}
        assert row["job_titles"] == [job["title"]] and row["job_count"] == 1 and row["resume_count"] == 1
        overview = adm.get("/api/admin/overview").json()
        assert set(overview) == {"recruiters", "admins_active", "jobs", "resumes", "resumes_7d", "logins_7d",
                                 "failed_logins_7d", "open_flags", "policy"}
        everything = json.dumps([adm.get("/api/admin/recruiters").json(), overview,
                                 adm.get("/api/admin/events?limit=500").json(), adm.get("/api/admin/admins").json()])
        for private in (candidate["display_name"], candidate["email"], candidate["phone"], JD[200:260]):
            assert private and private not in everything
        assert adm.get("/api/admin/recruiters", params={"status": "nonsense"}).status_code == 422


def test_4_recruiters_cannot_reach_each_others_data():
    with TestClient(app) as a, TestClient(app) as b:
        _, job, cid = recruiter_with_job(a, "r4a@x.com")
        me_b = login(b, "r4b@x.com", "Other Recruiter")
        assert job["id"] not in [j["id"] for j in b.get("/api/jobs").json()]
        for method, url in recruiter_urls(job["id"], cid)[1:-1]:
            assert call(b, method, url).status_code == 404, url
        assert b.patch(f"/api/candidates/{cid}", json={"decision": "rejected"}).status_code == 404
        assert b.delete(f"/api/jobs/{job['id']}").status_code == 404
        assert a.get(f"/api/candidates/{cid}").json()["decision"] == "pending"
    with SessionLocal() as db:
        tries = db.query(AuditEvent).filter(AuditEvent.action == "foreign_access",
                                            AuditEvent.target_user_id == me_b["id"]).all()
        assert len(tries) >= settings.FLAG_FOREIGN_ACCESS and any(t.flagged for t in tries)


def test_5_pending_and_suspended_recruiters_are_blocked():
    with TestClient(app) as cl, TestClient(app) as adm:
        r = cl.post("/api/auth/register", json={"name": "New One", "email": "r5@x.com", "password": "password123"})
        assert r.json()["status"] == "pending"
        login_r = cl.post("/api/auth/login", json={"email": "r5@x.com", "password": "password123"})
        assert login_r.status_code == 403 and "approve" in login_r.json()["detail"]
        assert cl.get("/api/jobs").status_code == 401
        login_admin(adm)
        uid = r.json()["id"]
        assert adm.post(f"/api/admin/accounts/{uid}/suspend", json=SERIOUS).json()["status"] == "suspended"
        login_s = cl.post("/api/auth/login", json={"email": "r5@x.com", "password": "password123"})
        assert login_s.status_code == 403 and "suspended" in login_s.json()["detail"]


def test_6_suspension_revokes_existing_sessions():
    with TestClient(app) as one, TestClient(app) as two, TestClient(app) as adm:
        me = login(one, "r6@x.com", "Two Devices")
        two.post("/api/auth/login", json={"email": "r6@x.com", "password": "password123"})
        assert one.get("/api/jobs").status_code == 200 and two.get("/api/jobs").status_code == 200
        login_admin(adm)
        adm.post(f"/api/admin/accounts/{me['id']}/suspend", json=SERIOUS)
        with SessionLocal() as db:
            assert db.query(UserSession).filter(UserSession.user_id == me["id"]).count() == 0
        assert one.get("/api/jobs").status_code == 401 and two.get("/api/jobs").status_code == 401
        adm.post(f"/api/admin/accounts/{me['id']}/reactivate", json={"reason": "Checked"})
        assert one.post("/api/auth/login", json={"email": "r6@x.com", "password": "password123"}).status_code == 200


def test_7_only_admins_manage_accounts_and_serious_actions_need_reason_and_confirm():
    with TestClient(app) as rec, TestClient(app) as adm, TestClient(app) as anon:
        r = anon.post("/api/auth/register", json={"name": "Waiting", "email": "r7@x.com", "password": "password123"})
        uid = r.json()["id"]
        login(rec, "r7rec@x.com", "Plain Recruiter")
        assert rec.post(f"/api/admin/accounts/{uid}/approve", json={}).status_code == 403
        assert rec.get("/api/admin/recruiters").status_code == 403
        assert anon.post(f"/api/admin/accounts/{uid}/approve", json={}).status_code == 401
        login_admin(adm)
        assert adm.post(f"/api/admin/accounts/{uid}/approve", json={}).json()["status"] == "active"
        assert adm.post(f"/api/admin/accounts/{uid}/suspend", json={"reason": "x", "confirm": True}).status_code == 400
        assert adm.post(f"/api/admin/accounts/{uid}/delete", json={"reason": "Long enough"}).status_code == 400
        assert adm.post(f"/api/admin/accounts/{uid}/approve", json={}).status_code == 400  # not pending any more
    with SessionLocal() as db:
        denied = db.query(AuditEvent).filter(AuditEvent.target_user_id == uid, AuditEvent.outcome == "denied").all()
        assert {d.action for d in denied} >= {"suspend", "delete", "approve"}


def test_8_last_active_admin_cannot_be_removed_or_demoted():
    with SessionLocal() as db:
        db.query(User).filter(User.role == "admin", User.email != "admin@example.com").update({"status": "suspended"})
        db.commit()
    with TestClient(app) as adm:
        me = login_admin(adm)
        for action in ("suspend", "delete", "demote"):
            r = adm.post(f"/api/admin/accounts/{me['id']}/{action}", json=SERIOUS)
            assert r.status_code == 400 and "at least one active admin" in r.json()["detail"]
        with SessionLocal() as db:
            second = create_admin(db, "Second Admin", "admin2@x.com", "admin-pass-2")
        r = adm.post(f"/api/admin/accounts/{me['id']}/demote", json=SERIOUS)
        assert r.status_code == 400 and "own account" in r.json()["detail"]
        assert adm.post(f"/api/admin/accounts/{second.id}/demote", json=SERIOUS).json()["role"] == "recruiter"
        assert adm.get("/api/admin/overview").json()["admins_active"] == 1


def test_9_deletion_follows_the_retention_policy(monkeypatch):
    monkeypatch.setattr(settings, "DELETION_GRACE_DAYS", 30)
    with TestClient(app) as rec, TestClient(app) as adm:
        me, job, cid = recruiter_with_job(rec, "r9@x.com")
        login_admin(adm)
        out = adm.post(f"/api/admin/accounts/{me['id']}/delete", json=SERIOUS).json()
        assert out["status"] == "deleted" and out["purge_on"]
        assert rec.get("/api/jobs").status_code == 401
        assert rec.post("/api/auth/login", json={"email": "r9@x.com", "password": "password123"}).status_code == 401
        with SessionLocal() as db:
            purge_due(db)
            assert db.get(Job, job["id"]) is not None  # still inside the grace period
            db.query(User).filter(User.id == me["id"]).update({"deleted_at": utcnow() - timedelta(days=31)})
            db.commit()
            assert purge_due(db) == 1
            assert db.get(Job, job["id"]) is None and db.get(Candidate, cid) is None
            gone = db.get(User, me["id"])
            assert gone.email == f"deleted-{me['id']}@invalid" and gone.name.startswith("Deleted user")
            assert not (settings.UPLOAD_DIR / f"job_{job['id']}").exists()
            ev = db.query(AuditEvent).filter(AuditEvent.action == "purge", AuditEvent.target_user_id == me["id"]).one()
            assert ev.detail == {"jobs": 1, "resumes": 1}
        assert adm.post(f"/api/admin/accounts/{me['id']}/reactivate", json={}).status_code == 404  # purged


def test_9b_zero_grace_purges_at_once(monkeypatch):
    monkeypatch.setattr(settings, "DELETION_GRACE_DAYS", 0)
    with TestClient(app) as rec, TestClient(app) as adm:
        me, job, _ = recruiter_with_job(rec, "r9b@x.com")
        login_admin(adm)
        adm.post(f"/api/admin/accounts/{me['id']}/delete", json=SERIOUS)
        with SessionLocal() as db:
            assert db.get(Job, job["id"]) is None and db.get(User, me["id"]).purged_at is not None


def test_10_audit_log_records_actions_without_resume_contents():
    with TestClient(app) as rec, TestClient(app) as adm:
        me, _, cid = recruiter_with_job(rec, "r10@x.com")
        resume_text = rec.get(f"/api/candidates/{cid}?reveal=true").json()["resume_text"]
        login_admin(adm)
        adm.post(f"/api/admin/accounts/{me['id']}/suspend", json={"reason": "Unusual activity", "confirm": True})
        adm.post(f"/api/admin/accounts/{me['id']}/reactivate", json={"reason": "Cleared after review"})
        events = adm.get("/api/admin/events", params={"kind": "admin", "target_id": me["id"]}).json()
        actions = {e["action"]: e for e in events}
        assert {"suspend", "reactivate"} <= set(actions)
        s = actions["suspend"]
        assert s["actor"] == "Site Admin" and s["target"] == "R10" and s["reason"] == "Unusual activity"
        assert s["outcome"] == "success" and s["created_at"]
    with SessionLocal() as db:
        dump = json.dumps([[e.action, e.reason, e.detail] for e in db.query(AuditEvent).all()])
    lines = [ln.strip() for ln in resume_text.splitlines() if len(ln.strip()) > 25]
    assert lines and not any(ln in dump for ln in lines)
    assert "r10@x.com" not in dump and "arjun" not in dump.lower()


def test_flags_are_reviewable_not_automatic_bans():
    with TestClient(app) as rec, TestClient(app) as adm:
        me = login(rec, "r11@x.com", "Many Duplicates")
        job = rec.post("/api/jobs", json={"title": "Dup test", "description": JD}).json()
        f = [("files", (RESUME.name, RESUME.read_bytes()))]
        for _ in range(settings.FLAG_DUPLICATES_PER_DAY + 1):
            rec.post(f"/api/jobs/{job['id']}/resumes", files=f)
        assert rec.get("/api/jobs").status_code == 200  # still allowed to work
        login_admin(adm)
        flags = [e for e in adm.get("/api/admin/events", params={"kind": "flagged", "target_id": me["id"]}).json()]
        assert [x["action"] for x in flags] == ["duplicate_upload"] and not flags[0]["reviewed"]
        assert adm.post(f"/api/admin/events/{flags[0]['id']}/review").json()["reviewed"] is True
        row = adm.get("/api/admin/recruiters", params={"q": "r11@"}).json()[0]
        assert row["open_flags"] == 0 and row["status"] == "active"
