# Stateless Intent Extraction + Product Matching Service (Phase 1)

A stateless FastAPI service that turns free text like
`"add peperonio cheese pizza and a coke to my cart"` into:

1. an **intent** (`ORDER` / `ADD_TO_CART` / `CHECKOUT` / `UNKNOWN`),
2. structured **items** (raw name, normalized name, quantity, modifiers),
3. **deterministic product matches** from MySQL via `rapidfuzz`,
4. an **intent-routed JSON response**.

## Design guarantees

- **Exactly one LLM call per request** — the extraction call. The LLM runs on a
  **local Ollama** model via its OpenAI-compatible endpoint, wrapped by
  [`instructor`](https://python.useinstructor.com/) in JSON mode with validation retries.
- **The LLM never touches the database.** It only produces a cleaned search query
  (`normalized_name`). All product matching is deterministic Python
  (`rapidfuzz.token_set_ratio`) — no embeddings, no vector DB, no SQL fuzzy search.
  This prevents hallucinated products.
- **Stateless** in phase 1: `session_id` is accepted but ignored. The schema carries
  phase-2 hooks (`Item.references_previous`) that are unused for now.
- No LangChain / CrewAI / Agno / MCP / agentic loops.

## Project layout

```
docker-compose.yml        MySQL 8.0 only (app runs on the host)
app/main.py               FastAPI app: POST /process, GET /health
app/schemas.py            Pydantic: Intent/Item/Extraction + API request/response
app/extractor.py          The single LLM call (Ollama + instructor, JSON mode)
app/matcher.py            rapidfuzz matching (deterministic)
app/services.py           Intent routing
app/db.py                 SQLAlchemy 2.0 + PyMySQL queries
app/logging_config.py     INFO-level console logging
scripts/seed.py           Idempotent product seeder
requirements.txt
.env.example
postman_collection.json
```

## Mandatory log checkpoints (visible on every `/process` call)

```
... | INFO  | app.extractor | INTENT EXTRACTED: ADD_TO_CART | items=[{raw='peperonio cheese pizza', norm='pepperoni cheese pizza', qty=1}, {raw='a coke', norm='Coca-Cola', qty=1}]
... | INFO  | app.matcher   | MATCHED 'pepperoni cheese pizza' -> [Pepperoni Cheese Pizza (id=1, score=100.0), Cheese Pizza (id=2, score=82.0)] | selected=Pepperoni Cheese Pizza | ambiguous=False
... | INFO  | app.matcher   | MATCHED 'Coca-Cola' -> [Coca-Cola 330ml (id=8, score=90.0), Coke Zero 330ml (id=9, score=72.0)] | selected=Coca-Cola 330ml | ambiguous=False
... | INFO  | app.services  | CALLING CART API: product_id=1 qty=1
... | INFO  | app.services  | CALLING CART API: product_id=8 qty=1
```

---

## Step-by-step local run

### 1. Start MySQL and wait for the healthcheck

```bash
docker compose up -d
# Wait until the container reports (healthy):
docker compose ps
# or watch the health status directly:
docker inspect --format '{{.State.Health.Status}}' ordering-mysql
```

Proceed once the status is `healthy`.

### 2. Install Ollama and pull the model

Install Ollama (https://ollama.com/download), then:

```bash
ollama pull llama3.1:8b
# More reliable for structured output if you hit JSON issues:
# ollama pull qwen2.5:7b   then set OLLAMA_MODEL=qwen2.5:7b in .env
```

Make sure the Ollama server is running (`ollama serve`, or the desktop app).

### 3. Install Python deps and configure env

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
cp .env.example .env          # defaults already match docker-compose.yml
```

### 4. Seed the database

```bash
python scripts/seed.py
```

Idempotent — safe to re-run.

### 5. Start the API and import Postman

```bash
uvicorn app.main:app --reload
```

Then import `postman_collection.json` into Postman. The collection base URL is
`http://localhost:8000`.

### 6. curl equivalents

```bash
# Health (Ollama + MySQL)
curl -s http://localhost:8000/health | jq

# 1. ORDER
curl -s -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"message":"i want to order a pepperoni pizza"}' | jq

# 2. ADD_TO_CART single
curl -s -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"message":"add a cheese pizza to my cart"}' | jq

# 3. ADD_TO_CART multi (2 items -> 2 CALLING CART API log lines)
curl -s -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"message":"add peperonio cheese pizza and a coke to my cart"}' | jq

# 4. CHECKOUT
curl -s -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"message":"checkout please"}' | jq

# 5. Ambiguous
curl -s -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"message":"add a pizza to my cart"}' | jq
```

### 7. Teardown

```bash
docker compose down      # stop MySQL, keep data
docker compose down -v   # stop MySQL and drop the mysql_data volume
```

## Configuration (`.env`)

| Variable          | Default                       | Purpose                              |
|-------------------|-------------------------------|--------------------------------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1`   | Ollama OpenAI-compatible endpoint    |
| `OLLAMA_MODEL`    | `llama3.1:8b`                 | Extraction model                     |
| `MYSQL_HOST`      | `localhost`                   | DB host                              |
| `MYSQL_PORT`      | `3306`                        | DB port                              |
| `MYSQL_USER`      | `root`                        | DB user                              |
| `MYSQL_PASSWORD`  | `rootpass`                    | DB password                          |
| `MYSQL_DB`        | `ordering`                    | DB name                              |
| `MATCH_THRESHOLD` | `75`                          | Min fuzzy score for a confident match|
| `TOP_K`           | `5`                           | Candidates returned per item         |

## API

### `POST /process`
```json
{ "message": "add a coke to my cart", "session_id": "optional-ignored" }
```
Returns `intent`, `items` (each with `candidates` + `selected` + `ambiguous`),
`actions`, and an optional `message`.

### `GET /health`
Returns `{ "status": "...", "ollama": "ok|unreachable", "mysql": "ok|unreachable" }`.
