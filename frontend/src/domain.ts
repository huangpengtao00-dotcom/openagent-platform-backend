export type RunStatus = "pending" | "running" | "pass" | "fail" | "timeout" | "cancelled";

export type RunTone = "queued" | "active" | "success" | "danger" | "warning" | "muted";

export type DataSource = "sample" | "live" | "offline";

export type Usage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  model: string;
};

export type Run = {
  run_id: number;
  task_id: number;
  status: RunStatus;
  mode: "local" | "api";
  model: string;
  model_provider?: string | null;
  base_url?: string | null;
  wire_api?: string | null;
  reasoning_effort?: string | null;
  disable_response_storage?: boolean;
  timeout_seconds: number;
  source_run_id?: number | null;
  failure_context_path?: string | null;
  harness_run_id: string | null;
  artifacts_dir: string | null;
  failure_type: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  usage: Usage | null;
  artifacts?: Record<string, string>;
};

export type RunCatalogItem = Run & {
  task_name: string;
  task_description: string;
  harness_task_path: string;
};

export type EvaluationHistoryRun = {
  run_id: number;
  status: RunStatus | string;
  model: string;
  model_provider?: string | null;
  harness_run_id: string | null;
  failure_type?: string | null;
  error_message?: string | null;
  total_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
};

export type EvaluationHistoryItem = {
  evaluation_id?: number | null;
  task_id: number;
  name: string;
  description: string;
  created_at: string;
  status: "running" | "pass" | "partial" | "fail" | "empty" | string;
  run_count: number;
  model_count: number;
  passed: number;
  failed: number;
  pending: number;
  running: number;
  pass_rate: number;
  total_tokens: number;
  estimated_cost_usd: number;
  latest_run_id: number | null;
  best_run_id: number | null;
  latest_failure_type?: string | null;
  latest_error_message?: string | null;
  failure_types?: Record<string, number>;
  models: string[];
  runs: EvaluationHistoryRun[];
};

export type Task = {
  task_id: number;
  name: string;
  description: string;
  harness_task_path: string;
  created_at: string;
};

export type EvaluationCreateResult = {
  evaluation_id?: number | null;
  task: Task;
  runs: Run[];
  next_steps: string[];
};

export type EvaluationMatrixCell = {
  run_id: number;
  status: RunStatus | string;
  model: string;
  model_provider?: string | null;
  failure_type?: string | null;
  error_message?: string | null;
  total_tokens: number;
  estimated_cost_usd: number;
  duration_seconds?: number | null;
  artifacts_dir?: string | null;
};

export type EvaluationMatrix = {
  evaluation_id: number;
  name: string;
  goal: string;
  status: "running" | "pass" | "partial" | "fail" | "empty" | string;
  task_count: number;
  model_count: number;
  run_count: number;
  passed: number;
  failed: number;
  pending: number;
  running: number;
  pass_rate: number;
  total_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
  tasks: Array<{
    task_id: number;
    task_name: string;
    task_description: string;
    models: EvaluationMatrixCell[];
  }>;
};

export type RunSource = {
  run_id: number;
  harness_run_id: string | null;
  artifacts_dir: string | null;
  files: Array<{
    path: string;
    content: string;
  }>;
};

export type FailureContext = {
  source_run_id: number;
  status: string;
  failure_type: string | null;
  error_message: string | null;
  harness_run_id: string | null;
  artifacts_dir: string;
  task: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  retry_guidance: Record<string, unknown>;
};

export type AgentRunArtifact = {
  strategy?: {
    tier?: "simple" | "standard" | "deep" | string;
    max_steps?: number;
    prompt_char_budget?: number;
    rationale?: string[];
  };
  steps?: Array<{
    index: number;
    action: string;
    args?: Record<string, unknown>;
    observation?: Record<string, unknown>;
    usage?: {
      prompt_tokens?: number;
      completion_tokens?: number;
      total_tokens?: number;
      estimated_cost_usd?: number;
    };
  }>;
  total_usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    estimated_cost_usd?: number;
  };
  finished?: boolean;
  summary?: string;
};

export type EvaluationMemorySummary = {
  total_records: number;
  passed_records: number;
  failed_records: number;
  retry_records: number;
  retry_successes: number;
  fail_to_pass_rate: number;
  failure_types: Record<string, number>;
  top_tasks: Array<{
    task_name: string;
    total: number;
    passed: number;
    failed: number;
    last_run_id: number | null;
  }>;
  recent_items: Array<Record<string, unknown>>;
};

export type CostMetrics = {
  total_runs: number;
  total_tokens: number;
  estimated_cost_usd: number;
  by_model: Array<{
    model: string;
    runs: number;
    tokens: number;
    estimated_cost_usd: number;
  }>;
};

export type DemoStatus = {
  status: string;
  app_env: string;
  database: string;
  harness_root: string;
  harness_exists: boolean;
  harness_runs_root: string;
  harness_executor: string;
  harness_docker_image: string;
  allow_real_llm_calls: boolean;
  real_api_budget_limit_cny: number;
  auto_start_runs: boolean;
  queue_backend_configured: string;
  queue_backend_active: string;
  queue_key: string;
  queue_depth: number | null;
  redis_enabled: boolean;
  redis_url: string;
  redis_available: boolean;
};

export type DemoIdState = {
  count: number;
  min_id: number | null;
  max_id: number | null;
  ids: number[];
};

export type DemoState = {
  status: string;
  database: string;
  generated_at: string;
  tasks: DemoIdState;
  runs: DemoIdState;
  latest_runs: RunCatalogItem[];
};

export type EvaluationSummary = {
  summary: {
    total: number;
    passed: number;
    failed: number;
    pass_rate: number;
    avg_score: number;
    total_patch_lines: number;
    total_changed_files: number;
    tests_passed: number;
    failure_types: Record<string, number>;
    tokens: number;
    total_cost_usd: number;
    duration_seconds: number;
  };
  profiles: Array<{
    profile: string;
    total: number;
    passed: number;
    failed: number;
    pass_rate: number;
    avg_score: number;
    patch_lines: number;
    changed_files: number;
    tokens: number;
    estimated_cost_usd: number;
    duration_seconds: number;
  }>;
  recommendations?: Array<{
    category: "stable" | "cheap" | "fast" | "balanced" | string;
    profile: string;
    reason: string;
    score: number;
  }>;
  tasks: Array<{
    run_id: number;
    task_id: string;
    harness_run_id: string | null;
    profile: string;
    attempt_index: number;
    status: string;
    score: number;
    patch_lines: number;
    changed_files: number;
    tests_passed: boolean;
    failure_type: string;
    tokens: number;
    estimated_cost_usd: number;
    duration_seconds: number | null;
    report_link: string | null;
  }>;
  retry_comparisons: Array<{
    task_id: string;
    first_attempt_status: string;
    retry_status: string;
    fail_to_pass: boolean;
    retry_cost: number;
    retry_patch_lines: number;
    failure_type_changed: boolean;
    first_failure_type: string;
    retry_failure_type: string;
  }>;
};

export type TimelineStep = {
  status: RunStatus;
  label: string;
  state: "done" | "current" | "upcoming";
};

export function statusTone(status: RunStatus): RunTone {
  const tones: Record<RunStatus, RunTone> = {
    pending: "queued",
    running: "active",
    pass: "success",
    fail: "danger",
    timeout: "warning",
    cancelled: "muted",
  };
  return tones[status];
}

export function formatTokens(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatCurrency(value: number): string {
  return `$${value.toFixed(5)}`;
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function dataSourceLabel(source: DataSource): string {
  const labels: Record<DataSource, string> = {
    sample: "示例数据",
    live: "实时接口",
    offline: "离线展示",
  };
  return labels[source];
}

export function stableRunKey(taskId: number, mode: string, model: string): string {
  return `console-task-${taskId}-${mode}-${model}`;
}

export function runTimeline(status: RunStatus): TimelineStep[] {
  const steps: Array<{ status: RunStatus; label: string }> = [
    { status: "pending", label: "排队" },
    { status: "running", label: "执行" },
    { status: status === "cancelled" ? "cancelled" : status === "timeout" ? "timeout" : status === "fail" ? "fail" : "pass", label: "完成" },
  ];
  const currentIndex = status === "pending" ? 0 : status === "running" ? 1 : 2;
  return steps.map((step, index) => ({
    ...step,
    state: index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming",
  }));
}
