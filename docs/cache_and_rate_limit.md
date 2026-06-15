# Cache And Rate Limit

The backend includes a small in-memory implementation that mirrors Redis-backed production behavior.

## Rate Limit

`POST /runs` is limited per user with `RATE_LIMIT_RUNS_PER_MINUTE`. This protects real DeepSeek runs from accidental repeated submissions and cost spikes.

## Idempotency

`Idempotency-Key` is checked before rate limiting. A repeated request from the same user returns the original run instead of creating a new run or triggering the Harness again.

## Cache Penetration

Missing run IDs are stored as negative cache entries for `CACHE_NEGATIVE_TTL_SECONDS`, reducing repeated database lookups for nonexistent resources.

## Cache Breakdown

The cache exposes per-key locks for mutex backfill. A future Redis version can use distributed locks with the same call shape.

## Cache Avalanche

TTL jitter is applied as `base_ttl + random(0, jitter)` so hot keys do not all expire at exactly the same second.

