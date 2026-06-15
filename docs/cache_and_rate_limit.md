# Cache And Rate Limit

The backend includes an in-memory implementation plus a Redis counter implementation. If `ENABLE_REDIS=true` but Redis is unavailable, the service falls back to memory so local demos do not break.

## Rate Limit

`POST /runs` is limited per user with `RATE_LIMIT_RUNS_PER_MINUTE`. This protects real DeepSeek runs from accidental repeated submissions and cost spikes.

Set `RATE_LIMIT_RUNS_PER_MINUTE=0` to disable the limiter for local development.

## Idempotency

`Idempotency-Key` is checked before rate limiting. A repeated request from the same user returns the original run instead of creating a new run or triggering the Harness again.

## Cache Penetration

Missing run IDs are stored as negative cache entries for `CACHE_NEGATIVE_TTL_SECONDS`, reducing repeated database lookups for nonexistent resources.

## Cache Breakdown

The cache exposes per-key locks for mutex backfill. A future Redis version can use distributed locks with the same call shape.

## Cache Avalanche

TTL jitter is applied as `base_ttl + random(0, jitter)` so hot keys do not all expire at exactly the same second.
