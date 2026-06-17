"""The single LLM call: free text -> Extraction (intent + items).

LOCAL OLLAMA only, via its OpenAI-compatible endpoint, wrapped by `instructor`
in JSON mode with validation retries. Exactly ONE LLM call per request and the
LLM never sees or queries the database.
"""
import os
from functools import lru_cache

import instructor
from openai import OpenAI

from app.logging_config import get_logger
from app.schemas import Extraction

logger = get_logger("app.extractor")

SYSTEM_PROMPT = """You are an order-intent extraction engine for a food ordering app.
You receive ONE user message and return a structured JSON object. You do NOT have
access to any product catalog or database — never invent product IDs or prices.

Your job:
1. Classify the intent as exactly one of:
   - ORDER         : user wants to place/order item(s) now.
   - ADD_TO_CART   : user wants to add item(s) to their cart.
   - CHECKOUT      : user wants to check out / pay / complete the order.
   - UNKNOWN       : the message is unrelated or you cannot tell.
2. Extract EVERY item the user mentions. For each item provide:
   - raw_name: the item exactly as the user wrote it.
   - normalized_name: the cleaned item name. FIX SPELLING/TYPOS and EXPAND brand or
     synonym terms using common knowledge.
   - quantity: integer count (default 1 if unspecified).
   - modifiers: list of extra requests like "extra cheese", "no onions", "large".
   - references_previous: always false.

Normalization examples (apply this kind of reasoning):
- "peperonio" -> "pepperoni"
- "peperonio cheese pizza" -> "pepperoni cheese pizza"
- "coke" -> "Coca-Cola"
- "coke zero" -> "Coke Zero"
- "sprite" -> "Sprite"
- "water" -> "Bottled Water"

Few-shot examples:

User: "i want to order a pepperoni pizza"
JSON: {"intent":"ORDER","items":[{"raw_name":"a pepperoni pizza","normalized_name":"pepperoni pizza","quantity":1,"modifiers":[],"references_previous":false}]}

User: "add a cheese pizza to my cart"
JSON: {"intent":"ADD_TO_CART","items":[{"raw_name":"a cheese pizza","normalized_name":"cheese pizza","quantity":1,"modifiers":[],"references_previous":false}]}

User: "add peperonio cheese pizza and a coke to my cart"
JSON: {"intent":"ADD_TO_CART","items":[{"raw_name":"peperonio cheese pizza","normalized_name":"pepperoni cheese pizza","quantity":1,"modifiers":[],"references_previous":false},{"raw_name":"a coke","normalized_name":"Coca-Cola","quantity":1,"modifiers":[],"references_previous":false}]}

User: "checkout please"
JSON: {"intent":"CHECKOUT","items":[]}

User: "add a pizza to my cart"
JSON: {"intent":"ADD_TO_CART","items":[{"raw_name":"a pizza","normalized_name":"pizza","quantity":1,"modifiers":[],"references_previous":false}]}

Return ONLY the structured object.
"""


@lru_cache(maxsize=1)
def get_client():
    """instructor-wrapped OpenAI client pointed at the local Ollama endpoint."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    openai_client = OpenAI(base_url=base_url, api_key="ollama")
    # JSON mode is the reliable path across Ollama models.
    return instructor.from_openai(openai_client, mode=instructor.Mode.JSON)


def extract(message: str) -> Extraction:
    """Run the one and only LLM call and return a validated Extraction."""
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    client = get_client()
    extraction: Extraction = client.chat.completions.create(
        model=model,
        response_model=Extraction,
        max_retries=2,  # instructor re-prompts on Pydantic validation failure
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    )

    # MANDATORY checkpoint #1: parsed intent + every extracted item.
    items_repr = ", ".join(
        "{{raw='{raw}', norm='{norm}', qty={qty}}}".format(
            raw=it.raw_name, norm=it.normalized_name, qty=it.quantity
        )
        for it in extraction.items
    )
    logger.info(
        "INTENT EXTRACTED: %s | items=[%s]", extraction.intent.value, items_repr
    )
    return extraction


def check_ollama() -> bool:
    """Lightweight reachability probe for /health (lists local models)."""
    try:
        models = get_client().models.list()
        return models is not None
    except Exception:
        return False
