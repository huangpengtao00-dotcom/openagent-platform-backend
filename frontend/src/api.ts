import type { CostMetrics, Run } from "./domain";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
  allow_llm_calls: boolean;
  timeout_seconds: number;
};

export async function createTask(input: CreateTaskInput) {
  return request<{ task_id: number }>("/tasks", {
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

export async function getRun(runId: number): Promise<Run> {
  return request<Run>(`/runs/${runId}`);
}

export async function cancelRun(runId: number): Promise<Run> {
  return request<Run>(`/runs/${runId}/cancel`, { method: "POST" });
}

export async function getCostMetrics(): Promise<CostMetrics> {
  return request<CostMetrics>("/metrics/cost");
}

export async function getArtifact(runId: number, kind: string): Promise<string> {
  const response = await fetch(`${API_BASE}/runs/${runId}/${kind}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.text();
}
