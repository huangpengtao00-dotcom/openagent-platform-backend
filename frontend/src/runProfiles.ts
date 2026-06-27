import type { CreateRunInput, CreateTaskInput } from "./api";

export type EvaluationProfile = {
  id: "local-demo" | "deepseek-api" | "newapi-5-4" | "newapi-5-5" | "openai-fighting" | "custom-api" | "retry-context";
  label: string;
  taskPath: string;
  mode: CreateRunInput["mode"];
  model: string;
  allowLlmCalls: boolean;
  timeoutSeconds: number;
  description: string;
  budgetHint: string;
  providerOptions?: Pick<CreateRunInput, "model_provider" | "base_url" | "wire_api" | "reasoning_effort" | "disable_response_storage">;
};

export const evaluationProfiles: EvaluationProfile[] = [
  {
    id: "local-demo",
    label: "本地兜底 baseline",
    taskPath: "benchmarks_realistic/retry-429-real/task.json",
    mode: "local",
    model: "scripted",
    allowLlmCalls: false,
    timeoutSeconds: 120,
    description: "开发/演示兜底链路。只证明 Platform -> Harness -> pytest -> artifact 回路，不参与主模型能力排序。",
    budgetHint: "0 tokens。稍难任务能力有限，默认不选。",
  },
  {
    id: "deepseek-api",
    label: "DeepSeek API",
    taskPath: "custom_tasks/stair-25-hard-token-bucket/task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 240,
    description: "DeepSeek 真实模型路径，用来观察复杂任务上的稳定性和成本。",
    budgetHint: "真实调用受后端 1 CNY 预算闸门控制。",
  },
  {
    id: "newapi-5-4",
    label: "NewAPI 5.4",
    taskPath: "custom_tasks/stair-25-hard-token-bucket/task.json",
    mode: "api",
    model: "gpt-5.4",
    allowLlmCalls: true,
    timeoutSeconds: 240,
    description: "NewAPI 5.4 横向对比路径，使用独立 key 运行同一个任务。",
    budgetHint: "真实调用。重点对比通过率、延迟、token 和报告质量。",
    providerOptions: {
      model_provider: "newapi-5.4",
      base_url: "https://api.sbbbbbbbbb.xyz/v1",
      wire_api: "chat_completions",
    },
  },
  {
    id: "newapi-5-5",
    label: "NewAPI 5.5",
    taskPath: "custom_tasks/stair-25-hard-token-bucket/task.json",
    mode: "api",
    model: "gpt-5.5",
    allowLlmCalls: true,
    timeoutSeconds: 240,
    description: "NewAPI 5.5 横向对比路径，和 5.4 在同一任务、同一验收标准下并排运行。",
    budgetHint: "真实调用。重点看更强模型是否带来更高成功率和更少重试。",
    providerOptions: {
      model_provider: "newapi-5.5",
      base_url: "https://api.sbbbbbbbbb.xyz/v1",
      wire_api: "chat_completions",
    },
  },
  {
    id: "openai-fighting",
    label: "OpenAI Fighting API",
    taskPath: "custom_tasks/stair-25-hard-token-bucket/task.json",
    mode: "api",
    model: "gpt-5.5",
    allowLlmCalls: true,
    timeoutSeconds: 240,
    description: "OpenAI-compatible Fighting provider 路径，使用 Responses API、高推理和关闭存储。",
    budgetHint: "真实调用。用于和 DeepSeek / NewAPI 对比准确率、token、延迟和报告质量。",
    providerOptions: {
      model_provider: "fighting",
      base_url: "http://43.106.115.130:8080/v1",
      wire_api: "responses",
      reasoning_effort: "high",
      disable_response_storage: true,
    },
  },
  {
    id: "custom-api",
    label: "自定义接口",
    taskPath: "custom_tasks/stair-25-hard-token-bucket/task.json",
    mode: "api",
    model: "custom-model",
    allowLlmCalls: true,
    timeoutSeconds: 240,
    description: "填入 OpenAI-compatible base_url、provider 名和模型 ID 后参与同一任务横评。",
    budgetHint: "适合临时接入新的模型渠道；密钥仍由后端环境变量读取。",
    providerOptions: {
      model_provider: "custom",
      base_url: "https://example.com/v1",
      wire_api: "chat_completions",
    },
  },
  {
    id: "retry-context",
    label: "retry with context",
    taskPath: "benchmarks_realistic/retry-429-real/task.json",
    mode: "api",
    model: "deepseek-v4-flash",
    allowLlmCalls: true,
    timeoutSeconds: 180,
    description: "失败上下文重试 profile。运行失败后用“带上下文重试”，看首次尝试和重试差异。",
    budgetHint: "同样受真实调用预算闸门控制；重试指标会进入评测看板。",
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
      ...(profile.providerOptions ?? {}),
      allow_llm_calls: profile.allowLlmCalls,
      timeout_seconds: profile.timeoutSeconds,
    },
    idempotencyKey: `console-eval-${profile.id}`,
  };
}

export function buildFreshIdempotencyKey(prefix: string, now = Date.now()): string {
  return `${prefix}-${now}`;
}
