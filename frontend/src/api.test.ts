import { afterEach, describe, expect, it, vi } from "vitest";
import { createRun } from "./api";

describe("api request headers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves JSON content type when createRun adds an idempotency key", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: 42,
        task_id: 7,
        status: "pending",
        mode: "api",
        model: "deepseek-v4-flash",
        timeout_seconds: 120,
        artifacts: {},
      }),
    } as Response);

    await createRun(
      {
        task_id: 7,
        mode: "api",
        model: "deepseek-v4-flash",
        allow_llm_calls: true,
        timeout_seconds: 120,
      },
      "console-eval-api-retry-429",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "Idempotency-Key": "console-eval-api-retry-429",
        }),
      }),
    );
  });
});
