"""FastAPI entrypoint.

POST /process  -> intent + extracted items + per-item matches + actions.
GET  /health   -> Ollama and MySQL reachability.
"""
from fastapi import FastAPI

from app.db import check_mysql
from app.extractor import check_ollama
from app.logging_config import get_logger
from app.schemas import ProcessRequest, ProcessResponse
from app.services import process_message

logger = get_logger("app.main")

app = FastAPI(title="Stateless Intent + Product Matching Service", version="1.0.0")


@app.post("/process", response_model=ProcessResponse)
def process(req: ProcessRequest) -> ProcessResponse:
    # session_id is accepted but intentionally ignored in phase 1 (stateless).
    logger.info("REQUEST /process message=%r", req.message)
    return process_message(req.message)


@app.get("/health")
def health() -> dict:
    ollama_ok = check_ollama()
    mysql_ok = check_mysql()
    status = "ok" if (ollama_ok and mysql_ok) else "degraded"
    return {
        "status": status,
        "ollama": "ok" if ollama_ok else "unreachable",
        "mysql": "ok" if mysql_ok else "unreachable",
    }
