"""Production AI agent with Redis-backed rate limiting and budgets."""
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from utils.mock_llm import MOCK_RESPONSES, ask as llm_ask

from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget, estimate_cost, record_cost
from .rate_limiter import check_rate_limit
from .redis_client import r, redis_healthy


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
logger.propagate = False


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "lvl": "INFO",
        "event": event,
        **fields,
    }))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("startup", environment=settings.environment)
    try:
        yield
    finally:
        r.close()
        log_event("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)

# The mock uses a fixed response catalog, so the reservation can bound its output cost.
MAX_OUTPUT_TOKENS = max(
    len(answer.split()) for answers in MOCK_RESPONSES.values() for answer in answers
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    log_event(
        "request", path=request.url.path, status=response.status_code,
        ms=round((perf_counter() - started) * 1000, 2),
    )
    return response


@app.exception_handler(RedisError)
async def redis_unavailable(request: Request, exc: RedisError):
    return JSONResponse(status_code=503, content={"detail": "Redis unavailable"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(503, "Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    if not body.question.strip():
        raise HTTPException(422, "question must not be blank")

    check_rate_limit(api_key)
    input_tokens = len(body.question.split())
    reserved_cost = estimate_cost(input_tokens, MAX_OUTPUT_TOKENS)
    budget_key = check_budget(reserved_cost)
    try:
        answer = llm_ask(body.question)
    except Exception:
        record_cost(budget_key, reserved_cost, 0, 0)
        raise
    record_cost(budget_key, reserved_cost, input_tokens, len(answer.split()))
    return {"question": body.question, "answer": answer}
