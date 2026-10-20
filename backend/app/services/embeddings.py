# Semantic similarity between a JD and a resume using embeddings (Gemini, OpenAI, Ollama, SBERT or TF-IDF)
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time

import httpx

from ..config import settings

log = logging.getLogger("screener.embeddings")
MAX_CHARS = 8000


class Embedder:
    name = "base"
    model = ""
    lo, hi = 0.0, 1.0  # calibration range for raw cosine
    vector_based = True

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}" if self.model else self.name

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class GeminiEmbedder(Embedder):
    name, lo, hi = "gemini", 0.55, 0.85

    def __init__(self):
        self.model = settings.GEMINI_EMBED_MODEL

    def embed(self, texts):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents"
        out: list[list[float]] = []
        with httpx.Client(timeout=60) as c:
            for i in range(0, len(texts), 100):
                reqs = [{"model": f"models/{self.model}", "content": {"parts": [{"text": t[:MAX_CHARS]}]},
                         "taskType": "SEMANTIC_SIMILARITY", "outputDimensionality": 768}
                        for t in texts[i:i + 100]]
                r = c.post(url, headers={"x-goog-api-key": settings.GEMINI_API_KEY}, json={"requests": reqs})
                r.raise_for_status()
                out.extend(e["values"] for e in r.json()["embeddings"])
        return out


class OpenAIEmbedder(Embedder):
    name, lo, hi = "openai", 0.20, 0.65

    def __init__(self):
        self.model = settings.OPENAI_EMBED_MODEL

    def embed(self, texts):
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{settings.OPENAI_BASE_URL.rstrip('/')}/embeddings",
                       headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                       json={"model": self.model, "input": [t[:MAX_CHARS] for t in texts]})
            r.raise_for_status()
            return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


class OllamaEmbedder(Embedder):
    name, lo, hi = "ollama", 0.40, 0.80

    def __init__(self):
        self.model = settings.OLLAMA_EMBED_MODEL

    def embed(self, texts):
        with httpx.Client(timeout=120) as c:
            r = c.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed",
                       json={"model": self.model, "input": [t[:MAX_CHARS] for t in texts]})
            r.raise_for_status()
            return r.json()["embeddings"]


class LocalEmbedder(Embedder):
    name, lo, hi = "local", 0.15, 0.70

    def __init__(self):
        from sentence_transformers import SentenceTransformer  # optional dependency
        self.model = settings.LOCAL_EMBED_MODEL
        self._m = SentenceTransformer(self.model)

    def embed(self, texts):
        return self._m.encode([t[:MAX_CHARS] for t in texts], normalize_embeddings=True).tolist()


class TfidfEmbedder(Embedder):
    """Offline fallback: cosine similarity of word counts, no model needed."""
    name, model, lo, hi = "tfidf", "sklearn", 0.08, 0.42
    vector_based = False

    def pair_similarity(self, a: str, b: str) -> float:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        from .skills import canonical_text
        vec = TfidfVectorizer(stop_words="english", sublinear_tf=True, use_idf=False,
                              ngram_range=(1, 2), token_pattern=r"(?u)\b[\w+#.]{2,}\b")
        m = vec.fit_transform([canonical_text(a), canonical_text(b)])
        return float(cosine_similarity(m[0], m[1])[0, 0])

    def rank(self, query: str, passages: list[str]) -> list[float]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        from .skills import canonical_text
        if not passages:
            return []
        vec = TfidfVectorizer(stop_words="english", sublinear_tf=True, ngram_range=(1, 2),
                              token_pattern=r"(?u)\b[\w+#.]{2,}\b")
        m = vec.fit_transform([canonical_text(query)] + [canonical_text(p) for p in passages])
        return [float(x) for x in cosine_similarity(m[0], m[1:])[0]]


_embedder: Embedder | None = None


def _build() -> Embedder:
    choice = settings.EMBEDDING_PROVIDER
    if choice == "auto":
        llm = settings.LLM_PROVIDER
        if settings.GEMINI_API_KEY and llm in ("auto", "gemini"):
            choice = "gemini"
        elif settings.OPENAI_API_KEY and llm in ("auto", "openai"):
            choice = "openai"
        elif llm == "ollama":
            choice = "ollama"
        else:
            choice = "local"
    try:
        if choice == "gemini" and settings.GEMINI_API_KEY:
            return GeminiEmbedder()
        if choice == "openai" and settings.OPENAI_API_KEY:
            return OpenAIEmbedder()
        if choice == "ollama":
            return OllamaEmbedder()
        if choice == "local":
            return LocalEmbedder()
    except Exception as exc:  # e.g. sentence-transformers not installed
        log.info("embedding backend '%s' unavailable (%s); using TF-IDF", choice, exc)
    return TfidfEmbedder()


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = _build()
        lo, hi = os.getenv("SEMANTIC_LO"), os.getenv("SEMANTIC_HI")
        if lo and hi:
            _embedder.lo, _embedder.hi = float(lo), float(hi)
        log.info("Embedding backend: %s", _embedder.label)
    return _embedder


def set_embedder(e: Embedder | None) -> None:
    global _embedder
    _embedder = e


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def calibrate(raw: float, e: Embedder) -> float:
    return max(0.0, min(1.0, (raw - e.lo) / (e.hi - e.lo)))


def _cached_embed(texts: list[str], db=None) -> list[list[float]]:
    """Embed texts, re-using vectors stored in the embedding_cache table."""
    e = get_embedder()
    keys = [hashlib.sha256(f"{e.label}|{t[:MAX_CHARS]}".encode()).hexdigest() for t in texts]
    found: dict[str, list[float]] = {}
    if db is not None:
        from ..models import EmbeddingCache
        for row in db.query(EmbeddingCache).filter(EmbeddingCache.key.in_(keys)).all():
            found[row.key] = row.vector
    todo = [(k, t) for k, t in zip(keys, texts) if k not in found]
    if todo:
        vectors = e.embed([t for _, t in todo])
        for (k, _), v in zip(todo, vectors):
            found[k] = v
        if db is not None:
            from ..models import EmbeddingCache
            for (k, _), v in zip(todo, vectors):
                db.merge(EmbeddingCache(key=k, model=e.label, vector=v))
            db.commit()
    return [found[k] for k in keys]


# If cloud embeddings fail (quota, network), use TF-IDF for 10 minutes instead of failing on every resume
EMBED_COOLDOWN_S = 600
_embed_down_until = 0.0


def _cloud_ok() -> bool:
    return time.monotonic() >= _embed_down_until


def _trip(exc: Exception) -> None:
    global _embed_down_until
    _embed_down_until = time.monotonic() + EMBED_COOLDOWN_S
    log.warning("embedding backend failed (%s); using TF-IDF for the next %d s", str(exc)[:200], EMBED_COOLDOWN_S)


def semantic_similarity(jd_text: str, resume_text: str, db=None) -> tuple[float, float, str]:
    """Return (raw cosine, calibrated 0..1, backend used) between a job description and a resume."""
    e = get_embedder()
    if not e.vector_based:
        raw = e.pair_similarity(jd_text, resume_text)
        return round(raw, 4), round(calibrate(raw, e), 4), e.label
    if _cloud_ok():
        try:
            va, vb = _cached_embed([jd_text, resume_text], db)
            raw = cosine(va, vb)
            return round(raw, 4), round(calibrate(raw, e), 4), e.label
        except Exception as exc:  # network/model/quota failure
            _trip(exc)
    tf = TfidfEmbedder()
    raw = tf.pair_similarity(jd_text, resume_text)
    return round(raw, 4), round(calibrate(raw, tf), 4), f"{tf.label} (fallback)"


def rank_passages(query: str, passages: list[str], db=None) -> list[float]:
    """Similarity of a question to each passage (for retrieval in Q&A)."""
    e = get_embedder()
    if not e.vector_based:
        return e.rank(query, passages)
    if _cloud_ok():
        try:
            vecs = _cached_embed([query, *passages], db)
            return [cosine(vecs[0], v) for v in vecs[1:]]
        except Exception as exc:
            _trip(exc)
    return TfidfEmbedder().rank(query, passages)


def chunk_text(text: str, size: int = 700) -> list[str]:
    """Split a resume into passages along line breaks; consecutive passages share one line."""
    lines = [ln.strip() for ln in re.split(r"\n+", text) if ln.strip()]
    chunks, cur = [], []
    for ln in lines:
        if cur and sum(len(x) + 1 for x in cur) + len(ln) > size:
            chunks.append("\n".join(cur))
            cur = cur[-1:] if len(cur[-1]) < size // 3 else []
        cur.append(ln)
    if cur:
        chunks.append("\n".join(cur))
    return chunks
