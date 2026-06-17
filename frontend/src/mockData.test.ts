import { describe, expect, it } from "vitest";
import { demoEvidenceSections, getDemoArtifact } from "./mockData";

describe("getDemoArtifact", () => {
  it("returns distinct offline content for each artifact tab", () => {
    const report = getDemoArtifact("report");
    const patch = getDemoArtifact("patch");
    const scorecard = getDemoArtifact("scorecard");
    const testResult = getDemoArtifact("test-result");
    const trace = getDemoArtifact("trace");

    expect(report).toContain("<h1>OpenAgent Run Report</h1>");
    expect(patch).toContain("diff --git");
    expect(patch).toContain("RETRYABLE_STATUSES = {429, 500, 502, 503, 504}");
    expect(scorecard).toContain('"pass_rate": 1');
    expect(scorecard).toContain('"score": 100');
    expect(testResult).toContain("4 passed in 0.02s");
    expect(trace).toContain('"phase": "verify"');
    expect(new Set([report, patch, scorecard, testResult, trace]).size).toBe(5);
  });
});

describe("demoEvidenceSections", () => {
  it("uses project-facing sections instead of interview script wording", () => {
    expect(demoEvidenceSections.map((section) => section.title)).toEqual(["项目亮点", "技术难点", "演示路径"]);
    expect(demoEvidenceSections.some((section) => section.items.some((item) => item.includes("面试讲解口径")))).toBe(false);
  });
});
