"""Atomic per-key sliding window shared by all agent processes."""
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException

from .config import settings
from .redis_client import r


take_slot = r.register_script("""
local now = redis.call('TIME')
local ms = now[1] * 1000 + math.floor(now[2] / 1000)
local window = 60000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ms - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    if #oldest == 0 then return 60 end
    return math.ceil((tonumber(oldest[2]) + window - ms) / 1000)
end
redis.call('ZADD', KEYS[1], ms, ARGV[2])
redis.call('PEXPIRE', KEYS[1], window)
return 0
""")


def check_rate_limit(key: str) -> None:
    key_hash = sha256(key.encode()).hexdigest()
    retry_after = take_slot(
        keys=[f"agent:rate:{key_hash}"],
        args=[settings.rate_limit_per_minute, uuid4().hex],
    )
    if retry_after:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(retry_after)})
