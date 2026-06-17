# OpenAgent Demo Console Design

## Goal

Add a lightweight, polished frontend console under `frontend/` that makes the Platform Backend visible to interviewers without expanding backend scope.

## Architecture Boundary

- Harness owns execution: agent loop, tools, patch, tests, trace, report.
- Platform Backend owns control plane: tasks, runs, cancellation, artifacts, cost metrics.
- Demo Console owns browser presentation only. It does not store API keys, call DeepSeek directly, or reimplement Harness behavior.

## Pages

- Overview: architecture boundary, test evidence, run states, guardrails.
- Runs: create a safe local scripted run, refresh run status, cancel run.
- Artifacts: view report, patch, scorecard, test-result, and trace by run id.
- Cost: show `/metrics/cost` totals and model breakdown.
- Evidence: show demo commands and interview talk track.

## Visual Direction

Borrow the reference zip's useful language: light gray background, white panels, subtle borders, low shadows, compact project cards, and technology pills. Replace the portfolio narrative with a SaaS/AgentOps console: left navigation, top status, dense but readable evidence panels, and code-native controls.

## Non-Goals

- No login or role system.
- No frontend API-key storage.
- No direct DeepSeek calls.
- No Harness logic in the browser.
- No complex charting or large UI framework.
