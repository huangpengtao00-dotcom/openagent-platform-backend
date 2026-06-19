import type { CreateRunInput, CreateTaskInput } from "./api";

export type EvaluationProfile = {
  id: "local-demo" | "deepseek-api" | "retry-context";
  label: string;
  taskPath: string;
  mode: CreateRunInput["mode"];
  model: string;
  allowLlmCalls: boolean;
  timeoutSeconds: number;
  description: string;
  budgetHint: string;
};

export const evaluationProfiles: EvaluationProfile[] = [
  {
    id: "local-demo",
    label: "scripted baseline",
    taskPath: "benchmarks_realistic/retry-429-real/task.json",
    mode: "local",
    model: "scripted",
    allowLlmCalls: false,
    timeoutSeconds: 120,
    description: "Offline zero-cost baseline. It exercises the full Platform -> Harness -> pytest -> report/patch/scorecard chain.",
    budgetHint: "0 tokens, stable for live interview demos.",
  },
  {
    id: "deepseek-api",
    label: "DeepSeek API",
    taskPath: "examples/deepseek_real_task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 120,
    description: "Real model path. Requires ALLOW_REAL_LLM_CALLS=true and a configured DeepSeek-compatible key.",
    budgetHint: "Real calls are capped by the backend 1 CNY budget gate.",
  },
  {
    id: "retry-context",
    label: "retry with context",
    taskPath: "benchmarks_realistic/retry-429-real/task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 180,
    description: "Failure-aware retry profile. Use the Retry with context button after a failed run so the dashboard compares first attempt and retry.",
    budgetHint: "Same real-call budget gate; retry metrics are folded into the Evaluation Dashboard.",
  },
];

export type EvaluationRequest = {
  task: CreateTaskInput;
  run: Omit<CreateRunInput, "task_id">;
  idempotencyKey: string;
};

export function buildEvaluationRequest(profile: EvaluationProfile): EvaluationRequest {
  return {
    task: {
      name: profile.label,
      description: profile.description,
      harness_task_path: profile.taskPath,
    },
    run: {
      mode: profile.mode,
      model: profile.model,
      allow_llm_calls: profile.allowLlmCalls,
      timeout_seconds: profile.timeoutSeconds,
    },
    idempotencyKey: `console-eval-${profile.id}`,
  };
}

export function buildFreshIdempotencyKey(prefix: string, now = Date.now()): string {
  return `${prefix}-${now}`;
}
