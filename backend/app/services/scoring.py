"""Hybrid scoring: combine the four signals into a 0-100 score and a recommendation band."""
from __future__ import annotations

DEFAULT_WEIGHTS = {"llm": 0.45, "skills": 0.25, "semantic": 0.20, "experience": 0.10}

BANDS = [(75, "Strong Fit"), (60, "Good Fit"), (45, "Consider"), (0, "Not a Fit")]


def normalize_weights(w: dict | None) -> dict:
    w = {k: max(0.0, float((w or {}).get(k, DEFAULT_WEIGHTS[k]))) for k in DEFAULT_WEIGHTS}
    total = sum(w.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(v / total, 4) for k, v in w.items()}


def experience_fit(years: float, required: float) -> float:
    """X = min(1, years / required). No requirement -> 1.0 (freshers are not penalised)."""
    if not required or required <= 0:
        return 1.0
    return round(max(0.0, min(1.0, (years or 0) / required)), 4)


def final_score(signals: dict, weights: dict) -> float:
    """S = 100 * (wL*L + wK*K + wE*E + wX*X); every signal is in [0, 1]."""
    w = normalize_weights(weights)
    s = (w["llm"] * signals["llm"] + w["skills"] * signals["skills"]
         + w["semantic"] * signals["semantic"] + w["experience"] * signals["experience"])
    return round(100 * s, 1)


def recommendation(score: float, must_coverage: float = 1.0) -> tuple[str, list[str]]:
    # Candidates missing most must-have skills are capped at "Consider"
    band = next(label for cutoff, label in BANDS if score >= cutoff)
    flags = []
    if must_coverage < 0.4 and band in ("Strong Fit", "Good Fit"):
        band = "Consider"
        flags.append("Capped at 'Consider': fewer than 40% of must-have skills found")
    return band, flags
