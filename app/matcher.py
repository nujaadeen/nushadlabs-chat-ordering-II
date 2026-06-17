"""Deterministic product matching with rapidfuzz.

No embeddings, no vector DB, no SQL LIKE/FULLTEXT. The LLM only supplies
`normalized_name`; everything here is plain Python scoring so a product can
never be hallucinated — candidates always come from the DB list.
"""
import os
import re
from typing import List

from rapidfuzz import fuzz, utils

from app.db import Product
from app.logging_config import get_logger
from app.schemas import Candidate, Item, ItemMatch

logger = get_logger("app.matcher")

# How far ahead the best candidate must be from the 2nd to count as "clearly leading".
LEAD_MARGIN = 10.0

# The category/description fallback is discounted so a mere description mention
# (e.g. Coke Zero's description contains "Coca-Cola") can never TIE a real name
# match. Name similarity always dominates; context only rescues weak names.
FALLBACK_WEIGHT = 0.85


def _top_k() -> int:
    return int(os.getenv("TOP_K", "5"))


def _threshold() -> float:
    return float(os.getenv("MATCH_THRESHOLD", "75"))


# token_set_ratio stays dominant so a subset query ('pepperoni pizza') still
# matches its superset product strongly; token_sort_ratio is mixed in lightly as a
# tie-breaker so exact names ('Cheese Pizza') beat superset names
# ('Pepperoni Cheese Pizza') when a query matches both at 100.
SET_WEIGHT = 0.7
SORT_WEIGHT = 0.3

# Filler/connective words that may sneak into a query but carry no product
# meaning. rapidfuzz's default_process only lowercases + strips punctuation; it
# does NOT drop stopwords, so we remove these ourselves BEFORE scoring.
_STOPWORDS = {
    "a", "an", "the", "some", "of", "with", "without", "and", "or",
    "to", "my", "me", "please", "i", "want", "order", "add", "get", "for", "no",
}


def _prepare_query(item: Item) -> str:
    """Build the search string for one item.

    Order matters: strip the item's own modifiers and filler stopwords FIRST
    (default_process won't do this), then scoring applies default_process to
    handle case/punctuation uniformly on both sides. Manual lowercasing is no
    longer needed here — default_process owns case normalization.
    """
    text = item.normalized_name or item.raw_name
    # Remove any modifier phrases the LLM already split out (e.g. 'without olive').
    for mod in item.modifiers:
        if mod.strip():
            text = re.sub(re.escape(mod), " ", text, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"\s+", text) if t and t.lower() not in _STOPWORDS]
    return " ".join(tokens) if tokens else (item.normalized_name or item.raw_name)


def _name_similarity(query: str, name: str) -> float:
    # processor=default_process normalizes BOTH the query and the product name
    # (lowercase + strip punctuation) so an exact match is case-insensitively 100.
    return (
        SET_WEIGHT
        * fuzz.token_set_ratio(query, name, processor=utils.default_process)
        + SORT_WEIGHT
        * fuzz.token_sort_ratio(query, name, processor=utils.default_process)
    )


def _score(query: str, product: Product) -> float:
    """Score query against the product name, with category/description as fallback.

    Primary signal is the name similarity. We also score against
    'name + category + description' (discounted) and take the max, so a query that
    matches a category ('drink', 'pizza') or a description word still surfaces the
    product without ever beating a true name match.
    """
    name_score = _name_similarity(query, product.name)
    haystack = " ".join(
        p for p in [product.name, product.category or "", product.description or ""] if p
    )
    fallback_score = _name_similarity(query, haystack) * FALLBACK_WEIGHT
    return max(name_score, fallback_score)


def match_item(item: Item, products: List[Product]) -> ItemMatch:
    """Score one extracted item against all products and decide confidence."""
    query = _prepare_query(item)

    scored = [
        Candidate(
            id=p.id,
            name=p.name,
            category=p.category,
            price=float(p.price) if p.price is not None else None,
            score=round(_score(query, p), 1),
        )
        for p in products
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    candidates = scored[: _top_k()]

    selected = None
    ambiguous = True
    if candidates:
        best = candidates[0]
        second = candidates[1].score if len(candidates) > 1 else 0.0
        leads = (best.score - second) >= LEAD_MARGIN or len(candidates) == 1
        if best.score >= _threshold() and leads:
            selected = best
            ambiguous = False

    match = ItemMatch(
        raw_name=item.raw_name,
        normalized_name=item.normalized_name,
        quantity=item.quantity,
        modifiers=item.modifiers,
        candidates=candidates,
        selected=selected,
        ambiguous=ambiguous,
    )

    # MANDATORY checkpoint #2: candidate list + selection, per item.
    cand_str = ", ".join(
        f"{c.name} (id={c.id}, score={c.score})" for c in candidates
    ) or "<no candidates>"
    sel_str = selected.name if selected else "None"
    logger.info(
        "MATCHED '%s' -> [%s] | selected=%s | ambiguous=%s",
        query,
        cand_str,
        sel_str,
        ambiguous,
    )
    return match
