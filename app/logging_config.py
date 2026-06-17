"""Centralised logging setup.

Every /process request emits the two MANDATORY checkpoints through this logger:
  1. INTENT EXTRACTED ...   (right after the single LLM call)
  2. MATCHED '<name>' -> [...] | selected=... | ambiguous=...   (per item)
plus the routing action lines (CALLING CART API / checkout).

Timestamps and log levels are kept on every line per the spec.
"""
import logging
import os
import sys

from dotenv import load_dotenv

# Load .env as early as possible so every module that reads os.getenv() sees it.
load_dotenv()

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotent root-logger configuration at INFO level to stdout."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers when uvicorn --reload re-imports the module.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    else:
        root.handlers = [handler]

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
