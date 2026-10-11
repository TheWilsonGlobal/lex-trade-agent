"""Fuzzy string matching and normalization utilities for Compliance MCP."""

from __future__ import annotations

import difflib
import re


def normalize_string(text: str) -> str:
    """Normalize text for consistent comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return " ".join(tokens)


def calculate_fuzzy_score(query: str, target: str) -> float:
    """Calculate normalized token-aware similarity score between 0 and 100."""
    q_norm = normalize_string(query)
    t_norm = normalize_string(target)

    # Direct match check
    if q_norm == t_norm:
        return 100.0

    seq_ratio = difflib.SequenceMatcher(None, q_norm, t_norm).ratio() * 100.0

    # Token overlap check
    q_tokens = set(q_norm.split())
    t_tokens = set(t_norm.split())
    if q_tokens and t_tokens:
        overlap = len(q_tokens.intersection(t_tokens))
        jaccard = (overlap / len(q_tokens.union(t_tokens))) * 100.0
        combined_score = (seq_ratio * 0.6) + (jaccard * 0.4)
    else:
        combined_score = seq_ratio

    # Substring bonus
    if q_norm in t_norm or t_norm in q_norm:
        combined_score = max(combined_score, 88.0)

    return round(min(100.0, combined_score), 2)
