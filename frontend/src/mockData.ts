import type { CostMetrics, EvaluationMemorySummary, EvaluationSummary, Run } from "./domain";

export type ArtifactKind = "report" | "patch" | "scorecard" | "test-result" | "trace";

export type EvidenceSection = {
  title: string;
  items: string[];
};

export const demoRun: Run = {
  run_id: 1,
  task_id: 1,
  status: "pass",
  mode: "local",
  model: "scripted",
  timeout_seconds: 120,
  harness_run_id: "retry-429-real",
  artifacts_dir: "harness_runs/retry-429-real",
  failure_type: null,
  error_message: null,
  created_at: "2026-06-16T09:20:00",
  started_at: "2026-06-16T09:20:03",
  finished_at: "2026-06-16T09:20:17",
  usage: {
    prompt_tokens: 8,
    completion_tokens: 7,
    total_tokens: 15,
    estimated_cost_usd: 0.00066,
    model: "deepseek-v4-flash",
  },
  artifacts: {
    report: "/runs/1/report",
    patch: "/runs/1/patch",
    scorecard: "/runs/1/scorecard",
    trace: "/runs/1/trace",
  },
};

export const demoCost: CostMetrics = {
  total_runs: 1,
  total_tokens: 15,
  estimated_cost_usd: 0.00066,
  by_model: [
    {
      model: "deepseek-v4-flash",
      runs: 1,
      tokens: 15,
      estimated_cost_usd: 0.00066,
    },
    {
      model: "newapi-5.4",
      runs: 1,
      tokens: 28640,
      estimated_cost_usd: 0,
    },
    {
      model: "gpt-5.5",
      runs: 1,
      tokens: 32159,
      estimated_cost_usd: 0,
    },
    {
      model: "scripted",
      runs: 10,
      tokens: 0,
      estimated_cost_usd: 0,
    },
  ],
};

export const demoEvaluation: EvaluationSummary = {
  summary: {
    total: 4,
    passed: 4,
    failed: 0,
    pass_rate: 1,
    avg_score: 97.38,
    total_patch_lines: 244,
    total_changed_files: 7,
    tests_passed: 4,
    failure_types: {
      None: 4,
      NoPatch: 0,
      TestFailed: 0,
      ScopeViolation: 0,
    },
    tokens: 32779,
    total_cost_usd: 0.00066,
    duration_seconds: 47.92,
  },
  profiles: [
    {
      profile: "本地兜底 baseline",
      total: 1,
      passed: 1,
      failed: 0,
      pass_rate: 1,
      avg_score: 100,
      patch_lines: 26,
      changed_files: 1,
      tokens: 0,
      estimated_cost_usd: 0,
      duration_seconds: 0.72,
    },
    {
      profile: "DeepSeek API",
      total: 1,
      passed: 1,
      failed: 0,
      pass_rate: 1,
      avg_score: 94,
      patch_lines: 78,
      changed_files: 2,
      tokens: 310,
      estimated_cost_usd: 0.00033,
      duration_seconds: 8.8,
    },
    {
      profile: "retry with context",
      total: 1,
      passed: 1,
      failed: 0,
      pass_rate: 1,
      avg_score: 95.5,
      patch_lines: 78,
      changed_files: 2,
      tokens: 310,
      estimated_cost_usd: 0.00033,
      duration_seconds: 8.9,
    },
    {
      profile: "OpenAI Fighting API",
      total: 1,
      passed: 1,
      failed: 0,
      pass_rate: 1,
      avg_score: 100,
      patch_lines: 62,
      changed_files: 2,
      tokens: 32159,
      estimated_cost_usd: 0,
      duration_seconds: 29.5,
    },
  ],
  recommendations: [
    {
      category: "stable",
      profile: "OpenAI Fighting API",
      score: 200,
      reason: "通过率 100%，平均分 100，复杂 token-bucket 任务一次通过。",
    },
    {
      category: "cheap",
      profile: "本地兜底 baseline",
      score: 0,
      reason: "离线路径 0 token、0 成本，适合演示平台闭环。",
    },
    {
      category: "fast",
      profile: "本地兜底 baseline",
      score: 0.72,
      reason: "平均耗时 0.72s，是最快的基准链路。",
    },
    {
      category: "balanced",
      profile: "DeepSeek API",
      score: 86.5,
      reason: "真实 API 成本和 token 更轻，复杂度较高时可作为性价比优先选择。",
    },
  ],
  tasks: [
    {
      run_id: 1,
      task_id: "retry-429-real",
      harness_run_id: "retry-429-real-bad6c1cc",
      profile: "本地兜底 baseline",
      attempt_index: 1,
      status: "pass",
      score: 100,
      patch_lines: 26,
      changed_files: 1,
      tests_passed: true,
      failure_type: "None",
      tokens: 0,
      estimated_cost_usd: 0,
      duration_seconds: 0.72,
      report_link: "/runs/1/report",
    },
    {
      run_id: 2,
      task_id: "retry-429-real",
      harness_run_id: "retry-429-real-deepseek",
      profile: "DeepSeek API",
      attempt_index: 1,
      status: "pass",
      score: 94,
      patch_lines: 78,
      changed_files: 2,
      tests_passed: true,
      failure_type: "None",
      tokens: 310,
      estimated_cost_usd: 0.00033,
      duration_seconds: 8.8,
      report_link: "/runs/2/report",
    },
    {
      run_id: 3,
      task_id: "retry-429-real",
      harness_run_id: "retry-429-real-retry",
      profile: "retry with context",
      attempt_index: 2,
      status: "pass",
      score: 95,
      patch_lines: 78,
      changed_files: 2,
      tests_passed: true,
      failure_type: "None",
      tokens: 310,
      estimated_cost_usd: 0.00033,
      duration_seconds: 8.9,
      report_link: "/runs/3/report",
    },
    {
      run_id: 4,
      task_id: "stair-25-hard-token-bucket",
      harness_run_id: "stair-25-hard-token-bucket-openai",
      profile: "OpenAI Fighting API",
      attempt_index: 1,
      status: "pass",
      score: 100,
      patch_lines: 62,
      changed_files: 2,
      tests_passed: true,
      failure_type: "None",
      tokens: 32159,
      estimated_cost_usd: 0,
      duration_seconds: 29.5,
      report_link: "/runs/4/report",
    },
  ],
  retry_comparisons: [
    {
      task_id: "retry-429-real",
      first_attempt_status: "fail",
      retry_status: "pass",
      fail_to_pass: true,
      retry_cost: 0.00033,
      retry_patch_lines: 78,
      failure_type_changed: true,
      first_failure_type: "TestFailed",
      retry_failure_type: "None",
    },
  ],
};

export const demoMemorySummary: EvaluationMemorySummary = {
  total_records: 4,
  passed_records: 3,
  failed_records: 1,
  retry_records: 1,
  retry_successes: 1,
  fail_to_pass_rate: 1,
  failure_types: {
    None: 3,
    TestFailed: 1,
  },
  top_tasks: [
    {
      task_name: "retry-429-real",
      total: 2,
      passed: 1,
      failed: 1,
      last_run_id: 3,
    },
    {
      task_name: "config-loader-real",
      total: 1,
      passed: 1,
      failed: 0,
      last_run_id: 2,
    },
  ],
  recent_items: [
    {
      run_id: 3,
      task_name: "retry-429-real",
      status: "pass",
      source_run_id: 1,
      failure_type: "None",
    },
  ],
};

const demoArtifacts: Record<ArtifactKind, string> = {
  report: `<h1>OpenAgent Run Report</h1>
<section>
  <h2>任务</h2>
  <p>HTTP 429 retry fix</p>
</section>
<section>
  <h2>结论</h2>
  <p>运行通过，4/4 tests passed。Harness 修改 retry 判断逻辑，Platform 记录运行状态、产物入口和成本信息。</p>
</section>
<section>
  <h2>证据</h2>
  <p>score=100, changed_files=1, patch_lines=26, failure_type=null。</p>
</section>`,
  patch: `diff --git a/http_client.py b/http_client.py
--- a/http_client.py
+++ b/http_client.py
@@ -1,12 +1,12 @@
-RETRYABLE_STATUSES = {500, 502, 503, 504}
+RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


 def should_retry(status_code: int, attempt: int, max_attempts: int) -> bool:
     """Return whether a failed HTTP request should be retried."""
     if attempt >= max_attempts:
         return False
     return status_code in RETRYABLE_STATUSES`,
  scorecard: `{
  "score": 100,
  "status": "pass",
  "patch_lines": 26,
  "changed_files": 1,
  "tests_passed": true,
  "failure_type": null,
  "pass_rate": 1,
  "rationale": [
    "quality gate passed",
    "acceptance tests passed",
    "patch stayed inside allowlist",
    "small changed-file footprint",
    "compact patch"
  ]
}`,
  "test-result": `{
  "tests_ran": true,
  "tests_passed": true,
  "command": "python -m pytest -q",
  "results": [
    {
      "command": "python -m pytest -q",
      "exit_code": 0,
      "stdout": "....                                                                     [100%]\\n4 passed in 0.02s\\n",
      "stderr": "",
      "timed_out": false,
      "duration_seconds": 0.3717
    }
  ]
}`,
  trace: `{"run_id": "retry-429-real-bad6c1cc", "task_id": "retry-429-real", "phase": "spec", "step": 1, "message": "HTTP 429 rate-limit responses should be retried when retry budget remains."}
{"run_id": "retry-429-real-bad6c1cc", "task_id": "retry-429-real", "phase": "act", "step": 2, "message": "created isolated workspace and captured full baseline"}
{"run_id": "retry-429-real-bad6c1cc", "task_id": "retry-429-real", "phase": "act", "step": 3, "message": "scripted agent applied local patch", "observation": {"changed": ["http_client.py"]}}
{"run_id": "retry-429-real-bad6c1cc", "task_id": "retry-429-real", "phase": "verify", "step": 4, "message": "ran acceptance checks", "tool": {"name": "acceptance", "args": ["python -m pytest -q"]}, "observation": {"tests_ran": true, "tests_passed": true, "exit_codes": [0]}}
{"run_id": "retry-429-real-bad6c1cc", "task_id": "retry-429-real", "phase": "report", "step": 5, "message": "generated scorecard and HTML report", "observation": {"score": 100, "html_report": "report.html"}}`,
};

export function getDemoArtifact(kind: ArtifactKind): string {
  return demoArtifacts[kind];
}

export const demoArtifact = getDemoArtifact("scorecard");

export const demoEvidenceSections: EvidenceSection[] = [
  {
    title: "项目亮点",
    items: [
      "把 Harness 执行能力封装成 FastAPI 控制面，前后职责边界清楚。",
      "run 状态、产物、成本和取消动作都可观察，便于复盘一次 agent 执行。",
      "默认离线展示不需要密钥；真实模型调用保持双重确认。",
    ],
  },
  {
    title: "技术难点",
    items: [
      "异步 worker 和 API 写入同一套 run 状态，需要处理 pending/running/pass/fail/timeout/cancelled 的状态收敛。",
      "artifact 访问要做路径约束，避免把运行目录之外的文件暴露出去。",
      "成本统计和真实调用保护要服务演示场景，同时避免误触发真实模型消费。",
    ],
  },
  {
    title: "演示路径",
    items: [
      "先看总览页说明 Harness、Platform API、Worker、Artifacts 的分工。",
      "再进入运行页创建或刷新 run，观察状态时间线和取消入口。",
      "最后查看产物和成本页，用 patch、scorecard、trace 解释一次完整执行证据。",
    ],
  },
];
