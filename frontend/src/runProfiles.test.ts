import { describe, expect, it } from "vitest";
import { buildEvaluationRequest, evaluationProfiles } from "./runProfiles";

describe("evaluationProfiles", () => {
  it("offers both safe scripted and real api evaluation examples", () => {
    expect(evaluationProfiles.map((profile) => profile.id)).toEqual([
      "scripted-retry-429",
      "api-retry-429",
      "api-config-loader",
    ]);
  });

  it("keeps task paths relative to the allowed Harness root", () => {
    for (const profile of evaluationProfiles) {
      expect(profile.taskPath).not.toMatch(/^[A-Za-z]:\\/);
      expect(profile.taskPath).not.toContain("..");
      expect(profile.taskPath.endsWith("task.json")).toBe(true);
    }
  });
});

describe("buildEvaluationRequest", () => {
  it("keeps scripted evaluation in no-spend mode", () => {
    const request = buildEvaluationRequest(evaluationProfiles[0]);

    expect(request.run.mode).toBe("local");
    expect(request.run.model).toBe("scripted");
    expect(request.run.allow_llm_calls).toBe(false);
    expect(request.idempotencyKey).toContain("scripted-retry-429");
  });

  it("turns on api mode only for explicit real evaluation profiles", () => {
    const request = buildEvaluationRequest(evaluationProfiles[1]);

    expect(request.task.harness_task_path).toBe("examples/deepseek_real_task.json");
    expect(request.run.mode).toBe("api");
    expect(request.run.model).toBe("deepseek-v4-flash");
    expect(request.run.allow_llm_calls).toBe(true);
    expect(request.idempotencyKey).toContain("api-retry-429");
  });
});
