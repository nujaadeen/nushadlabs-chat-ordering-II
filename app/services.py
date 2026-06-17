"""Routing: take an Extraction, match items, and act per intent.

Cart and checkout steps only LOG (placeholders for the real APIs). The only
network call in the whole flow is the local Ollama extraction in extractor.py.
"""
from typing import List

from app.db import fetch_available_products
from app.extractor import extract
from app.logging_config import get_logger
from app.matcher import match_item
from app.schemas import (
    Extraction,
    Intent,
    ItemMatch,
    ProcessResponse,
)

logger = get_logger("app.services")


def _match_all(extraction: Extraction) -> List[ItemMatch]:
    products = fetch_available_products()
    return [match_item(item, products) for item in extraction.items]


def process_message(message: str) -> ProcessResponse:
    extraction = extract(message)  # the single LLM call (+ checkpoint #1)

    # No DB calls for clarification / unknown.
    if extraction.intent == Intent.UNKNOWN or extraction.needs_clarification:
        logger.info("ROUTING: clarification required (no DB calls)")
        return ProcessResponse(
            intent=extraction.intent,
            needs_clarification=True,
            items=[],
            actions=[],
            message="Could you clarify what you'd like to order?",
        )

    if extraction.intent == Intent.CHECKOUT:
        action = "checkout - api not ready"
        logger.info(action)
        return ProcessResponse(
            intent=extraction.intent,
            items=[],
            actions=[action],
            message="Checkout requested. checkout - api not ready",
        )

    # ORDER / ADD_TO_CART both need matching (+ checkpoint #2 per item).
    matches = _match_all(extraction)
    actions: List[str] = []

    if extraction.intent == Intent.ADD_TO_CART:
        for m in matches:
            if m.selected is not None:
                line = (
                    f"CALLING CART API: product_id={m.selected.id} qty={m.quantity}"
                )
                logger.info(line)
                actions.append(line)
            else:
                note = (
                    f"SKIPPED add for '{m.normalized_name}': ambiguous, "
                    f"{len(m.candidates)} candidates returned"
                )
                logger.info(note)
                actions.append(note)
        return ProcessResponse(
            intent=extraction.intent,
            needs_clarification=any(m.ambiguous for m in matches),
            items=matches,
            actions=actions,
        )

    # ORDER: just return matched product(s) / candidate lists.
    logger.info("ROUTING: ORDER -> returning %d matched item(s)", len(matches))
    return ProcessResponse(
        intent=extraction.intent,
        needs_clarification=any(m.ambiguous for m in matches),
        items=matches,
        actions=["ORDER matched; returning products/candidates"],
    )
