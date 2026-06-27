import type { AgentRunArtifact, CostMetrics, DemoState, DemoStatus, EvaluationCreateResult, EvaluationHistoryItem, EvaluationMatrix, EvaluationMemorySummary, EvaluationSummary, FailureContext, Run, RunCatalogItem, RunSource } from "./domain";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export type ApiWorkspaceContext = {
  tenantId: string;
  workspaceId: string;
};

let workspaceContext: ApiWorkspaceContext = {
  tenantId: "default",
  workspaceId: "interview-demo",
};

export function setApiWorkspaceContext(next: ApiWorkspaceContext): void {
  workspaceContext = {
    tenantId: next.tenantId.trim() || "default",
    workspaceId: next.workspaceId.trim() || "default",
  };
}

export function getApiWorkspaceContext(): ApiWorkspaceContext {
  return workspaceContext;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-ID": workspaceContext.tenantId,
      "X-Workspace-ID": workspaceContext.workspaceId,
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type CreateTaskInput = {
  name: string;
  description: string;
  harness_task_path: string;
};

export type CreateRunInput = {
  task_id: number;
  mode: "local" | "api";
  model: string;
  model_provider?: string | null;
  base_url?: string | null;
  wire_api?: "chat_completions" | "responses" | null;
  reasoning_effort?: string | null;
  disable_response_storage?: boolean;
  allow_llm_calls: boolean;
  timeout_seconds: number;
};

export type CreateCustomTaskInput = {
  name: string;
  goal: string;
  source_filename: string;
  source_code: string;
  test_filename: string;
  test_code: string;
  acceptance_command: string;
};

export type EvaluationTaskFileInput = {
  path: string;
  content: string;
};

export type EvaluationModelProfileInput = {
  name: string;
  mode: "local" | "api";
  model: string;
  model_provider?: string | null;
  base_url?: string | null;
  wire_api?: "chat_completions" | "responses" | null;
  reasoning_effort?: string | null;
  disable_response_storage?: boolean;
  allow_llm_calls?: boolean;
  timeout_seconds?: number;
};

export type CreateEvaluationInput = {
  name: string;
  goal: string;
  files: EvaluationTaskFileInput[];
  test_files: EvaluationTaskFileInput[];
  model_profiles: EvaluationModelProfileInput[];
  acceptance_command?: string;
  context_summary_files?: number;
};

export type EvaluationDraftInput = {
  source_code: string;
  source_filename?: string;
  instruction?: string;
  current_name?: string;
  current_goal?: string;
  current_test_code?: string;
};

export type EvaluationDraft = {
  name: string;
  goal: string;
  source_filename: string;
  source_code: string;
  test_filename: string;
  test_code: string;
  acceptance_command: string;
  difficulty: {
    difficulty_level: "easy" | "medium" | "hard" | string;
    difficulty_score: number;
    reasons: string[];
    risk_factors: string[];
    suggested_strategy: {
      notes?: string[];
      [key: string]: unknown;
    };
  };
  difficulty_level: "easy" | "medium" | "hard" | string;
  difficulty_score: number;
  difficulty_reasons: string[];
  risk_factors: string[];
  suggested_strategy: {
    notes?: string[];
    [key: string]: unknown;
  };
  analysis_steps: string[];
  findings: string[];
  suggested_changes: string[];
  confidence: string;
};

export type RetryRunInput = {
  allow_llm_calls: boolean;
  timeout_seconds?: number;
  use_failure_context?: boolean;
};

export async function createTask(input: CreateTaskInput) {
  return request<{ task_id: number }>("/tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function createCustomTask(input: CreateCustomTaskInput) {
  return request<{ task_id: number; harness_task_path: string }>("/custom-tasks", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function createEvaluation(input: CreateEvaluationInput, idempotencyKey?: string): Promise<EvaluationCreateResult> {
  return request<EvaluationCreateResult>("/evaluations", {
    method: "POST",
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    body: JSON.stringify(input),
  });
}

export async function createEvaluationDraft(input: EvaluationDraftInput): Promise<EvaluationDraft> {
  return request<EvaluationDraft>("/evaluation-drafts", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function createRun(input: CreateRunInput, idempotencyKey = `console-${Date.now()}`): Promise<Run> {
  return request<Run>("/runs", {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(input),
  });
}

export async function retryRun(runId: number, input: RetryRunInput): Promise<Run> {
  return request<Run>(`/runs/${runId}/retry`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getRun(runId: number): Promise<Run> {
  return request<Run>(`/runs/${runId}`);
}

export async function listRuns(limit = 200): Promise<RunCatalogItem[]> {
  return request<RunCatalogItem[]>(`/runs?limit=${limit}`);
}

export async function listEvaluationHistory(): Promise<EvaluationHistoryItem[]> {
  return request<EvaluationHistoryItem[]>("/evaluations/history");
}

export async function getEvaluationMatrix(evaluationId: number): Promise<EvaluationMatrix> {
  return request<EvaluationMatrix>(`/evaluations/${evaluationId}/matrix`);
}

export async function deleteEvaluation(taskId: number): Promise<{ status: string; task_id: number; deleted_runs: number; deleted_usage: number }> {
  return request<{ status: string; task_id: number; deleted_runs: number; deleted_usage: number }>(`/evaluations/${taskId}`, {
    method: "DELETE",
  });
}

export async function getRunSource(runId: number): Promise<RunSource> {
  return request<RunSource>(`/runs/${runId}/source`);
}

export async function getFailureContext(runId: number): Promise<FailureContext> {
  return request<FailureContext>(`/runs/${runId}/failure-context`);
}

export async function getAgentRunArtifact(runId: number): Promise<AgentRunArtifact> {
  return request<AgentRunArtifact>(`/runs/${runId}/agent-run`);
}

export async function cancelRun(runId: number): Promise<Run> {
  return request<Run>(`/runs/${runId}/cancel`, { method: "POST" });
}

export async function getCostMetrics(): Promise<CostMetrics> {
  return request<CostMetrics>("/metrics/cost");
}

export async function getEvaluationSummary(): Promise<EvaluationSummary> {
  return request<EvaluationSummary>("/evaluation/summary");
}

export async function getEvaluationMemorySummary(): Promise<EvaluationMemorySummary> {
  return request<EvaluationMemorySummary>("/memory/evaluation/summary");
}

export async function getDemoStatus(): Promise<DemoStatus> {
  return request<DemoStatus>("/demo/status");
}

export async function getDemoState(): Promise<DemoState> {
  return request<DemoState>("/demo/state");
}

export async function getArtifact(runId: number, kind: string): Promise<string> {
  const response = await fetch(`${API_BASE}/runs/${runId}/${kind}`, {
    headers: {
      "X-Tenant-ID": workspaceContext.tenantId,
      "X-Workspace-ID": workspaceContext.workspaceId,
    },
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.text();
}
