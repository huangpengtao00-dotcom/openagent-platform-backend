import type { CreateRunInput, CreateTaskInput } from "./api";

export type EvaluationProfile = {
  id: "scripted-retry-429" | "api-retry-429" | "api-config-loader";
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
    id: "scripted-retry-429",
    label: "Safe scripted retry-429",
    taskPath: "benchmarks_realistic/retry-429-real/task.json",
    mode: "local",
    model: "scripted",
    allowLlmCalls: false,
    timeoutSeconds: 120,
    description: "Zero-cost baseline. Exercises the same Platform -> Harness artifact path without calling a model.",
    budgetHint: "0 tokens, safe for repeated demos",
  },
  {
    id: "api-retry-429",
    label: "Real DeepSeek retry-429",
    taskPath: "examples/deepseek_real_task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 120,
    description: "Real model evaluation for the HTTP 429 retry bug. Good interview demo because the patch is small and easy to explain.",
    budgetHint: "Typical smoke cost is well below 1 CNY",
  },
  {
    id: "api-config-loader",
    label: "Real DeepSeek config-loader",
    taskPath: "benchmarks_realistic/config-loader-real/task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 120,
    description: "A second real task example so the demo is not hard-coded to one scripted benchmark.",
    budgetHint: "Use once for variety; still guarded by backend double opt-in",
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
