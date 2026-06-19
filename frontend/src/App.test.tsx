import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("App custom task flow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not submit a real API run after creating a custom task while the backend LLM gate is disabled", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/demo/status") {
        return jsonResponse({
          status: "ok",
          harness_root: "C:/bundle/02_OpenAgent_Harness",
          harness_exists: true,
          allow_real_llm_calls: false,
          harness_runs_root: "C:/bundle/artifacts/harness_runs",
        });
      }
      if (url === "/api/runs") {
        return jsonResponse([]);
      }
      if (url === "/api/custom-tasks") {
        return jsonResponse({ task_id: 12, harness_task_path: "custom_tasks/custom-config-merge/task.json" });
      }
      return jsonResponse({});
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Custom Task" }));
    await screen.findByText("Create a tiny isolated Harness task from source code, tests, and an acceptance command.");
    fireEvent.click(screen.getByRole("button", { name: /Create custom task/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/custom-tasks", expect.objectContaining({ method: "POST" }));
    });
    expect(fetchMock).not.toHaveBeenCalledWith("/api/runs", expect.objectContaining({ method: "POST" }));
  });

  it("refreshes demo status before deciding whether a custom task can submit a real API run", async () => {
    let statusCalls = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/demo/status") {
        statusCalls += 1;
        if (statusCalls === 1) {
          return new Promise<Response>(() => {
            // Leave the initial mount status request pending to simulate a fast user click.
          });
        }
        return jsonResponse({
          status: "ok",
          harness_root: "C:/bundle/02_OpenAgent_Harness",
          harness_exists: true,
          allow_real_llm_calls: true,
          harness_runs_root: "C:/bundle/artifacts/harness_runs",
        });
      }
      if (url === "/api/runs" && init?.method !== "POST") {
        return jsonResponse([]);
      }
      if (url === "/api/custom-tasks") {
        return jsonResponse({ task_id: 12, harness_task_path: "custom_tasks/custom-config-merge/task.json" });
      }
      if (url === "/api/runs" && init?.method === "POST") {
        return jsonResponse({
          run_id: 44,
          task_id: 12,
          status: "pending",
          mode: "api",
          model: "deepseek-v4-flash",
          timeout_seconds: 180,
          harness_run_id: null,
          artifacts_dir: null,
          failure_type: null,
          error_message: null,
          created_at: "2026-06-19T12:00:00",
          started_at: null,
          finished_at: null,
          usage: null,
          artifacts: {},
        });
      }
      return jsonResponse({});
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Custom Task" }));
    await screen.findByText("Create a tiny isolated Harness task from source code, tests, and an acceptance command.");
    fireEvent.click(screen.getByRole("button", { name: /Create custom task/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/runs", expect.objectContaining({ method: "POST" }));
    });
  });
});
