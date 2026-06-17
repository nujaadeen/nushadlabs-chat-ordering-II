"""Pydantic schemas.

Two groups:
  * LLM extraction schema (Intent / Item / Extraction) — the ONLY thing the LLM fills.
  * API request/response schema — what /process accepts and returns.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# LLM extraction schema (produced by the single LLM call)                     #
# --------------------------------------------------------------------------- #
class Intent(str, Enum):
    ORDER = "ORDER"
    ADD_TO_CART = "ADD_TO_CART"
    CHECKOUT = "CHECKOUT"
    UNKNOWN = "UNKNOWN"


class Item(BaseModel):
    raw_name: str = Field(..., description="The item exactly as the user typed it.")
    normalized_name: str = Field(
        ...,
        description=(
            "Cleaned item name: fix typos and expand brand/synonym terms using common "
            "knowledge (e.g. 'peperonio' -> 'pepperoni', 'coke' -> 'Coca-Cola')."
        ),
    )
    quantity: int = Field(default=1, description="How many of this item. Default 1.")
    modifiers: List[str] = Field(
        default_factory=list,
        description="Extra requests, e.g. 'extra cheese', 'no onions', 'large'.",
    )
    # Phase-2 hook: unused in phase 1, kept so the schema is forward-compatible.
    references_previous: bool = Field(
        default=False,
        description="Phase-2 hook. Whether the item refers to a previously mentioned item. Always false for now.",
    )


class Extraction(BaseModel):
    intent: Intent
    items: List[Item] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# API request / response schema                                               #
# --------------------------------------------------------------------------- #
class ProcessRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # Phase-1: accepted but ignored.


class Candidate(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    price: Optional[float] = None
    score: float


class ItemMatch(BaseModel):
    raw_name: str
    normalized_name: str
    quantity: int
    modifiers: List[str] = Field(default_factory=list)
    candidates: List[Candidate] = Field(default_factory=list)
    selected: Optional[Candidate] = None
    ambiguous: bool = True


class ProcessResponse(BaseModel):
    intent: Intent
    needs_clarification: bool = False
    items: List[ItemMatch] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    message: Optional[str] = None
