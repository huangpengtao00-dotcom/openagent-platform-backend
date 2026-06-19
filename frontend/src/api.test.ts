import { afterEach, describe, expect, it, vi } from "vitest";
import { createCustomTask, createRun, getDemoStatus, getRunSource, listRuns, retryRun } from "./api";

describe("api request headers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves JSON content type when createRun adds an idempotency key", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 42,
        task_id: 7,
        status: "pending",
        mode: "api",
        model: "deepseek-v4-flash",
        timeout_seconds: 120,
        artifacts: {},
      }),
    } as Response);

    await createRun(
      {
        task_id: 7,
        mode: "api",
        model: "deepseek-v4-flash",
        allow_llm_calls: true,
        timeout_seconds: 120,
      },
      "console-eval-api-retry-429",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "Idempotency-Key": "console-eval-api-retry-429",
        }),
      }),
    );
  });

  it("posts custom task payloads to the backend generator", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ task_id: 9, harness_task_path: "custom_tasks/demo/task.json" }),
    } as Response);

    await createCustomTask({
      name: "demo",
      goal: "fix it",
      source_filename: "app.py",
      source_code: "def f(): pass\n",
      test_filename: "test_app.py",
      test_code: "def test_ok(): assert True\n",
      acceptance_command: "python -m pytest -q",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/custom-tasks",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"source_filename":"app.py"'),
      }),
    );
  });

  it("posts retry requests with explicit real-call intent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 43,
        task_id: 7,
        status: "pending",
        mode: "api",
        model: "deepseek-v4-flash",
        timeout_seconds: 120,
        artifacts: {},
      }),
    } as Response);

    await retryRun(42, { allow_llm_calls: true, timeout_seconds: 120 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/42/retry",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"allow_llm_calls":true'),
      }),
    );
  });

  it("loads demo status for the frontend real-call gate", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "ok",
        harness_root: "C:/bundle/02_OpenAgent_Harness",
        harness_exists: true,
        allow_real_llm_calls: false,
        real_api_budget_limit_cny: 1.0,
        harness_runs_root: "C:/bundle/artifacts/interview_demo_runs",
      }),
    } as Response);

    const status = await getDemoStatus();

    expect(status.allow_real_llm_calls).toBe(false);
    expect(status.real_api_budget_limit_cny).toBe(1.0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/demo/status",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("loads the run catalog from the backend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        {
          run_id: 7,
          task_id: 3,
          task_name: "retry-429-real",
          task_description: "retry task",
          harness_task_path: "benchmarks/retry/task.json",
          status: "pass",
          mode: "local",
          model: "scripted",
          timeout_seconds: 120,
          harness_run_id: "retry-429-real-abcd",
          artifacts_dir: "artifacts/runs/retry-429-real-abcd",
          failure_type: null,
          error_message: null,
          created_at: "2026-06-18T00:00:00",
          started_at: null,
          finished_at: null,
          usage: null,
          artifacts: {},
        },
      ],
    } as Response);

    const runs = await listRuns();

    expect(runs[0].task_name).toBe("retry-429-real");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("loads source snapshots for a selected run", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 7,
        harness_run_id: "retry-429-real-abcd",
        artifacts_dir: "artifacts/runs/retry-429-real-abcd",
        files: [{ path: "http_client.py", content: "def should_retry(): pass\n" }],
      }),
    } as Response);

    const source = await getRunSource(7);

    expect(source.files[0].path).toBe("http_client.py");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/7/source",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });
});
