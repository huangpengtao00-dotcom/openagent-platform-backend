# Harness Integration

The Platform calls the final OpenAgent Harness with subprocess. It does not import or duplicate the agent loop.

```bash
python -m openagent_harness.cli run <task.json> --mode local --model scripted --runs ./artifacts/harness_runs
```

API mode is gated twice:

- server env `ALLOW_REAL_LLM_CALLS=true`
- request body `allow_llm_calls=true`

The Harness writes artifacts such as `report.html`, `patch.diff`, `scorecard.json`, `test_result.json`, and `trace.jsonl`. The Platform stores the resulting artifact directory and serves only known files under the configured `HARNESS_RUNS_ROOT`.

Cost is parsed from `trace.jsonl` when it contains `observation.usage`, falling back to `api_agent_run.json` if present.

