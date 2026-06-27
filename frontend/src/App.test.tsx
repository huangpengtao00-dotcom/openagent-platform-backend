import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App, { buildCustomTaskClipboardText, confirmFailureContextRetry, copyTextToClipboard, formatRunTaskIdentity, parseCustomTaskClipboardText } from "./App";

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function mockBaseFetch(extra?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const overridden = extra?.(url, init);
    if (overridden) {
      return overridden;
    }
    if (url === "/api/demo/status") {
      return jsonResponse({
        status: "ok",
        app_env: "test",
        database: "test.db",
        harness_root: "C:/bundle/02_OpenAgent_Harness",
        harness_exists: true,
        harness_runs_root: "C:/bundle/artifacts/harness_runs",
        harness_executor: "docker",
        harness_docker_image: "openagent-harness:latest",
        allow_real_llm_calls: false,
        real_api_budget_limit_cny: 1,
        auto_start_runs: true,
        queue_backend_configured: "redis",
        queue_backend_active: "redis",
        queue_key: "openagent:runs",
        queue_depth: 0,
        redis_enabled: true,
        redis_url: "redis://localhost:6379/0",
        redis_available: true,
      });
    }
    if (url === "/api/demo/state") {
      return jsonResponse({
        status: "ok",
        database: "test.db",
        generated_at: "2026-06-24T12:00:00",
        tasks: { count: 0, min_id: null, max_id: null, ids: [] },
        runs: { count: 0, min_id: null, max_id: null, ids: [] },
        latest_runs: [],
      });
    }
    if (url.startsWith("/api/runs")) {
      return jsonResponse([]);
    }
    if (url === "/api/evaluations/history") {
      return jsonResponse([]);
    }
    if (url === "/api/evaluation-drafts" && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      return jsonResponse({
        name: "load_config 行为修复评测",
        goal: "修复 load_config 的嵌套配置合并行为。",
        source_filename: body.source_filename ?? "config_loader.py",
        source_code: body.source_code,
        test_filename: "test_config_loader.py",
        test_code: "from config_loader import load_config\n\n\ndef test_config_merge():\n    assert load_config({}) is not None\n",
        acceptance_command: "python -m pytest -q",
        difficulty: {
          difficulty_level: "medium",
          difficulty_score: 44,
          reasons: ["涉及结构化数据或配置合并，需要覆盖嵌套字段和默认值。"],
          risk_factors: ["weak_tests"],
          suggested_strategy: { notes: ["标准 Agent Loop", "ContextBuilder 检索", "pytest 验证", "允许一次 retry"] },
        },
        difficulty_level: "medium",
        difficulty_score: 44,
        difficulty_reasons: ["涉及结构化数据或配置合并，需要覆盖嵌套字段和默认值。"],
        risk_factors: ["weak_tests"],
        suggested_strategy: { notes: ["标准 Agent Loop", "ContextBuilder 检索", "pytest 验证", "允许一次 retry"] },
        analysis_steps: ["读取源码", "生成 pytest 草稿"],
        findings: ["识别到函数入口：load_config。"],
        suggested_changes: ["确认目标是否正确。"],
        confidence: "规则整理草稿。",
      });
    }
    return jsonResponse({});
  });
}

describe("App simplified evaluation flow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("formats the run to task mapping for catalog cards", () => {
    expect(formatRunTaskIdentity({ run_id: 7, task_id: 3 })).toBe("run #7 -> task #3");
  });

  it("builds a paste-ready evaluation task template", () => {
    const text = buildCustomTaskClipboardText({
      name: "retry after rate limit",
      goal: "Retry HTTP 429 while budget remains.",
      source_filename: "http_client.py",
      source_code: "def should_retry():\n    return False\n",
      test_filename: "test_http_client.py",
      test_code: "def test_retry():\n    assert True\n",
      acceptance_command: "python -m pytest -q",
    });

    expect(text).toContain("任务名称: retry after rate limit");
    expect(text).toContain("目标: Retry HTTP 429 while budget remains.");
    expect(text).toContain("源码文件: http_client.py");
    expect(text).toContain("测试文件: test_http_client.py");
    expect(text).toContain("验收命令: python -m pytest -q");
  });

  it("imports a copied task template back into a draft", () => {
    const draft = {
      name: "retry after rate limit",
      goal: "Retry HTTP 429 while budget remains.",
      source_filename: "http_client.py",
      source_code: "def should_retry():\n    return False\n",
      test_filename: "test_http_client.py",
      test_code: "def test_retry():\n    assert True\n",
      acceptance_command: "python -m pytest -q",
    };

    expect(parseCustomTaskClipboardText(buildCustomTaskClipboardText(draft))).toEqual({
      ...draft,
      source_code: draft.source_code.trimEnd(),
      test_code: draft.test_code.trimEnd(),
    });
  });

  it("rejects pasted task text when required fields are missing", () => {
    expect(parseCustomTaskClipboardText("任务名称: demo\n目标: missing source")).toBeNull();
  });

  it("copies the task template through the Clipboard API", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(copyTextToClipboard("任务名称: demo")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("任务名称: demo");
  });

  it("turns pasted source code into an evaluation draft", async () => {
    mockBaseFetch();

    render(<App />);
    fireEvent.click(screen.getAllByRole("button", { name: "新建评测" })[0]);
    await screen.findByText("粘贴源码");
    fireEvent.change(screen.getByLabelText("源码"), { target: { value: "def load_config(user_config):\n    return user_config\n" } });
    fireEvent.click(screen.getByRole("button", { name: "分析源码" }));

    expect(await screen.findByText("load_config 行为修复评测")).toBeInTheDocument();
    expect(screen.getByText("系统判断：medium")).toBeInTheDocument();
    expect(screen.getByText("识别到函数入口：load_config。")).toBeInTheDocument();
  });

  it("submits one evaluation with multiple selected model profiles", async () => {
    const fetchMock = mockBaseFetch((url, init) => {
      if (url === "/api/demo/status") {
        return jsonResponse({
          status: "ok",
          app_env: "test",
          database: "test.db",
          harness_root: "C:/bundle/02_OpenAgent_Harness",
          harness_exists: true,
          harness_runs_root: "C:/bundle/artifacts/harness_runs",
          harness_executor: "docker",
          harness_docker_image: "openagent-harness:latest",
          allow_real_llm_calls: true,
          real_api_budget_limit_cny: 1,
          auto_start_runs: true,
          queue_backend_configured: "redis",
          queue_backend_active: "redis",
          queue_key: "openagent:runs",
          queue_depth: 0,
          redis_enabled: true,
          redis_url: "redis://localhost:6379/0",
          redis_available: true,
        });
      }
      if (url === "/api/evaluations" && init?.method === "POST") {
        return jsonResponse({
          task: {
            task_id: 12,
            name: "custom config merge",
            description: "Fix load_config so nested headers are merged without mutating DEFAULTS.",
            harness_task_path: "custom_tasks/custom-config-merge/task.json",
            created_at: "2026-06-24T12:00:00",
          },
          runs: [
            {
              run_id: 44,
              task_id: 12,
              status: "pending",
              mode: "api",
              model: "gpt-5.5",
              timeout_seconds: 240,
              harness_run_id: null,
              artifacts_dir: null,
              failure_type: null,
              error_message: null,
              created_at: "2026-06-24T12:00:00",
              started_at: null,
              finished_at: null,
              usage: null,
              artifacts: {},
            },
          ],
          next_steps: ["watch runs"],
        });
      }
      return undefined;
    });

    render(<App />);
    fireEvent.click(screen.getAllByRole("button", { name: "新建评测" })[0]);
    await screen.findByText("粘贴源码");
    fireEvent.click(screen.getByRole("button", { name: "载入样例：配置合并任务" }));
    fireEvent.click(screen.getByRole("button", { name: "分析源码" }));
    await screen.findByText("load_config 行为修复评测");
    fireEvent.click(screen.getByRole("button", { name: "开始多模型评测" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/evaluations", expect.objectContaining({ method: "POST" }));
    });
    const evaluationCall = fetchMock.mock.calls.find(([url, init]) => String(url) === "/api/evaluations" && init?.method === "POST");
    expect(evaluationCall).toBeTruthy();
    const body = JSON.parse(String(evaluationCall?.[1]?.body));
    expect(body.files[0].path).toBe("config_loader.py");
    expect(body.test_files[0].path).toBe("test_config_loader.py");
    expect(body.model_profiles).toHaveLength(3);
    expect(body.model_profiles.map((profile: { model: string }) => profile.model)).toEqual(expect.arrayContaining(["deepseek-v4-flash", "gpt-5.4", "gpt-5.5"]));
    expect(body.model_profiles.map((profile: { model_provider: string }) => profile.model_provider)).toEqual(expect.arrayContaining(["DeepSeek API", "newapi-5.4", "newapi-5.5"]));
    expect(body.model_profiles.filter((profile: { mode: string; allow_llm_calls: boolean }) => profile.mode === "api").every((profile: { allow_llm_calls: boolean }) => profile.allow_llm_calls)).toBe(true);
  });

  it("shows history as task-level evaluation records", async () => {
    mockBaseFetch((url) => {
      if (url === "/api/evaluations/history") {
        return jsonResponse([
          {
            evaluation_id: 9,
            task_id: 12,
            name: "历史评测任务",
            description: "同一源码的多模型横向对比。",
            created_at: "2026-06-24T12:00:00",
            status: "partial",
            run_count: 3,
            model_count: 3,
            passed: 1,
            failed: 2,
            pending: 0,
            running: 0,
            pass_rate: 0.333,
            total_tokens: 1234,
            estimated_cost_usd: 0.02,
            latest_run_id: 44,
            best_run_id: 42,
            latest_failure_type: "ProviderTransient",
            latest_error_message: "exceeded retry limit, last status: 429 Too Many Requests",
            failure_types: { ProviderTransient: 1 },
            models: ["scripted", "newapi-5.4", "newapi-5.5"],
            runs: [
              {
                run_id: 44,
                status: "fail",
                model: "gpt-5.5",
                model_provider: "newapi-5.5",
                harness_run_id: "run-44",
                failure_type: "ProviderTransient",
                error_message: "exceeded retry limit, last status: 429 Too Many Requests",
                total_tokens: 900,
                estimated_cost_usd: 0.01,
                created_at: "2026-06-24T12:00:00",
              },
            ],
          },
        ]);
      }
      if (url === "/api/evaluations/9/matrix") {
        return jsonResponse({
          evaluation_id: 9,
          name: "历史评测任务",
          goal: "同一源码的多模型横向对比。",
          status: "partial",
          task_count: 1,
          model_count: 3,
          run_count: 3,
          passed: 1,
          failed: 2,
          pending: 0,
          running: 0,
          pass_rate: 0.333,
          total_tokens: 1234,
          estimated_cost_usd: 0.02,
          created_at: "2026-06-24T12:00:00",
          tasks: [
            {
              task_id: 12,
              task_name: "历史评测任务",
              task_description: "同一源码的多模型横向对比。",
              models: [
                {
                  run_id: 44,
                  status: "fail",
                  model: "gpt-5.5",
                  model_provider: "newapi-5.5",
                  failure_type: "ProviderTransient",
                  error_message: "exceeded retry limit, last status: 429 Too Many Requests",
                  total_tokens: 900,
                  estimated_cost_usd: 0.01,
                  duration_seconds: 18,
                  artifacts_dir: "artifacts/run-44",
                },
              ],
            },
          ],
        });
      }
      return undefined;
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "历史" }));

    expect(await screen.findByText("历史评测任务")).toBeInTheDocument();
    expect(screen.getAllByText("部分通过").length).toBeGreaterThan(0);
    expect(screen.getByText("最近失败：模型服务临时失败")).toBeInTheDocument();
    expect(screen.getByText(/429 Too Many Requests/)).toBeInTheDocument();
    expect(screen.getAllByText("newapi-5.5").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /查看最新 run/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /查看矩阵/i }));
    expect(await screen.findByText("Evaluation 结果矩阵")).toBeInTheDocument();
    expect(screen.getByText(/Evaluation #9/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /删除该任务/i })).toBeInTheDocument();
  });

  it("requires explicit consent before using failed-run evidence for retry", () => {
    const confirm = vi.fn(() => false);
    const allowed = confirmFailureContextRetry(
      {
        run_id: 7,
        task_id: 3,
        status: "fail",
        mode: "api",
        model: "deepseek-v4-flash",
        timeout_seconds: 180,
        harness_run_id: "retry-429-real-failed",
        artifacts_dir: "artifacts/interview_demo_runs/retry-429-real-failed",
        failure_type: "Regression",
        error_message: "pytest failed",
        created_at: "2026-06-21T12:00:00",
        started_at: null,
        finished_at: null,
        usage: null,
        artifacts: {},
      },
      confirm,
    );

    expect(allowed).toBe(false);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("trace"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("scorecard"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("patch"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("模型"));
  });

  it("keeps NewAPI 5.4 visible on the cost page even before usage exists", async () => {
    mockBaseFetch((url) => {
      if (url === "/api/metrics/cost") {
        return jsonResponse({
          total_runs: 1,
          total_tokens: 120,
          estimated_cost_usd: 0.001,
          by_model: [
            { model: "deepseek-v4-flash", runs: 1, tokens: 120, estimated_cost_usd: 0.001 },
          ],
        });
      }
      return undefined;
    });

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "成本" }));
    fireEvent.click(await screen.findByRole("button", { name: "刷新成本" }));

    expect(await screen.findByText("DeepSeek API")).toBeInTheDocument();
    expect(screen.getByText("NewAPI 5.4")).toBeInTheDocument();
    expect(screen.getByText("NewAPI 5.5")).toBeInTheDocument();
  });
});
