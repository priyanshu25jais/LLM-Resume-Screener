from fastapi.testclient import TestClient

from app.main import app
from conftest import SAMPLES, login

JD = (SAMPLES / "job_descriptions" / "python_backend_developer.txt").read_text()


def test_full_screening_flow():
    with TestClient(app) as cl:
        assert cl.get("/api/health").json()["status"] == "ok"
        login(cl)
        job = cl.post("/api/jobs", json={"title": "Python Backend Developer", "description": JD}).json()
        assert "FastAPI or Django" in job["requirements"]["must_have_skills"]

        files = [("files", (p.name, p.read_bytes())) for p in sorted((SAMPLES / "resumes").iterdir())]
        files.append(("files", ("notes.exe", b"binary")))
        r = cl.post(f"/api/jobs/{job['id']}/resumes", files=files).json()
        assert len(r["added"]) == 15 and r["skipped"][0]["filename"] == "notes.exe"

        dup = cl.post(f"/api/jobs/{job['id']}/resumes", files=files[:1]).json()
        assert dup["skipped"][0]["reason"].startswith("duplicate")

        cands = cl.get(f"/api/jobs/{job['id']}/candidates").json()
        assert all(c["status"] == "done" for c in cands)
        assert cands[0]["rank"] == 1 and cands[0]["final_score"] >= cands[-1]["final_score"]
        assert cands[0]["display_name"].startswith("Candidate")  # blind mode hides names

        top = cl.get(f"/api/candidates/{cands[0]['id']}").json()
        assert top["identity_hidden"] and top["email"] == ""
        assert top["evaluation"]["interview_questions"]
        revealed = cl.get(f"/api/candidates/{cands[0]['id']}?reveal=true").json()
        assert "@" in revealed["email"]

        injected = next(c for c in cands if c["filename"] == "tanya_malhotra.txt")
        assert injected["recommendation"] == "Not a Fit" and injected["flags"]

        upd = cl.patch(f"/api/candidates/{cands[0]['id']}", json={"decision": "shortlisted", "notes": "Call"}).json()
        assert upd["decision"] == "shortlisted"

        new = cl.patch(f"/api/jobs/{job['id']}", json={"weights": {"llm": 0, "skills": 1, "semantic": 0,
                                                                     "experience": 0}}).json()
        assert new["weights"]["skills"] == 1.0
        after = cl.get(f"/api/jobs/{job['id']}/candidates").json()
        assert abs(after[0]["final_score"] - after[0]["skill_score"] * 100) < 0.2

        ans = cl.post(f"/api/jobs/{job['id']}/ask", json={"question": "Who has worked with Kafka?"}).json()
        assert ans["sources"] and "Kafka" in ans["answer"]

        csv = cl.get(f"/api/jobs/{job['id']}/export.csv")
        assert csv.status_code == 200 and csv.text.count("\n") >= 16

        assert cl.delete(f"/api/jobs/{job['id']}").status_code == 204
        assert cl.get(f"/api/jobs/{job['id']}").status_code == 404
