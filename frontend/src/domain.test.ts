import { describe, expect, it } from "vitest";
import { dataSourceLabel, formatCurrency, formatTokens, runTimeline, stableRunKey, statusTone } from "./domain";

describe("statusTone", () => {
  it("maps known run statuses to stable console tones", () => {
    expect(statusTone("pending")).toBe("queued");
    expect(statusTone("running")).toBe("active");
    expect(statusTone("pass")).toBe("success");
    expect(statusTone("fail")).toBe("danger");
    expect(statusTone("timeout")).toBe("warning");
    expect(statusTone("cancelled")).toBe("muted");
  });
});

describe("formatTokens", () => {
  it("formats token counts with compact separators", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(1500)).toBe("1,500");
  });
});

describe("formatCurrency", () => {
  it("keeps tiny demo costs readable", () => {
    expect(formatCurrency(0)).toBe("$0.00000");
    expect(formatCurrency(0.00066)).toBe("$0.00066");
    expect(formatCurrency(1.2)).toBe("$1.20000");
  });
});

describe("dataSourceLabel", () => {
  it("uses interview-friendly labels for data source state", () => {
    expect(dataSourceLabel("sample")).toBe("示例数据");
    expect(dataSourceLabel("live")).toBe("实时接口");
    expect(dataSourceLabel("offline")).toBe("离线展示");
  });
});

describe("stableRunKey", () => {
  it("keeps demo run creation idempotent for the same task/mode/model", () => {
    expect(stableRunKey(1, "local", "scripted")).toBe(stableRunKey(1, "local", "scripted"));
    expect(stableRunKey(1, "local", "scripted")).not.toBe(stableRunKey(1, "api", "scripted"));
  });
});

describe("runTimeline", () => {
  it("marks terminal states as the final current step", () => {
    expect(runTimeline("pass").map((step) => step.state)).toEqual(["done", "done", "current"]);
    expect(runTimeline("cancelled")[2]).toMatchObject({ status: "cancelled", state: "current" });
  });
});
