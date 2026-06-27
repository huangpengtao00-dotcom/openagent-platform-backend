import { afterEach, describe, expect, it, vi } from "vitest";
import { createCustomTask, createRun, deleteEvaluation, getApiWorkspaceContext, getArtifact, getDemoState, getDemoStatus, getEvaluationMatrix, getEvaluationMemorySummary, getRunSource, listRuns, retryRun, setApiWorkspaceContext } from "./api";

describe("api request headers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setApiWorkspaceContext({ tenantId: "default", workspaceId: "default" });
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

  it("attaches the active tenant and workspace headers to JSON requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "ok",
        app_env: "dev",
        database: "sqlite:///demo.db",
        harness_root: "C:/bundle/02_OpenAgent_Harness",
        harness_exists: true,
        harness_runs_root: "C:/bundle/artifacts/harness_runs",
        harness_executor: "local",
        harness_docker_image: "openagent-harness:latest",
        allow_real_llm_calls: false,
        real_api_budget_limit_cny: 1,
        auto_start_runs: true,
        queue_backend_configured: "db",
        queue_backend_active: "db",
        queue_key: "openagent:runs",
        queue_depth: null,
        redis_enabled: false,
        redis_url: "redis://localhost:6379/0",
        redis_available: false,
      }),
    } as Response);

    setApiWorkspaceContext({ tenantId: "team-a", workspaceId: "alpha" });
    expect(getApiWorkspaceContext()).toEqual({ tenantId: "team-a", workspaceId: "alpha" });
    await getDemoStatus();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/demo/status",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Tenant-ID": "team-a",
          "X-Workspace-ID": "alpha",
        }),
      }),
    );
  });

  it("attaches workspace headers when loading text artifacts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      text: async () => "diff --git a/app.py b/app.py\n",
    } as Response);

    setApiWorkspaceContext({ tenantId: "team-b", workspaceId: "experiments" });
    const patch = await getArtifact(12, "patch");

    expect(patch).toContain("diff --git");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/12/patch",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Tenant-ID": "team-b",
          "X-Workspace-ID": "experiments",
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

    await retryRun(42, { allow_llm_calls: true, timeout_seconds: 120, use_failure_context: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/42/retry",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"allow_llm_calls":true'),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/42/retry",
      expect.objectContaining({
        body: expect.stringContaining('"use_failure_context":true'),
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

  it("loads evaluation memory summary for the lightweight memory panel", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        total_records: 3,
        passed_records: 2,
        failed_records: 1,
        retry_records: 1,
        retry_successes: 1,
        fail_to_pass_rate: 1,
        failure_types: { None: 2, TestFailed: 1 },
        top_tasks: [{ task_name: "retry-429-real", total: 2, passed: 1, failed: 1, last_run_id: 3 }],
        recent_items: [],
      }),
    } as Response);

    const summary = await getEvaluationMemorySummary();

    expect(summary.retry_successes).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/memory/evaluation/summary",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("loads live demo state for occupied ids", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        status: "ok",
        database: "sqlite:///./artifacts/interview_demo.db",
        generated_at: "2026-06-20T10:00:00Z",
        tasks: { count: 2, min_id: 1, max_id: 2, ids: [1, 2] },
        runs: { count: 1, min_id: 1, max_id: 1, ids: [1] },
        latest_runs: [],
      }),
    } as Response);

    const state = await getDemoState();

    expect(state.tasks.ids).toEqual([1, 2]);
    expect(state.runs.count).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/demo/state",
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
      "/api/runs?limit=200",
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

  it("deletes evaluation tasks through the management endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ status: "deleted", task_id: 23, deleted_runs: 3, deleted_usage: 1 }),
    } as Response);

    const result = await deleteEvaluation(23);

    expect(result.deleted_runs).toBe(3);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/evaluations/23",
      expect.objectContaining({
        method: "DELETE",
      }),
    );
  });

  it("loads an evaluation result matrix", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        evaluation_id: 9,
        name: "matrix demo",
        goal: "compare models",
        status: "partial",
        task_count: 1,
        model_count: 2,
        run_count: 2,
        passed: 1,
        failed: 1,
        pending: 0,
        running: 0,
        pass_rate: 0.5,
        total_tokens: 1200,
        estimated_cost_usd: 0.02,
        created_at: "2026-06-24T12:00:00",
        tasks: [],
      }),
    } as Response);

    const matrix = await getEvaluationMatrix(9);

    expect(matrix.evaluation_id).toBe(9);
    expect(fetchMock).toHaveBeenCalledWith("/api/evaluations/9/matrix", expect.any(Object));
  });
});
