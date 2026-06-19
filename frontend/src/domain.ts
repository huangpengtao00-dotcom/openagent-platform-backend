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
  timeout_seconds: number;
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

export type RunSource = {
  run_id: number;
  harness_run_id: string | null;
  artifacts_dir: string | null;
  files: Array<{
    path: string;
    content: string;
  }>;
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
  harness_root: string;
  harness_exists: boolean;
  allow_real_llm_calls: boolean;
  real_api_budget_limit_cny: number;
  harness_runs_root: string;
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
