"""Conservative factual guards shared by ingest and publication deduplication."""
import re


def fact_tokens(text: str) -> set[str]:
    text = text.lower().replace("ё", "е")
    # Preserve ordered scores: 1:0 and 0:1 are different facts.
    scores = set(re.findall(r"\b\d+\s*:\s*\d+\b", text))
    numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))
    negatives = set(re.findall(r"\b(?:не|нет|без|not|no|without)\b", text))
    return {re.sub(r"\s+", "", score) for score in scores} | numbers | negatives


def facts_conflict(left: str, right: str) -> bool:
    # Missing or additional facts deserve retention, not automatic suppression.
    return fact_tokens(left) != fact_tokens(right)
