import { describe, expect, it } from "vitest";
import { buildEvaluationRequest, buildFreshIdempotencyKey, evaluationProfiles } from "./runProfiles";

describe("evaluationProfiles", () => {
  it("offers baseline, real api, and retry evaluation examples", () => {
    expect(evaluationProfiles.map((profile) => profile.id)).toEqual([
      "local-demo",
      "deepseek-api",
      "newapi-5-4",
      "newapi-5-5",
      "openai-fighting",
      "custom-api",
      "retry-context",
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
    expect(request.idempotencyKey).toContain("local-demo");
  });

  it("turns on api mode only for explicit real evaluation profiles", () => {
    const request = buildEvaluationRequest(evaluationProfiles[1]);

    expect(request.task.harness_task_path).toBe("custom_tasks/stair-25-hard-token-bucket/task.json");
    expect(request.run.mode).toBe("api");
    expect(request.run.model).toBe("deepseek-v4-flash");
    expect(request.run.allow_llm_calls).toBe(true);
    expect(request.idempotencyKey).toContain("deepseek-api");
  });

  it("keeps retry profile on the real guarded model path", () => {
    const request = buildEvaluationRequest(evaluationProfiles[6]);

    expect(request.run.mode).toBe("api");
    expect(request.run.model).toBe("deepseek-v4-flash");
    expect(request.run.allow_llm_calls).toBe(true);
    expect(request.idempotencyKey).toContain("retry-context");
  });

  it("passes fighting provider options for OpenAI-compatible runs", () => {
    const request = buildEvaluationRequest(evaluationProfiles[4]);

    expect(request.run.model).toBe("gpt-5.5");
    expect(request.run.model_provider).toBe("fighting");
    expect(request.run.base_url).toBe("http://43.106.115.130:8080/v1");
    expect(request.run.wire_api).toBe("responses");
    expect(request.run.reasoning_effort).toBe("high");
    expect(request.run.disable_response_storage).toBe(true);
  });

  it("passes separate NewAPI provider options for 5.4 and 5.5 runs", () => {
    const gpt54 = buildEvaluationRequest(evaluationProfiles[2]);
    const gpt55 = buildEvaluationRequest(evaluationProfiles[3]);

    expect(gpt54.run.model).toBe("gpt-5.4");
    expect(gpt54.run.model_provider).toBe("newapi-5.4");
    expect(gpt54.run.base_url).toBe("https://api.sbbbbbbbbb.xyz/v1");
    expect(gpt54.run.wire_api).toBe("chat_completions");
    expect(gpt55.run.model).toBe("gpt-5.5");
    expect(gpt55.run.model_provider).toBe("newapi-5.5");
  });

  it("passes custom OpenAI-compatible provider options", () => {
    const request = buildEvaluationRequest(evaluationProfiles[5]);

    expect(request.run.mode).toBe("api");
    expect(request.run.model).toBe("custom-model");
    expect(request.run.model_provider).toBe("custom");
    expect(request.run.base_url).toBe("https://example.com/v1");
    expect(request.run.wire_api).toBe("chat_completions");
  });
});

describe("buildFreshIdempotencyKey", () => {
  it("keeps the profile prefix but changes for each submission", () => {
    const first = buildFreshIdempotencyKey("console-eval-local-demo", 1000);
    const second = buildFreshIdempotencyKey("console-eval-local-demo", 1001);

    expect(first).toContain("console-eval-local-demo");
    expect(first).not.toBe(second);
  });
});
