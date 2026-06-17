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
