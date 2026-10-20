# Checks how well our ranking matches the human labels in sample_data/labels.json
# Usage (from backend/): python scripts/evaluate.py [--provider offline|gemini|groq]
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="auto|gemini|openai|groq|ollama|offline")
    ap.add_argument("--keep-db", action="store_true", help="keep the temporary database for inspection")
    return ap.parse_args()


def ndcg_at_k(labels_in_rank_order: list[int], all_labels: list[int], k: int) -> float:
    def dcg(rels):
        return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    ideal = dcg(sorted(all_labels, reverse=True))
    return dcg(labels_in_rank_order) / ideal if ideal else 0.0


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for t in range(i, j + 1):
                r[order[t]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def average_precision(rel: list[int]) -> float:
    hits, total = 0, 0.0
    for i, r in enumerate(rel, 1):
        if r >= 1:
            hits += 1
            total += hits / i
    return total / hits if hits else 0.0


def metrics(scored: list[tuple[str, float]], labels: dict[str, int]) -> dict:
    order = sorted(scored, key=lambda t: -t[1])
    rel = [labels[f] for f, _ in order]
    n_strong = sum(v == 2 for v in labels.values()) or 1
    return {
        "R-Precision": sum(r == 2 for r in rel[:n_strong]) / n_strong,
        "MAP": average_precision(rel),
        "NDCG@5": ndcg_at_k(rel, list(labels.values()), 5),
        "Spearman": spearman([s for _, s in scored], [labels[f] for f, _ in scored]),
    }


def main():
    args = parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="screener_eval_"))
    os.environ["DATA_DIR"] = str(tmp)
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
        if args.provider == "offline":
            os.environ["EMBEDDING_PROVIDER"] = "tfidf"

    from fastapi.testclient import TestClient

    from app.main import app

    labels_all = json.loads((ROOT / "sample_data" / "labels.json").read_text())
    resumes = sorted((ROOT / "sample_data" / "resumes").iterdir())
    results, per_job_rows = {}, {}

    with TestClient(app) as cl:
        from app.auth import hash_password
        from app.database import SessionLocal
        from app.models import User
        with SessionLocal() as db:
            db.add(User(name="Evaluator", email="eval@local.test", password_hash=hash_password("evaluate-123"),
                        role="recruiter", status="active"))
            db.commit()
        cl.post("/api/auth/login", json={"email": "eval@local.test", "password": "evaluate-123"})
        health = cl.get("/api/health").json()
        print(f"LLM: {health['llm_provider']}:{health['llm_model']} | embeddings: {health['embedding_backend']}")
        for jd_file, labels in labels_all.items():
            if jd_file.startswith("_"):
                continue
            jd_text = (ROOT / "sample_data" / "job_descriptions" / jd_file).read_text()
            title = jd_text.split("\n", 1)[0].strip()
            job = cl.post("/api/jobs", json={"title": title, "description": jd_text, "blind_mode": True}).json()
            files = [("files", (p.name, p.read_bytes())) for p in resumes]
            t0 = time.time()
            cl.post(f"/api/jobs/{job['id']}/resumes", files=files)
            elapsed = time.time() - t0
            cands = cl.get(f"/api/jobs/{job['id']}/candidates").json()
            done = [c for c in cands if c["status"] == "done"]
            if len(done) != len(cands):
                print("  WARNING: some resumes failed:", [c["filename"] for c in cands if c["status"] != "done"])
            sig = {
                "Keyword skill match only": [(c["filename"], c["skill_score"]) for c in done],
                "Semantic similarity only": [(c["filename"], c["semantic_score"]) for c in done],
                "Evaluator (LLM / rules) only": [(c["filename"], c["llm_score"]) for c in done],
                "Hybrid score (proposed)": [(c["filename"], c["final_score"]) for c in done],
            }
            results[title] = {name: metrics(sc, labels) for name, sc in sig.items()}
            results[title]["_seconds_total"] = round(elapsed, 1)
            details = [cl.get(f"/api/candidates/{c['id']}").json() for c in done]
            results[title]["_avg_ms_per_resume"] = round(statistics.mean(d["processing_ms"] for d in details))
            per_job_rows[title] = [
                {"rank": c["rank"], "file": c["filename"], "label": labels[c["filename"]],
                 "score": c["final_score"], "recommendation": c["recommendation"], "flags": c["flags"]}
                for c in done]
            print(f"\n{title}  ({len(done)} resumes, {elapsed:.1f}s)")
            for name, m in results[title].items():
                if not name.startswith("_"):
                    print(f"  {name:32s} " + "  ".join(f"{k}={v:.2f}" for k, v in m.items()))

        # Bias check: same resume, different name and gender, blind mode on
        base = (ROOT / "sample_data" / "resumes" / "arjun_reddy.txt").read_text()
        variants = {
            "Arjun Reddy (original)": base,
            "Priyanka Reddy (she)": base.replace("Arjun Reddy", "Priyanka Reddy").replace("arjun.reddy", "priyanka.r")
            + "\nShe is a quick learner.",
            "Mohammed Iqbal (he)": base.replace("Arjun Reddy", "Mohammed Iqbal").replace("arjun.reddy", "m.iqbal")
            + "\nHe is a quick learner.",
        }
        bjd = (ROOT / "sample_data" / "job_descriptions" / "python_backend_developer.txt").read_text()
        bias = {}
        for blind in (True, False):
            job = cl.post("/api/jobs", json={"title": "Python Backend Developer", "description": bjd,
                                             "blind_mode": blind}).json()
            files = [("files", (f"v{i}.txt", t.encode())) for i, t in enumerate(variants.values())]
            cl.post(f"/api/jobs/{job['id']}/resumes", files=files)
            cs = sorted(cl.get(f"/api/jobs/{job['id']}/candidates").json(), key=lambda c: c["filename"])
            scores = dict(zip(variants.keys(), (c["final_score"] for c in cs)))
            bias["blind" if blind else "not blind"] = {"scores": scores,
                                                       "max_difference": round(max(scores.values()) - min(scores.values()), 2)}
        results["_bias_check"] = bias
        print("\nBias check:", json.dumps(bias, indent=1))

    out = {"llm": f"{health['llm_provider']}:{health['llm_model']}", "embeddings": health["embedding_backend"],
           "results": results, "rankings": per_job_rows}
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    suffix = "" if health["llm_provider"] == "offline" else f"_{health['llm_provider']}"
    (docs / f"evaluation_results{suffix}.md").write_text(to_markdown(out))
    print(f"\nSaved docs/evaluation_results{suffix}.md")
    if not args.keep_db:
        shutil.rmtree(tmp, ignore_errors=True)


def to_markdown(out: dict) -> str:
    lines = [f"# Evaluation results\n\nLLM: `{out['llm']}`, embeddings: `{out['embeddings']}`\n"]
    for title, res in out["results"].items():
        if title.startswith("_"):
            continue
        lines.append(f"\n## {title}\n\n| Method | R-Precision | MAP | NDCG@5 | Spearman |\n|---|---|---|---|---|")
        for name, m in res.items():
            if name.startswith("_"):
                continue
            lines.append(f"| {name} | {m['R-Precision']:.2f} | {m['MAP']:.2f} | {m['NDCG@5']:.2f} | "
                         f"{m['Spearman']:.2f} |")
        lines.append(f"\nAverage processing time per resume: {res['_avg_ms_per_resume']} ms\n")
        lines.append("| Rank | Resume | Human label | Score | Recommendation |\n|---|---|---|---|---|")
        for r in out["rankings"][title]:
            lines.append(f"| {r['rank']} | {r['file']} | {r['label']} | {r['score']} | {r['recommendation']} |")
    b = out["results"].get("_bias_check", {})
    if b:
        lines.append("\n## Bias check (same resume, different name and gender)\n\n| Mode | Scores | Max difference |\n|---|---|---|")
        for mode, v in b.items():
            lines.append(f"| {mode} | " + ", ".join(f"{k}: {s}" for k, s in v["scores"].items())
                         + f" | {v['max_difference']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
