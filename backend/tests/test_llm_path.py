"""Exercise the LLM code path with a fake model (no network, no API key)."""
import asyncio
import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.llm import LLMClient, extract_json, set_llm
from app.services.llm import providers
from conftest import SAMPLES, login


class FakeLLM(LLMClient):
    name, model = "fake", "test-1"

    def __init__(self):
        self.calls = 0

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        self.calls += 1
        if "Turn a job description" in system:
            return json.dumps({"role_title": "Backend Dev", "seniority": "Mid", "min_years_experience": "2",
                               "must_have_skills": ["python", "Fast API or django", "postgres"],
                               "nice_to_have_skills": "docker, AWS", "education": "B.Tech",
                               "responsibilities": ["Build APIs"], "summary": "x"})
        if "search the resumes" in system:
            return '{"answer": "C1 has used Kafka.", "cited": ["C1"]}'
        if self.calls == 2:  # first evaluation reply is broken -> retry path
            return "Sure! Here is the JSON: {not valid"
        return ("```json\n" + json.dumps({
            "overall_score": 81, "skills_score": "85", "experience_score": 80, "education_score": 90,
            "projects_score": 70, "recommendation": "strong fit", "summary": "Solid backend engineer.",
            "strengths": ["FastAPI microservices"], "gaps": ["No Kafka"], "red_flags": [],
            "interview_questions": ["Explain your caching strategy."]}) + "\n```")


def test_extract_json_handles_chatter_and_fences():
    assert extract_json('Here you go: {"a": {"b": "}"}} thanks')["a"]["b"] == "}"
    assert extract_json('```json\n{"x": 1}\n```')["x"] == 1


def test_llm_pipeline_with_cache_and_retry():
    fake = FakeLLM()
    set_llm(fake)
    try:
        with TestClient(app) as cl:
            login(cl)
            jd = (SAMPLES / "job_descriptions" / "python_backend_developer.txt").read_text()
            job = cl.post("/api/jobs", json={"title": "Backend", "description": jd}).json()
            assert job["analysed_by"] == "fake:test-1"
            assert job["requirements"]["must_have_skills"] == ["Python", "FastAPI or Django", "PostgreSQL"]
            assert job["requirements"]["nice_to_have_skills"] == ["Docker", "AWS"]

            f = SAMPLES / "resumes" / "aarav_sharma.pdf"
            cl.post(f"/api/jobs/{job['id']}/resumes", files=[("files", (f.name, f.read_bytes()))])
            c = cl.get(f"/api/jobs/{job['id']}/candidates").json()[0]
            assert c["status"] == "done" and c["llm_score"] == 0.81
            detail = cl.get(f"/api/candidates/{c['id']}").json()
            assert detail["evaluation"]["recommendation"] == "Strong Fit"
            assert detail["evaluated_by"] == "fake:test-1"
            tokens = detail["evaluation"]["tokens"]
            assert tokens["calls"] == 2 and tokens["total"] > 0 and not tokens["cached"]  # 1 bad reply + 1 retry
            calls = fake.calls

            # same resume, same job -> served from cache, no new model call
            cl.post(f"/api/candidates/{c['id']}/reprocess")
            again = cl.get(f"/api/candidates/{c['id']}").json()
            assert again["evaluated_by"].endswith("(cached)") and fake.calls == calls
            assert again["evaluation"]["tokens"] == {"cached": True, "saved": tokens["total"]}
            stats = cl.get(f"/api/jobs/{job['id']}").json()["stats"]["tokens"]
            assert stats["cached_resumes"] == 1 and stats["saved"] == tokens["total"]

            ans = cl.post(f"/api/jobs/{job['id']}/ask", json={"question": "Who knows Kafka?"}).json()
            assert ans["answer"] == "C1 has used Kafka." and ans["answered_by"] == "fake:test-1"
            assert ans["tokens"] > 0
    finally:
        set_llm(None)


def test_prompt_compaction_keeps_content():
    from app.services.llm.prompts import compact, to_json
    text = "Page 1\n\n  John   Doe  \nPython,   SQL\n\nPage 1\nPython,   SQL\n"
    assert compact(text, 1000) == "Page 1\nJohn Doe\nPython, SQL"
    assert to_json({"a": [], "b": "", "c": ["x"]}) == '{"c":["x"]}'


def test_provider_token_counts_are_recorded(monkeypatch):
    from app.services.llm.base import start_usage

    async def fake_post(url, *, headers, payload, attempts=4, patient=True):
        assert payload["max_completion_tokens"] > 0 and payload["reasoning_effort"] == "low"
        return {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
    monkeypatch.setattr(providers, "_post_json", fake_post)
    client = providers.OpenAICompatibleClient("groq", "k", "m", "https://x")

    async def run():
        usage = start_usage()
        await client.complete("sys", "user")
        return usage
    assert asyncio.run(run()) == {"input": 120, "output": 30, "total": 150, "calls": 1}


def test_unsupported_setting_is_dropped(monkeypatch):
    from app.services.llm import LLMError
    sent = []

    async def fake_post(url, *, headers, payload, attempts=4, patient=True):
        sent.append(dict(payload))
        if "reasoning_effort" in payload:
            raise LLMError("HTTP 400: `reasoning_effort` is not supported with this model")
        return {"choices": [{"message": {"content": "{}"}}]}
    monkeypatch.setattr(providers, "_post_json", fake_post)
    client = providers.OpenAICompatibleClient("groq", "k", "m", "https://x")
    asyncio.run(client.complete("sys", "user"))
    asyncio.run(client.complete("sys", "user"))
    assert len(sent) == 3 and "reasoning_effort" not in sent[2]  # remembered after the first failure


def test_gemini_response_parsing(monkeypatch):
    async def fake_post(url, *, headers, payload, attempts=4, patient=True):
        assert url.endswith("/models/gemini-x:generateContent")
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert headers["x-goog-api-key"] == "k"
        return {"candidates": [{"content": {"parts": [{"text": '{"ok": '}, {"text": "true}"}]}}]}
    monkeypatch.setattr(providers, "_post_json", fake_post)
    out = asyncio.run(providers.GeminiClient("k", "gemini-x").complete("sys", "user"))
    assert json.loads(out) == {"ok": True}


class FailingLLM(FakeLLM):
    name, model = "broken", "x"

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        from app.services.llm import LLMError
        raise LLMError("quota exhausted")


def test_backup_provider_takes_over():
    from app.schemas import QAAnswer
    from app.services.llm import FallbackClient
    client = FallbackClient([FailingLLM(), FakeLLM()])

    async def run():
        res = await client.complete_json("search the resumes", "q", QAAnswer)
        return res, client.last_label
    res, used = asyncio.run(run())
    assert res.answer == "C1 has used Kafka." and used == "fake:test-1"
    assert client.chain == ["broken:x", "fake:test-1"]


class QuotaLLM(FakeLLM):
    """First provider whose daily quota is used up."""
    name, model = "gemini", "quota"

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        from app.services.llm import RateLimitError
        self.calls += 1
        raise RateLimitError("daily quota exhausted", retry_after=3600)


class SlowLLM(FakeLLM):
    def __init__(self, name):
        super().__init__()
        self.name = name

    async def complete(self, system, user, *, json_mode=True, temperature=None):
        await asyncio.sleep(0.05 if self.name == "slow" else 0.0)
        return '{"answer": "%s", "cited": []}' % self.name


def test_exhausted_provider_is_skipped_until_cooldown_ends():
    from app.schemas import QAAnswer
    from app.services.llm import FallbackClient
    quota, backup = QuotaLLM(), FakeLLM()
    client = FallbackClient([quota, backup])

    async def run():
        for _ in range(3):
            await client.complete_json("search the resumes", "q", QAAnswer)
    asyncio.run(run())
    assert quota.calls == 1  # tried once, then cooled down for an hour
    assert backup.calls == 3
    assert client.status()[0]["cooling_down_s"] > 3000


def test_parallel_calls_report_their_own_provider():
    from app.schemas import QAAnswer
    from app.services.llm import FallbackClient
    from app.services.llm.base import LLMError

    class Flaky(SlowLLM):
        async def complete(self, system, user, *, json_mode=True, temperature=None):
            if "fail" in user:
                raise LLMError("boom")
            return await super().complete(system, user)
    client = FallbackClient([Flaky("slow"), SlowLLM("fast")])

    async def one(prompt):
        await client.complete_json("x", prompt, QAAnswer)
        return client.last_label
    async def run():
        return await asyncio.gather(one("ok"), one("fail please"))
    first, second = asyncio.run(run())
    assert first == "slow:test-1" and second == "fast:test-1"


def test_build_client_adds_backups(monkeypatch):
    from app.services.llm import FallbackClient, build_client
    monkeypatch.setattr(providers.settings, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(providers.settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(providers.settings, "OPENAI_API_KEY", "")
    c = build_client("auto", "auto")
    assert isinstance(c, FallbackClient) and [x.name for x in c.clients] == ["gemini", "groq"]
    assert build_client("auto", "none").name == "gemini"
