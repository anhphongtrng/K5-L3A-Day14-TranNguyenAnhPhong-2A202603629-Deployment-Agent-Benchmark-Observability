"""Reserve and settle the daily LLM budget in shared Redis."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .config import settings
from .redis_client import r


# Integer nanodollars avoid rounding the cumulative token cost.
INPUT_COST = 150
OUTPUT_COST = 600
NANODOLLARS_PER_USD = 1_000_000_000

reserve = r.register_script("""
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(ARGV[1])
if used + cost > tonumber(ARGV[2]) then return 0 end
redis.call('INCRBY', KEYS[1], cost)
redis.call('EXPIREAT', KEYS[1], ARGV[3])
return 1
""")


def estimate_cost(input_tokens: int, output_tokens: int) -> int:
    return input_tokens * INPUT_COST + output_tokens * OUTPUT_COST


def check_budget(estimated_cost: int) -> str:
    now = datetime.now(timezone.utc)
    budget_day = now.date()
    key = f"agent:cost:{budget_day.isoformat()}"
    # Retain the previous day's key while any requests admitted before midnight finish.
    expires_at = int(datetime.combine(
        budget_day + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc
    ).timestamp())
    budget = int(settings.daily_budget_usd * NANODOLLARS_PER_USD)
    if not reserve(keys=[key], args=[estimated_cost, budget, expires_at]):
        raise HTTPException(402, "Daily budget exceeded")
    return key


def record_cost(key: str, reserved_cost: int, input_tokens: int, output_tokens: int) -> None:
    adjustment = estimate_cost(input_tokens, output_tokens) - reserved_cost
    if adjustment:
        r.eval(
            "if redis.call('EXISTS', KEYS[1]) == 1 then "
            "return redis.call('INCRBY', KEYS[1], ARGV[1]) end",
            1, key, adjustment,
        )
