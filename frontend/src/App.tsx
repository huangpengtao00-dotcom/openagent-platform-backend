import { useEffect, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  FileCode2,
  Gauge,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Square,
  TerminalSquare,
  Wifi,
  Workflow,
} from "lucide-react";
import {
  cancelRun,
  createEvaluationDraft,
  createEvaluation,
  deleteEvaluation,
  getAgentRunArtifact,
  getArtifact,
  getCostMetrics,
  getDemoStatus,
  getDemoState,
  getEvaluationMatrix,
  getEvaluationMemorySummary,
  getEvaluationSummary,
  getRun,
  getRunSource,
  listEvaluationHistory,
  listRuns,
  retryRun,
  setApiWorkspaceContext,
  type EvaluationDraft,
} from "./api";
import { demoArtifact, demoCost, demoEvaluation, demoMemorySummary, demoRun, getDemoArtifact, type ArtifactKind } from "./mockData";
import { evaluationProfiles, type EvaluationProfile } from "./runProfiles";
import {
  formatCurrency,
  formatPercent,
  formatTokens,
  runTimeline,
  statusTone,
  type CostMetrics,
  type AgentRunArtifact,
  type DemoState,
  type DemoStatus,
  type EvaluationMemorySummary,
  type EvaluationMatrix,
  type EvaluationSummary,
  type EvaluationHistoryItem,
  type Run,
  type RunCatalogItem,
  type RunSource,
} from "./domain";

type NavItem = "overview" | "evaluate" | "history" | "runs" | "artifacts" | "cost";
type ProfileId = EvaluationProfile["id"];

const navItems: Array<{ id: NavItem; label: string }> = [
  { id: "overview", label: "看板" },
  { id: "evaluate", label: "新建评测" },
  { id: "history", label: "历史" },
  { id: "runs", label: "运行" },
  { id: "artifacts", label: "证据" },
  { id: "cost", label: "成本" },
];

const artifactKinds: ArtifactKind[] = ["report", "scorecard", "patch", "test-result", "trace"];

const artifactLabels: Record<ArtifactKind, string> = {
  report: "报告",
  scorecard: "评分卡",
  patch: "补丁",
  "test-result": "测试结果",
  trace: "轨迹",
};

type CustomTaskDraft = {
  difficulty?: "简单" | "中等" | "困难";
  name: string;
  goal: string;
  source_filename: string;
  source_code: string;
  test_filename: string;
  test_code: string;
  acceptance_command: string;
};

const customExamples: CustomTaskDraft[] = [
  {
    difficulty: "简单",
    name: "时长解析任务",
    goal: "当 duration_seconds 缺失或格式错误时返回 0，而不是抛出异常。",
    source_filename: "duration_parser.py",
    source_code: `def parse_duration(payload):
    return int(payload["duration_seconds"])
`,
    test_filename: "test_duration_parser.py",
    test_code: `from duration_parser import parse_duration


def test_reads_integer_duration():
    assert parse_duration({"duration_seconds": "12"}) == 12


def test_missing_duration_is_zero():
    assert parse_duration({}) == 0


def test_malformed_duration_is_zero():
    assert parse_duration({"duration_seconds": "soon"}) == 0
`,
    acceptance_command: "python -m pytest -q",
  },
  {
    difficulty: "中等",
    name: "配置合并任务",
    goal: "修复 load_config，让嵌套 headers/retry 合并时保留默认值，允许用户覆盖 timeout，并且不修改 DEFAULTS。",
    source_filename: "config_loader.py",
    source_code: `DEFAULTS = {
    "timeout_seconds": 5,
    "headers": {"accept": "application/json"},
    "retry": {"max_attempts": 3, "statuses": [429, 500, 502, 503]},
}


def load_config(user_config):
    config = DEFAULTS.copy()
    if user_config:
        config.update(user_config)
    return config
`,
    test_filename: "test_config_loader.py",
    test_code: `from config_loader import DEFAULTS, load_config


def test_nested_headers_keep_defaults():
    config = load_config({"headers": {"authorization": "Bearer test"}})
    assert config["headers"]["authorization"] == "Bearer test"
    assert config["headers"]["accept"] == "application/json"


def test_nested_retry_keeps_default_statuses_and_overrides_attempts():
    config = load_config({"retry": {"max_attempts": 5}})
    assert config["retry"]["max_attempts"] == 5
    assert 429 in config["retry"]["statuses"]


def test_defaults_are_not_mutated():
    load_config({"headers": {"x-debug": "1"}, "retry": {"statuses": [418]}})
    assert "x-debug" not in DEFAULTS["headers"]
    assert DEFAULTS["retry"]["statuses"] == [429, 500, 502, 503]
`,
    acceptance_command: "python -m pytest -q",
  },
  {
    difficulty: "困难",
    name: "产物查询 API 任务",
    goal: "修复 search_artifacts，让它支持状态、作者、标签、关键词、limit 组合过滤，并按 created_at 倒序返回，同时不能修改原始 ARTIFACTS。",
    source_filename: "artifact_api.py",
    source_code: `ARTIFACTS = [
    {"id": 1, "name": "retry report", "status": "pass", "owner": "platform", "tags": ["retry", "api"], "created_at": "2026-06-20T10:00:00"},
    {"id": 2, "name": "cost trace", "status": "fail", "owner": "eval", "tags": ["cost", "trace"], "created_at": "2026-06-21T09:30:00"},
    {"id": 3, "name": "agent loop scorecard", "status": "pass", "owner": "eval", "tags": ["agent", "score"], "created_at": "2026-06-22T08:00:00"},
]


def search_artifacts(filters):
    results = ARTIFACTS
    if "status" in filters:
        results = [item for item in results if item["status"] == filters["status"]]
    if "owner" in filters:
        results = [item for item in results if item["owner"] == filters["owner"]]
    return results
`,
    test_filename: "test_artifact_api.py",
    test_code: `from artifact_api import ARTIFACTS, search_artifacts


def test_filters_status_owner_and_keyword_case_insensitive():
    result = search_artifacts({"status": "PASS", "owner": "EVAL", "keyword": "loop"})
    assert [item["id"] for item in result] == [3]


def test_filters_all_requested_tags():
    result = search_artifacts({"tags": ["trace", "cost"]})
    assert [item["id"] for item in result] == [2]


def test_sorts_newest_first_and_applies_limit():
    result = search_artifacts({"limit": 2})
    assert [item["id"] for item in result] == [3, 2]


def test_does_not_mutate_original_artifacts():
    before = list(ARTIFACTS)
    search_artifacts({"limit": 1, "tags": ["api"]})
    assert ARTIFACTS == before
`,
    acceptance_command: "python -m pytest -q",
  },
];

const defaultCustom = customExamples[0];

type CustomModelConfig = {
  label: string;
  provider: string;
  model: string;
  baseUrl: string;
  wireApi: "chat_completions" | "responses";
};

const defaultCustomModel: CustomModelConfig = {
  label: "自定义接口",
  provider: "custom",
  model: "custom-model",
  baseUrl: "https://example.com/v1",
  wireApi: "chat_completions",
};

export function formatRunTaskIdentity(run: Pick<Run, "run_id" | "task_id">): string {
  return `run #${run.run_id} -> task #${run.task_id}`;
}

export function buildCustomTaskClipboardText(custom: CustomTaskDraft): string {
  return [
    `任务名称: ${custom.name}`,
    "",
    `目标: ${custom.goal}`,
    "",
    `源码文件: ${custom.source_filename}`,
    "源码:",
    custom.source_code.trimEnd(),
    "",
    `测试文件: ${custom.test_filename}`,
    "测试代码:",
    custom.test_code.trimEnd(),
    "",
    `验收命令: ${custom.acceptance_command}`,
  ].join("\n");
}

function trimTemplateBlock(lines: string[]): string {
  const next = [...lines];
  while (next.length > 0 && next[0].trim() === "") {
    next.shift();
  }
  while (next.length > 0 && next[next.length - 1].trim() === "") {
    next.pop();
  }
  return next.join("\n");
}

function findLabelLine(lines: string[], labels: string[]): number {
  return lines.findIndex((line) => labels.some((label) => line.trimStart().startsWith(`${label}:`)));
}

function readInlineLabel(lines: string[], labels: string[]): string {
  const index = findLabelLine(lines, labels);
  if (index < 0) {
    return "";
  }
  const line = lines[index].trimStart();
  for (const label of labels) {
    const prefix = `${label}:`;
    if (line.startsWith(prefix)) {
      return line.slice(prefix.length).trim();
    }
  }
  return "";
}

function findSectionLine(lines: string[], labels: string[]): number {
  return lines.findIndex((line) => labels.some((label) => line.trim() === `${label}:`));
}

export function parseCustomTaskClipboardText(text: string): CustomTaskDraft | null {
  const lines = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const sourceStart = findSectionLine(lines, ["源码", "Source code"]);
  const testFileIndex = findLabelLine(lines, ["测试文件", "Test file"]);
  const testCodeStart = findSectionLine(lines, ["测试代码", "Test code"]);
  const acceptanceIndex = findLabelLine(lines, ["验收命令", "Acceptance command"]);

  if (sourceStart < 0 || testFileIndex < 0 || testCodeStart < 0 || acceptanceIndex < 0 || !(sourceStart < testFileIndex && testFileIndex < testCodeStart && testCodeStart < acceptanceIndex)) {
    return null;
  }

  const draft: CustomTaskDraft = {
    name: readInlineLabel(lines, ["任务名称", "Task name"]),
    goal: readInlineLabel(lines, ["目标", "Goal"]),
    source_filename: readInlineLabel(lines, ["源码文件", "Source file"]),
    source_code: trimTemplateBlock(lines.slice(sourceStart + 1, testFileIndex)),
    test_filename: readInlineLabel(lines, ["测试文件", "Test file"]),
    test_code: trimTemplateBlock(lines.slice(testCodeStart + 1, acceptanceIndex)),
    acceptance_command: readInlineLabel(lines, ["验收命令", "Acceptance command"]),
  };

  return Object.values(draft).every((value) => value.trim().length > 0) ? draft : null;
}

export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to document.execCommand for older browser contexts.
  }

  if (typeof document === "undefined" || !document.body) {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(textarea);
  }
}

export function confirmFailureContextRetry(run: Run, confirmFn: (message: string) => boolean = (message) => window.confirm(message)): boolean {
  if (!["fail", "timeout", "cancelled"].includes(run.status)) {
    return false;
  }
  return confirmFn(
    [
      `确认基于 run #${run.run_id} 的失败证据重试吗？`,
      "",
      "平台会把 trace、test-result、scorecard、patch 和 report 摘要写入 failure_context.json，再交给模型重试。",
      "这样重试对比会基于真实运行证据，而不是凭空再跑一次。",
    ].join("\n"),
  );
}

type TaskRunGroup = {
  task_id: number;
  task_name: string;
  task_description: string;
  latest_run_id: number;
  latest_created_at: string;
  runs: RunCatalogItem[];
  passed: number;
  active: number;
  total_tokens: number;
  estimated_cost_usd: number;
};

function isLocalBaselineRun(item: Pick<Run, "mode" | "model" | "model_provider">): boolean {
  const label = `${item.model_provider ?? ""} ${item.model}`.toLowerCase();
  return item.mode === "local" || label.includes("scripted");
}

function displayRunModel(item: Pick<Run, "model" | "model_provider">): string {
  return item.model_provider || item.model;
}

function groupRunsByTask(runs: RunCatalogItem[]): TaskRunGroup[] {
  const buckets = new Map<number, RunCatalogItem[]>();
  for (const item of runs) {
    buckets.set(item.task_id, [...(buckets.get(item.task_id) ?? []), item]);
  }

  return Array.from(buckets.entries())
    .map(([taskId, items]) => {
      const sortedRuns = [...items].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      const latest = sortedRuns[0];
      return {
        task_id: taskId,
        task_name: latest?.task_name ?? `task #${taskId}`,
        task_description: latest?.task_description ?? "",
        latest_run_id: latest?.run_id ?? 0,
        latest_created_at: latest?.created_at ?? "",
        runs: sortedRuns,
        passed: sortedRuns.filter((item) => item.status === "pass").length,
        active: sortedRuns.filter((item) => item.status === "pending" || item.status === "running").length,
        total_tokens: sortedRuns.reduce((sum, item) => sum + (item.usage?.total_tokens ?? 0), 0),
        estimated_cost_usd: sortedRuns.reduce((sum, item) => sum + (item.usage?.estimated_cost_usd ?? 0), 0),
      };
    })
    .sort((a, b) => new Date(b.latest_created_at).getTime() - new Date(a.latest_created_at).getTime());
}

function matrixFromHistoryItem(item: EvaluationHistoryItem): EvaluationMatrix {
  return {
    evaluation_id: item.evaluation_id ?? item.task_id,
    name: item.name,
    goal: item.description,
    status: item.status,
    task_count: 1,
    model_count: item.model_count,
    run_count: item.run_count,
    passed: item.passed,
    failed: item.failed,
    pending: item.pending,
    running: item.running,
    pass_rate: item.pass_rate,
    total_tokens: item.total_tokens,
    estimated_cost_usd: item.estimated_cost_usd,
    created_at: item.created_at,
    tasks: [
      {
        task_id: item.task_id,
        task_name: item.name,
        task_description: item.description,
        models: item.runs.map((run) => ({
          run_id: run.run_id,
          status: run.status,
          model: run.model,
          model_provider: run.model_provider,
          failure_type: run.failure_type,
          error_message: run.error_message,
          total_tokens: run.total_tokens,
          estimated_cost_usd: run.estimated_cost_usd,
          duration_seconds: null,
          artifacts_dir: null,
        })),
      },
    ],
  };
}

function taskGroupTone(group: TaskRunGroup): string {
  if (group.active > 0) {
    return "active";
  }
  if (group.passed === group.runs.length && group.runs.length > 0) {
    return "success";
  }
  if (group.passed > 0) {
    return "warning";
  }
  return "danger";
}

function App() {
  const [active, setActive] = useState<NavItem>("overview");
  const [run, setRun] = useState<Run>(demoRun);
  const [cost, setCost] = useState<CostMetrics>(demoCost);
  const [evaluation, setEvaluation] = useState<EvaluationSummary>(demoEvaluation);
  const [memorySummary, setMemorySummary] = useState<EvaluationMemorySummary>(demoMemorySummary);
  const [artifactKind, setArtifactKind] = useState<ArtifactKind>("scorecard");
  const [artifact, setArtifact] = useState(demoArtifact);
  const [runIdInput, setRunIdInput] = useState("1");
  const [runCatalog, setRunCatalog] = useState<RunCatalogItem[]>([]);
  const [history, setHistory] = useState<EvaluationHistoryItem[]>([]);
  const [matrix, setMatrix] = useState<EvaluationMatrix | null>(null);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyStatusFilter, setHistoryStatusFilter] = useState("all");
  const [sourceSnapshot, setSourceSnapshot] = useState<RunSource | null>(null);
  const [sourceFile, setSourceFile] = useState("");
  const [agentRun, setAgentRun] = useState<AgentRunArtifact | null>(null);
  const [notice, setNotice] = useState("已加载示例证据。启动后端后可刷新真实运行。");
  const [busy, setBusy] = useState(false);
  const [evaluationProfileIds, setEvaluationProfileIds] = useState<ProfileId[]>(["deepseek-api", "newapi-5-4", "newapi-5-5"]);
  const [custom, setCustom] = useState(defaultCustom);
  const [customModel, setCustomModel] = useState<CustomModelConfig>(defaultCustomModel);
  const [draft, setDraft] = useState<EvaluationDraft | null>(null);
  const [draftInstruction, setDraftInstruction] = useState("");
  const [showAdvancedDraft, setShowAdvancedDraft] = useState(false);
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [demoState, setDemoState] = useState<DemoState | null>(null);
  const [demoStateError, setDemoStateError] = useState<string | null>(null);
  const [allowRealLlmIntent, setAllowRealLlmIntent] = useState(true);
  const evaluationSubmitKey = useRef<{ fingerprint: string; key: string } | null>(null);

  const serverAllowsRealLlm = demoStatus?.allow_real_llm_calls === true;
  const timeline = runTimeline(run.status);
  const failure = explainFailure(run);
  const pageHeading = pageTitle(active);
  const visibleProfiles = evaluationProfiles.filter((profile) => profile.id !== "retry-context");

  useEffect(() => {
    setApiWorkspaceContext({ tenantId: "default", workspaceId: "interview-demo" });
    void refreshDemoStatus(false);
    void handleRefreshDemoState(false);
    void handleRefreshRunCatalog(false);
    void handleRefreshHistory(false);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void handleRefreshDemoState(false);
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  async function runLive<T>(action: () => Promise<T>, onSuccess: (value: T) => void, message: string | ((value: T) => string)) {
    setBusy(true);
    try {
      const value = await action();
      onSuccess(value);
      setNotice(typeof message === "function" ? message(value) : message);
    } catch (error) {
      setNotice(error instanceof Error ? `接口调用失败：${error.message}` : "接口调用失败，请检查后端服务。");
    } finally {
      setBusy(false);
    }
  }

  async function refreshDemoStatus(showNotice = true) {
    try {
      const status = await getDemoStatus();
      setDemoStatus(status);
      if (showNotice) {
        setNotice(status.allow_real_llm_calls ? "后端允许真实模型调用。" : "后端真实模型闸门关闭；API profile 会以 allow_llm_calls=false 排队。");
      }
    } catch (error) {
      if (showNotice) {
        setNotice(error instanceof Error ? `无法读取运行时状态：${error.message}` : "无法读取运行时状态。");
      }
    }
  }

  async function handleRefreshDemoState(showNotice = true) {
    try {
      const state = await getDemoState();
      setDemoState(state);
      setDemoStateError(null);
      if (showNotice) {
        setNotice(`运行态已刷新：${state.tasks.count} 个任务，${state.runs.count} 个运行。`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "运行态接口不可用。";
      setDemoStateError(message);
      if (showNotice) {
        setNotice(`无法刷新运行态：${message}`);
      }
    }
  }

  function syncRunCatalog(items: RunCatalogItem[]) {
    setRunCatalog(items);
    const selectedRunId = Number(runIdInput || run.run_id);
    const selected = items.find((item) => item.run_id === selectedRunId);
    if (selected) {
      setRun(selected);
      return;
    }
    const latest = items[0];
    if (latest) {
      setRun(latest);
      setRunIdInput(String(latest.run_id));
      setAgentRun(null);
    }
  }

  async function handleRefreshRunCatalog(showNotice = true) {
    if (!showNotice) {
      try {
        syncRunCatalog(await listRuns());
      } catch {
        // Keep sample data when backend is offline.
      }
      return;
    }
    await runLive(listRuns, syncRunCatalog, "运行目录已刷新。");
  }

  async function handleRefreshHistory(showNotice = true) {
    if (!showNotice) {
      try {
        setHistory(await listEvaluationHistory());
      } catch {
        // Keep sample state when backend is offline.
      }
      return;
    }
    await runLive(listEvaluationHistory, setHistory, "历史评测已刷新。");
  }

  async function handleOpenEvaluationMatrix(evaluationId: number | null | undefined) {
    if (!evaluationId) {
      setNotice("这条历史记录还没有 evaluation_id，可能是旧数据；可以用运行页按 task 查看横向对比。");
      return;
    }
    await runLive(
      () => getEvaluationMatrix(evaluationId),
      (value) => {
        setMatrix(value);
        setActive("runs");
      },
      (value) => `已打开 Evaluation #${value.evaluation_id} 的结果矩阵。`,
    );
  }

  async function handleOpenHistoryMatrix(item: EvaluationHistoryItem) {
    if (item.evaluation_id) {
      await handleOpenEvaluationMatrix(item.evaluation_id);
      return;
    }
    setMatrix(matrixFromHistoryItem(item));
    setActive("runs");
    setNotice(`已用历史 run 生成任务 #${item.task_id} 的兼容结果矩阵。`);
  }

  async function handleDeleteEvaluation(taskId: number) {
    const item = history.find((entry) => entry.task_id === taskId);
    if (!window.confirm(`确认删除评测任务「${item?.name ?? taskId}」吗？\n会移除这条评测下的 run 记录；已生成的本地 artifact 文件会保留。`)) {
      return;
    }
    await runLive(
      () => deleteEvaluation(taskId),
      () => {
        setHistory((items) => items.filter((entry) => entry.task_id !== taskId));
        void handleRefreshRunCatalog(false);
        void handleRefreshDemoState(false);
      },
      (value) => `已删除评测任务 #${value.task_id}，移除 ${value.deleted_runs} 条 run 记录。`,
    );
  }

  async function handleRefreshEvaluation() {
    await runLive(
      async () => ({
        evaluation: await getEvaluationSummary(),
        memory: await getEvaluationMemorySummary(),
      }),
      (value) => {
        setEvaluation(value.evaluation);
        setMemorySummary(value.memory);
        void handleRefreshRunCatalog(false);
        void handleRefreshDemoState(false);
        void handleRefreshHistory(false);
      },
      "评测汇总已刷新。",
    );
  }

  async function handleSelectRun(runId: number) {
    setRunIdInput(String(runId));
    await runLive(
      async () => {
        const nextRun = await getRun(runId);
        try {
          setAgentRun(await getAgentRunArtifact(runId));
        } catch {
          setAgentRun(null);
        }
        return nextRun;
      },
      (value) => {
        setRun(value);
        setActive("runs");
      },
      `已选择 run #${runId}。`,
    );
  }

  async function handleCreateEvaluation() {
    const selectedProfiles = visibleProfiles.filter((profile) => evaluationProfileIds.includes(profile.id));
    if (selectedProfiles.length === 0) {
      setNotice("提交前至少选择一个模型 profile。");
      return;
    }

    await runLive(
      async () => {
        const status = demoStatus ?? await getDemoStatus();
        setDemoStatus(status);
        const allowApiCalls = allowRealLlmIntent && status.allow_real_llm_calls;
        const input = {
          name: custom.name,
          goal: custom.goal,
          files: [{ path: custom.source_filename, content: custom.source_code }],
          test_files: [{ path: custom.test_filename, content: custom.test_code }],
          model_profiles: selectedProfiles.map((profile) => {
            const isCustomApi = profile.id === "custom-api";
            return {
              name: isCustomApi ? customModel.label.trim() || profile.label : profile.label,
              mode: profile.mode,
              model: isCustomApi ? customModel.model.trim() || profile.model : profile.model,
              model_provider: isCustomApi ? customModel.provider.trim() || "custom" : profile.providerOptions?.model_provider ?? profile.label,
              base_url: isCustomApi ? customModel.baseUrl.trim() || undefined : profile.providerOptions?.base_url,
              wire_api: isCustomApi ? customModel.wireApi : profile.providerOptions?.wire_api,
              reasoning_effort: profile.providerOptions?.reasoning_effort,
              disable_response_storage: profile.providerOptions?.disable_response_storage,
              allow_llm_calls: profile.mode === "api" ? allowApiCalls : false,
              timeout_seconds: profile.timeoutSeconds,
            };
          }),
          acceptance_command: custom.acceptance_command,
          context_summary_files: 16,
        };
        const fingerprint = JSON.stringify({ input, profiles: selectedProfiles.map((profile) => profile.id) });
        if (!evaluationSubmitKey.current || evaluationSubmitKey.current.fingerprint !== fingerprint) {
          evaluationSubmitKey.current = {
            fingerprint,
            key: `console-evaluation-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          };
        }
        return createEvaluation(input, evaluationSubmitKey.current.key);
      },
      (result) => {
        evaluationSubmitKey.current = null;
        const firstRun = result.runs[0];
        if (firstRun) {
          setRun(firstRun);
          setRunIdInput(String(firstRun.run_id));
          setAgentRun(null);
        }
        if (result.evaluation_id) {
          void handleOpenEvaluationMatrix(result.evaluation_id);
        }
        setActive("runs");
        void handleRefreshRunCatalog(false);
        void handleRefreshDemoState(false);
        void handleRefreshHistory(false);
      },
      (result) => `评测已提交：${result.runs.length} 个模型运行已进入横向对比队列。`,
    );
  }

  async function handleCreateDraft() {
    if (!custom.source_code.trim()) {
      setNotice("请先粘贴源码，再让系统整理评测草稿。");
      return;
    }
    await runLive(
      () =>
        createEvaluationDraft({
          source_code: custom.source_code,
          source_filename: custom.source_filename,
          instruction: draftInstruction || undefined,
          current_name: custom.name,
          current_goal: custom.goal,
          current_test_code: custom.test_code,
        }),
      (value) => {
        setDraft(value);
        setCustom({
          name: value.name,
          goal: value.goal,
          source_filename: value.source_filename,
          source_code: value.source_code,
          test_filename: value.test_filename,
          test_code: value.test_code,
          acceptance_command: value.acceptance_command,
        });
      },
      "源码已整理成评测草稿。你可以直接开始评测，也可以继续手动或用提示词调整。",
    );
  }

  function handleToggleProfile(id: ProfileId) {
    setEvaluationProfileIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  async function handleRetryWithContext() {
    if (!confirmFailureContextRetry(run)) {
      setNotice("已取消重试。");
      return;
    }
    await runLive(
      () => retryRun(run.run_id, { allow_llm_calls: allowRealLlmIntent && serverAllowsRealLlm, timeout_seconds: 180, use_failure_context: true }),
      (value) => {
        setRun(value);
        setRunIdInput(String(value.run_id));
        setAgentRun(null);
        setActive("runs");
        void handleRefreshRunCatalog(false);
      },
      (value) => `已提交重试 run #${value.run_id}。`,
    );
  }

  async function handleCancelRun() {
    await runLive(
      () => cancelRun(Number(runIdInput || run.run_id)),
      setRun,
      (value) => `run #${value.run_id} 已取消。`,
    );
  }

  async function handleRefreshRun() {
    await handleSelectRun(Number(runIdInput || run.run_id));
  }

  async function handleLoadArtifact(kind = artifactKind) {
    await runLive(
      () => getArtifact(Number(runIdInput || run.run_id), kind),
      (value) => {
        setArtifactKind(kind);
        setArtifact(value);
      },
      `已加载 run #${runIdInput || run.run_id} 的${artifactLabels[kind]}。`,
    );
  }

  async function handleLoadSource() {
    await runLive(
      () => getRunSource(Number(runIdInput || run.run_id)),
      (value) => {
        setSourceSnapshot(value);
        setSourceFile(value.files[0]?.path ?? "");
      },
      "已加载隔离源码快照。",
    );
  }

  async function handleLoadCost() {
    await runLive(getCostMetrics, setCost, "成本指标已刷新。");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">OA</div>
          <div>
            <strong>OpenAgent</strong>
            <span>评测控制台</span>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <button className={active === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setActive(item.id)} type="button">
              {item.label}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <ShieldCheck size={18} />
          <span>粘贴源码，先让系统整理评测草稿，再同时跑多个模型横向对比。</span>
        </div>
      </aside>

      <main className="workspace">
        {active === "overview" ? (
          <Hero
            cost={cost}
            evaluation={evaluation}
            memorySummary={memorySummary}
            onOpenRuns={() => setActive("runs")}
            onStart={() => setActive("evaluate")}
          />
        ) : (
          <header className="compact-header">
            <div>
              <p className="eyebrow">{navItems.find((item) => item.id === active)?.label ?? "OpenAgent"}</p>
              <h2>{pageHeading}</h2>
            </div>
            <button className="ghost-btn" onClick={() => setActive("evaluate")} type="button">
              <Sparkles size={16} />
              新建评测
            </button>
          </header>
        )}

        <div className="notice">
          <Wifi size={16} />
          {notice}
        </div>

        {active === "overview" && (
          <DashboardPage
            busy={busy}
            cost={cost}
            demoState={demoState}
            demoStateError={demoStateError}
            evaluation={evaluation}
            memorySummary={memorySummary}
            onRefresh={handleRefreshEvaluation}
            onSelectRun={handleSelectRun}
            run={run}
          />
        )}
        {active === "evaluate" && (
          <EvaluationBuilderPage
            allowRealLlmIntent={allowRealLlmIntent}
            busy={busy}
            custom={custom}
            customModel={customModel}
            draft={draft}
            draftInstruction={draftInstruction}
            demoStatus={demoStatus}
            profileIds={evaluationProfileIds}
            profiles={visibleProfiles}
            showAdvancedDraft={showAdvancedDraft}
            onChange={setCustom}
            onChangeCustomModel={setCustomModel}
            onAnalyzeDraft={handleCreateDraft}
            onCreate={handleCreateEvaluation}
            onSetDraftInstruction={setDraftInstruction}
            onSetAllowRealLlmIntent={setAllowRealLlmIntent}
            onSetShowAdvancedDraft={setShowAdvancedDraft}
            onToggleProfile={handleToggleProfile}
          />
        )}
        {active === "history" && (
          <HistoryPage
            busy={busy}
            history={history}
            query={historyQuery}
            statusFilter={historyStatusFilter}
            onDeleteEvaluation={handleDeleteEvaluation}
            onOpenMatrix={handleOpenHistoryMatrix}
            onRefresh={handleRefreshHistory}
            onSelectRun={handleSelectRun}
            onSetQuery={setHistoryQuery}
            onSetStatusFilter={setHistoryStatusFilter}
          />
        )}
        {active === "runs" && (
          <RunsPage
            busy={busy}
            failure={failure}
            run={run}
            agentRun={agentRun}
            history={history}
            matrix={matrix}
            runCatalog={runCatalog}
            runIdInput={runIdInput}
            timeline={timeline}
            onCancel={handleCancelRun}
            onDeleteEvaluation={handleDeleteEvaluation}
            onOpenMatrix={handleOpenEvaluationMatrix}
            onRefreshRun={handleRefreshRun}
            onRefreshRunCatalog={handleRefreshRunCatalog}
            onRetry={handleRetryWithContext}
            onSelectRun={handleSelectRun}
            onSetRunIdInput={setRunIdInput}
          />
        )}
        {active === "artifacts" && (
          <EvidencePage
            artifact={artifact}
            artifactKind={artifactKind}
            busy={busy}
            run={run}
            runIdInput={runIdInput}
            sourceFile={sourceFile}
            sourceSnapshot={sourceSnapshot}
            onLoadArtifact={handleLoadArtifact}
            onLoadSource={handleLoadSource}
            onSelectArtifactKind={setArtifactKind}
            onSelectRun={handleSelectRun}
            onSelectSourceFile={setSourceFile}
          />
        )}
        {active === "cost" && <CostPage busy={busy} cost={cost} demoStatus={demoStatus} onLoadCost={handleLoadCost} onRefreshGate={() => refreshDemoStatus(true)} />}
      </main>
    </div>
  );
}

function Hero({ cost, evaluation, memorySummary, onOpenRuns, onStart }: { cost: CostMetrics; evaluation: EvaluationSummary; memorySummary: EvaluationMemorySummary; onOpenRuns: () => void; onStart: () => void }) {
  return (
    <section className="hero">
      <div className="hero-bg" />
      <div className="hero-nav">
        <span>源码粘贴驱动</span>
        <span>草稿确认 / 并发评测 / 证据对比</span>
      </div>
      <div className="hero-content">
        <p className="eyebrow">多模型横向评测</p>
        <h1>粘贴源码，系统先整理任务，再同时评测多个模型。</h1>
        <p>用户不用先配置平台概念。把源码贴进来，确认系统整理出的目标和测试草稿，然后让 DeepSeek、NewAPI 5.4 和 NewAPI 5.5 在同一任务下并行评测。</p>
        <div className="hero-actions">
          <button className="primary-btn" onClick={onStart} type="button">
            <Play size={16} />
            新建评测
          </button>
          <button className="ghost-btn" onClick={onOpenRuns} type="button">
            <TerminalSquare size={16} />
            查看运行
          </button>
        </div>
      </div>
      <div className="hero-card">
        <strong>对比快照</strong>
        <p>通过率、成本、重试记忆和最新运行状态都留在一个页面里，不再让用户跳进分散的小功能页。</p>
        <div className="hero-metrics">
          <div>
            <b>{formatPercent(evaluation.summary.pass_rate)}</b>
            <span>通过率</span>
          </div>
          <div>
            <b>{formatTokens(evaluation.summary.tokens)}</b>
            <span>Token 数</span>
          </div>
          <div>
            <b>{formatCurrency(cost.estimated_cost_usd)}</b>
            <span>成本</span>
          </div>
          <div>
            <b>{evaluation.profiles.length}</b>
            <span>模型数</span>
          </div>
          <div>
            <b>{memorySummary.retry_successes}</b>
            <span>重试成功</span>
          </div>
          <div>
            <b>{evaluation.summary.avg_score.toFixed(1)}</b>
            <span>平均分</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function DashboardPage({
  busy,
  cost,
  demoState,
  demoStateError,
  evaluation,
  memorySummary,
  onRefresh,
  onSelectRun,
  run,
}: {
  busy: boolean;
  cost: CostMetrics;
  demoState: DemoState | null;
  demoStateError: string | null;
  evaluation: EvaluationSummary;
  memorySummary: EvaluationMemorySummary;
  onRefresh: () => void;
  onSelectRun: (runId: number) => void;
  run: Run;
}) {
  return (
    <section className="page-grid">
      <MetricCard label="评测数" value={String(evaluation.summary.total)} icon={Workflow} tone="active" />
      <MetricCard label="通过率" value={formatPercent(evaluation.summary.pass_rate)} icon={CheckCircle2} tone="success" />
      <MetricCard label="总 Token" value={formatTokens(evaluation.summary.tokens)} icon={Gauge} tone="queued" />
      <MetricCard label="总成本" value={formatCurrency(cost.estimated_cost_usd)} icon={CircleDollarSign} tone="warning" />

      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <BarChart3 size={18} />
            <h3>累计模型表现</h3>
          </div>
          <button className="ghost-btn compact" onClick={onRefresh} disabled={busy} type="button">
            <RefreshCw size={16} />
            刷新
          </button>
        </div>
        <div className="model-list">
          {evaluation.profiles.map((profile) => (
            <div className="model-row" key={profile.profile}>
              <strong>{profile.profile}</strong>
              <span>{formatPercent(profile.pass_rate)} 通过</span>
              <span>{profile.avg_score.toFixed(1)} 分</span>
              <span>{formatTokens(profile.tokens)} tokens</span>
              <span>{formatCurrency(profile.estimated_cost_usd)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <RotateCcw size={18} />
          <h3>重试记忆</h3>
        </div>
        <p className="muted">{memorySummary.retry_successes} 次重试成功，fail-to-pass 率 {formatPercent(memorySummary.fail_to_pass_rate)}。</p>
        <div className="detail-list">
          <div>
            <dt>记录数</dt>
            <dd>{memorySummary.total_records}</dd>
          </div>
          <div>
            <dt>失败数</dt>
            <dd>{memorySummary.failed_records}</dd>
          </div>
        </div>
      </div>

      <DemoStatePanel demoState={demoState} error={demoStateError} onSelectRun={onSelectRun} run={run} />
    </section>
  );
}

function EvaluationBuilderPage({
  allowRealLlmIntent,
  busy,
  custom,
  customModel,
  draft,
  draftInstruction,
  demoStatus,
  profileIds,
  profiles,
  showAdvancedDraft,
  onChange,
  onChangeCustomModel,
  onAnalyzeDraft,
  onCreate,
  onSetDraftInstruction,
  onSetAllowRealLlmIntent,
  onSetShowAdvancedDraft,
  onToggleProfile,
}: {
  allowRealLlmIntent: boolean;
  busy: boolean;
  custom: CustomTaskDraft;
  customModel: CustomModelConfig;
  draft: EvaluationDraft | null;
  draftInstruction: string;
  demoStatus: DemoStatus | null;
  profileIds: ProfileId[];
  profiles: EvaluationProfile[];
  showAdvancedDraft: boolean;
  onChange: (value: CustomTaskDraft) => void;
  onChangeCustomModel: (value: CustomModelConfig) => void;
  onAnalyzeDraft: () => void;
  onCreate: () => void;
  onSetDraftInstruction: (value: string) => void;
  onSetAllowRealLlmIntent: (value: boolean) => void;
  onSetShowAdvancedDraft: (value: boolean) => void;
  onToggleProfile: (id: ProfileId) => void;
}) {
  const selectedProfiles = profiles.filter((profile) => profileIds.includes(profile.id));
  const primaryProfiles = profiles.filter((profile) => ["deepseek-api", "newapi-5-4", "newapi-5-5"].includes(profile.id));
  const optionalProfiles = profiles.filter((profile) => !["deepseek-api", "newapi-5-4", "newapi-5-5"].includes(profile.id));
  const customApiSelected = profileIds.includes("custom-api");
  return (
    <section className="draft-flow">
      <div className="panel draft-input-panel">
        <div className="panel-title">
          <Sparkles size={18} />
          <h3>粘贴源码</h3>
        </div>
        <p className="muted">把要评测的单文件源码粘进来。系统会先按预设步骤整理任务、测试建议和验收方式，再让你确认是否修改。</p>
        <TextField label="源码文件名" value={custom.source_filename} onChange={(value) => onChange({ ...custom, source_filename: value })} />
        <TextField label="源码" value={custom.source_code} onChange={(value) => onChange({ ...custom, source_code: value })} textarea tall />
        <label className="form-row">
          <span>想让系统怎么调整草稿</span>
          <textarea
            className="prompt-box"
            placeholder="可选，例如：重点测试 429 重试、不要改公开函数名、补充空输入场景。"
            value={draftInstruction}
            onChange={(event) => onSetDraftInstruction(event.target.value)}
          />
        </label>
        <div className="example-row tier-row">
          {customExamples.map((example) => (
            <button className={custom.name === example.name ? "tab active" : "tab"} key={example.name} onClick={() => onChange(example)} type="button">
              载入样例：{example.name}
            </button>
          ))}
        </div>
        <div className="button-row">
          <button className="primary-btn" onClick={onAnalyzeDraft} disabled={busy || !custom.source_code.trim()} type="button">
            <Sparkles size={16} />
            {draft ? "重新整理草稿" : "分析源码"}
          </button>
          <button className="ghost-btn" onClick={() => onSetShowAdvancedDraft(!showAdvancedDraft)} type="button">
            <FileCode2 size={16} />
            {showAdvancedDraft ? "收起手动编辑" : "手动编辑"}
          </button>
        </div>
      </div>

      <div className="panel draft-result-panel">
        <div className="panel-title">
          <CheckCircle2 size={18} />
          <h3>系统整理结果</h3>
        </div>
        {draft ? (
          <div className="draft-review">
            <div className="draft-summary">
              <span>评测名称</span>
              <strong>{custom.name}</strong>
              <span>目标</span>
              <p>{custom.goal}</p>
            </div>
            <div className="difficulty-strip">
              <div>
                <span>代码难度</span>
                <strong>系统判断：{draft.difficulty_level}</strong>
              </div>
              <div>
                <span>复杂度分</span>
                <strong>{draft.difficulty_score}/10</strong>
              </div>
              <div>
                <span>建议 Agent Loop</span>
                <strong>{draft.suggested_strategy.notes?.[0] ?? "-"}</strong>
              </div>
            </div>
            <div className="draft-lists">
              <div>
                <strong>分析步骤</strong>
                <ul>
                  {draft.analysis_steps.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
              <div>
                <strong>难度判断依据</strong>
                <ul>
                  {draft.difficulty_reasons.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
            {draft.risk_factors.length > 0 && (
              <div className="risk-factor-row">
                {draft.risk_factors.map((item) => <span key={item}>{item}</span>)}
              </div>
            )}
            <div className="draft-lists single">
              <div>
                <strong>发现的问题</strong>
                <ul>
                  {draft.findings.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
            <p className="muted">{draft.confidence}</p>
          </div>
        ) : (
          <div className="empty-state">点击“分析源码”后，这里会展示系统整理好的评测目标、测试建议和可修改点。</div>
        )}
      </div>

      {showAdvancedDraft && (
        <div className="panel wide">
          <div className="panel-title">
            <FileCode2 size={18} />
            <h3>高级编辑</h3>
          </div>
          <div className="advanced-grid">
            <TextField label="评测名称" value={custom.name} onChange={(value) => onChange({ ...custom, name: value })} />
            <TextField label="测试文件路径" value={custom.test_filename} onChange={(value) => onChange({ ...custom, test_filename: value })} />
            <TextField label="目标描述" value={custom.goal} onChange={(value) => onChange({ ...custom, goal: value })} textarea />
            <TextField label="测试代码" value={custom.test_code} onChange={(value) => onChange({ ...custom, test_code: value })} textarea tall />
            <TextField label="验收命令" value={custom.acceptance_command} onChange={(value) => onChange({ ...custom, acceptance_command: value })} />
          </div>
        </div>
      )}

      <div className="panel wide compare-launch-panel">
        <div className="panel-title with-action">
          <div>
            <BarChart3 size={18} />
            <h3>同一任务横向对比</h3>
          </div>
          <span className="status-pill active"><i />已选 {selectedProfiles.length} 个</span>
        </div>
        <p className="muted">默认只选真实主模型：DeepSeek、5.4、5.5。每次提交会创建一个评测任务，三个模型同时跑，结果在“运行”页按同一个任务归档。</p>
        <div className="model-selector-list compact-models">
          {primaryProfiles.map((profile) => (
            <label className={profileIds.includes(profile.id) ? "model-selector selected" : "model-selector"} key={profile.id}>
              <input checked={profileIds.includes(profile.id)} onChange={() => onToggleProfile(profile.id)} type="checkbox" />
              <span>
                <strong>{profile.label}</strong>
                <small>{profile.model} / {profile.mode}</small>
              </span>
            </label>
          ))}
        </div>
        <details className="advanced-options">
          <summary>更多模型接口</summary>
          <div className="model-selector-list compact-models">
            {optionalProfiles.map((profile) => (
              <label className={profileIds.includes(profile.id) ? "model-selector selected muted-selector" : "model-selector muted-selector"} key={profile.id}>
                <input checked={profileIds.includes(profile.id)} onChange={() => onToggleProfile(profile.id)} type="checkbox" />
                <span>
                  <strong>{profile.label}</strong>
                  <small>{profile.id === "local-demo" ? "本地兜底，不参与真实模型排序" : `${profile.model} / ${profile.mode}`}</small>
                </span>
              </label>
            ))}
          </div>
          {customApiSelected && (
            <div className="custom-model-grid">
              <TextField label="显示名称" value={customModel.label} onChange={(value) => onChangeCustomModel({ ...customModel, label: value })} />
              <TextField label="Provider 标识" value={customModel.provider} onChange={(value) => onChangeCustomModel({ ...customModel, provider: value })} />
              <TextField label="模型 ID" value={customModel.model} onChange={(value) => onChangeCustomModel({ ...customModel, model: value })} />
              <TextField label="Base URL" value={customModel.baseUrl} onChange={(value) => onChangeCustomModel({ ...customModel, baseUrl: value })} />
              <label className="form-row">
                <span>协议</span>
                <select value={customModel.wireApi} onChange={(event) => onChangeCustomModel({ ...customModel, wireApi: event.target.value as CustomModelConfig["wireApi"] })}>
                  <option value="chat_completions">Chat Completions</option>
                  <option value="responses">Responses</option>
                </select>
              </label>
            </div>
          )}
        </details>
        <div className={`real-call-box ${demoStatus?.allow_real_llm_calls ? "server-on" : "server-off"}`}>
          <label className="toggle-row">
            <input checked={allowRealLlmIntent} onChange={(event) => onSetAllowRealLlmIntent(event.target.checked)} type="checkbox" />
            <span>允许真实模型调用</span>
          </label>
          <p>后端闸门：{demoStatus?.allow_real_llm_calls ? "已开启" : "关闭或离线"}。关闭时仍会创建可对比 run，但不会真正调用 API。</p>
        </div>
        <button className="primary-btn full-width" onClick={onCreate} disabled={busy || profileIds.length === 0 || !draft} type="button">
          <Play size={16} />
          开始多模型评测
        </button>
      </div>
    </section>
  );
}

function HistoryPage({
  busy,
  history,
  query,
  statusFilter,
  onDeleteEvaluation,
  onOpenMatrix,
  onRefresh,
  onSelectRun,
  onSetQuery,
  onSetStatusFilter,
}: {
  busy: boolean;
  history: EvaluationHistoryItem[];
  query: string;
  statusFilter: string;
  onDeleteEvaluation: (taskId: number) => void;
  onOpenMatrix: (item: EvaluationHistoryItem) => void;
  onRefresh: () => void;
  onSelectRun: (runId: number) => void;
  onSetQuery: (value: string) => void;
  onSetStatusFilter: (value: string) => void;
}) {
  const filteredHistory = filterHistory(history, query, statusFilter);
  return (
    <section className="page-grid">
      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <Workflow size={18} />
            <h3>历史评测</h3>
          </div>
          <button className="ghost-btn compact" onClick={onRefresh} disabled={busy} type="button">
            <RefreshCw size={16} />
            刷新历史
          </button>
        </div>
        <div className="history-toolbar">
          <label className="filter-field">
            <span>搜索评测</span>
            <input value={query} onChange={(event) => onSetQuery(event.target.value)} placeholder="任务名、模型、失败类型" />
          </label>
          <label className="filter-field small">
            <span>状态</span>
            <select value={statusFilter} onChange={(event) => onSetStatusFilter(event.target.value)}>
              <option value="all">全部</option>
              <option value="running">进行中</option>
              <option value="partial">部分通过</option>
              <option value="fail">需处理</option>
              <option value="pass">全部通过</option>
            </select>
          </label>
        </div>
        {history.length === 0 ? (
          <div className="empty-state">还没有历史评测。粘贴源码并开始多模型评测后，这里会按任务聚合展示。</div>
        ) : filteredHistory.length === 0 ? (
          <div className="empty-state">没有匹配的评测任务。调整搜索词或状态筛选后再看。</div>
        ) : (
          <div className="history-list">
            {filteredHistory.map((item) => (
              <article className="history-item" key={item.task_id}>
                <div className="history-main">
                  <span className={`mini-status ${historyTone(item.status)}`}>{translateHistoryStatus(item.status)}</span>
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.description}</p>
                  </div>
                </div>
                {item.failed > 0 && (
                  <div className="failure-box compact">
                    <strong>{historyFailureTitle(item)}</strong>
                    <p>{historyFailureMessage(item)}</p>
                    <div className="failure-tags">
                      {Object.entries(item.failure_types ?? {}).map(([type, count]) => (
                        <span key={type}>{translateFailureType(type)} x {count}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="history-metrics">
                  <span><b>{item.run_count}</b> runs</span>
                  <span><b>{item.model_count}</b> 模型</span>
                  <span><b>{formatPercent(item.pass_rate)}</b> 通过</span>
                  <span><b>{formatTokens(item.total_tokens)}</b> tokens</span>
                  <span><b>{formatCurrency(item.estimated_cost_usd)}</b> 成本</span>
                </div>
                <div className="history-models">
                  {item.models.map((model) => <span key={model}>{model}</span>)}
                </div>
                <div className="history-runs">
                  {item.runs.map((run) => (
                    <button className="history-run" key={run.run_id} onClick={() => onSelectRun(run.run_id)} type="button">
                      <span className={`mini-status ${runStatusTone(run.status)}`}>#{run.run_id} {translateStatus(run.status)}</span>
                      <strong>{run.model_provider ?? run.model}</strong>
                      {run.failure_type && run.failure_type !== "None" && <em>{translateFailureType(run.failure_type)}</em>}
                      <small>{formatTokens(run.total_tokens)} / {formatCurrency(run.estimated_cost_usd)}</small>
                    </button>
                  ))}
                </div>
                <div className="button-row">
                  {item.latest_run_id && (
                    <button className="ghost-btn compact" onClick={() => onSelectRun(item.latest_run_id!)} type="button">
                      <TerminalSquare size={16} />
                      查看最新 run
                    </button>
                  )}
                  {item.best_run_id && (
                    <button className="ghost-btn compact" onClick={() => onSelectRun(item.best_run_id!)} type="button">
                      <CheckCircle2 size={16} />
                      查看最佳通过
                    </button>
                  )}
                  <button className="ghost-btn compact" onClick={() => onOpenMatrix(item)} type="button">
                    <BarChart3 size={16} />
                    查看矩阵
                  </button>
                  <button className="danger-btn compact" onClick={() => onDeleteEvaluation(item.task_id)} disabled={busy || item.running > 0 || item.pending > 0} type="button">
                    <Square size={14} />
                    删除评测
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function EvaluationMatrixPanel({ matrix, onSelectRun }: { matrix: EvaluationMatrix; onSelectRun: (runId: number) => void }) {
  const task = matrix.tasks[0];
  const cells = task?.models ?? [];
  return (
    <div className="panel wide evaluation-matrix-panel">
      <div className="panel-title">
        <BarChart3 size={18} />
        <h3>Evaluation 结果矩阵</h3>
      </div>
      <div className="matrix-summary">
        <div>
          <span>Evaluation</span>
          <strong>#{matrix.evaluation_id} {matrix.name}</strong>
        </div>
        <div>
          <span>状态</span>
          <strong>{translateHistoryStatus(matrix.status)}</strong>
        </div>
        <div>
          <span>模型</span>
          <strong>{matrix.model_count}</strong>
        </div>
        <div>
          <span>通过率</span>
          <strong>{formatPercent(matrix.pass_rate)}</strong>
        </div>
        <div>
          <span>成本</span>
          <strong>{formatCurrency(matrix.estimated_cost_usd)}</strong>
        </div>
      </div>
      <p className="muted">{matrix.goal}</p>
      <div className="matrix-table">
        <div className="matrix-row header">
          <span>模型</span>
          <span>状态</span>
          <span>Run</span>
          <span>Token</span>
          <span>成本</span>
          <span>失败反馈</span>
          <span>Artifact</span>
        </div>
        {cells.length === 0 ? (
          <div className="empty-state">这个 Evaluation 还没有模型运行结果。</div>
        ) : (
          cells.map((cell) => (
            <button className="matrix-row" key={cell.run_id} onClick={() => onSelectRun(cell.run_id)} type="button">
              <span>
                <strong>{cell.model_provider ?? cell.model}</strong>
                <em>{cell.model}</em>
              </span>
              <span className={`mini-status ${runStatusTone(cell.status)}`}>{translateStatus(cell.status)}</span>
              <span>#{cell.run_id}</span>
              <span>{formatTokens(cell.total_tokens)}</span>
              <span>{formatCurrency(cell.estimated_cost_usd)}</span>
              <span title={cell.error_message ?? undefined}>
                {cell.failure_type ? translateFailureType(cell.failure_type) : "无"}
                {cell.error_message ? `：${cell.error_message}` : ""}
              </span>
              <span>{compactPath(cell.artifacts_dir ?? null)}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function RunsPage({
  agentRun,
  busy,
  failure,
  history,
  matrix,
  run,
  runCatalog,
  runIdInput,
  timeline,
  onCancel,
  onDeleteEvaluation,
  onOpenMatrix,
  onRefreshRun,
  onRefreshRunCatalog,
  onRetry,
  onSelectRun,
  onSetRunIdInput,
}: {
  agentRun: AgentRunArtifact | null;
  busy: boolean;
  failure: FailureExplanation | null;
  history: EvaluationHistoryItem[];
  matrix: EvaluationMatrix | null;
  run: Run;
  runCatalog: RunCatalogItem[];
  runIdInput: string;
  timeline: ReturnType<typeof runTimeline>;
  onCancel: () => void;
  onDeleteEvaluation: (taskId: number) => void;
  onOpenMatrix: (evaluationId: number | null | undefined) => void;
  onRefreshRun: () => void;
  onRefreshRunCatalog: () => void;
  onRetry: () => void;
  onSelectRun: (runId: number) => void;
  onSetRunIdInput: (value: string) => void;
}) {
  const duration = formatRunDuration(run.started_at, run.finished_at);
  const strategy = agentRun?.strategy;
  const agentSteps = agentRun?.steps ?? [];
  const visibleSteps = agentSteps.slice(-5);
  const taskGroups = groupRunsByTask(runCatalog);
  const selectedTaskGroup = taskGroups.find((group) => group.task_id === run.task_id);
  const selectedHistory = history.find((item) => item.task_id === run.task_id);
  const selectedTaskRuns = selectedTaskGroup?.runs ?? runCatalog.filter((item) => item.task_id === run.task_id);
  const selectedTaskName = selectedTaskGroup?.task_name ?? selectedHistory?.name ?? `task #${run.task_id}`;
  const canDeleteSelectedTask = selectedHistory ? selectedHistory.running === 0 && selectedHistory.pending === 0 : selectedTaskGroup?.active === 0;

  return (
    <section className="page-grid two-col">
      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <TerminalSquare size={18} />
            <h3>运行目录</h3>
          </div>
          <button className="ghost-btn compact" onClick={onRefreshRunCatalog} disabled={busy} type="button">
            <RefreshCw size={16} />
            刷新目录
          </button>
        </div>
        <div className="task-run-grid">
          {runCatalog.length === 0 ? (
            <div className="empty-state">还没有加载到真实 run。可以提交评测，或刷新运行目录。</div>
          ) : (
            taskGroups.map((group, index) => (
              <article className={`task-run-card tone-${taskGroupTone(group)} color-${index % 4}`} key={group.task_id}>
                <div className="task-run-head">
                  <span className={`mini-status ${taskGroupTone(group)}`}>task #{group.task_id}</span>
                  <strong>{group.task_name}</strong>
                  <small>{group.task_description}</small>
                </div>
                <div className="task-run-metrics">
                  <span><b>{group.runs.length}</b> runs</span>
                  <span><b>{group.passed}</b> 通过</span>
                  <span><b>{formatTokens(group.total_tokens)}</b> tokens</span>
                  <span><b>{formatCurrency(group.estimated_cost_usd)}</b> 成本</span>
                </div>
                <div className="task-run-list">
                  {group.runs.map((item) => (
                    <button className={item.run_id === run.run_id ? "task-run-pill active" : "task-run-pill"} key={item.run_id} onClick={() => onSelectRun(item.run_id)} type="button">
                      <span className={`mini-status ${statusTone(item.status)}`}>#{item.run_id} {translateStatus(item.status)}</span>
                      <strong>{displayRunModel(item)}</strong>
                      <small>{isLocalBaselineRun(item) ? "本地兜底" : `${formatTokens(item.usage?.total_tokens ?? 0)} tokens`}</small>
                    </button>
                  ))}
                </div>
              </article>
            ))
          )}
        </div>
      </div>

      {matrix && (
        <EvaluationMatrixPanel matrix={matrix} onSelectRun={onSelectRun} />
      )}

      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <BarChart3 size={18} />
            <h3>当前任务横向对比</h3>
          </div>
          <div className="button-row compact-actions">
            {selectedHistory?.evaluation_id && (
              <button className="ghost-btn compact" onClick={() => onOpenMatrix(selectedHistory.evaluation_id)} disabled={busy} type="button">
                <BarChart3 size={16} />
                刷新矩阵
              </button>
            )}
            <button className="danger-btn compact" onClick={() => onDeleteEvaluation(run.task_id)} disabled={busy || !canDeleteSelectedTask} type="button">
              <Square size={14} />
              删除该任务
            </button>
          </div>
        </div>
        <p className="muted">{selectedTaskName}。这里按同一个 task 汇总，不再把不同任务的 run 混在一起比较。</p>
        <div className="task-compare-table">
          <div className="task-compare-row header">
            <span>模型</span>
            <span>状态</span>
            <span>Token</span>
            <span>成本</span>
            <span>失败</span>
            <span>证据</span>
          </div>
          {selectedTaskRuns.length === 0 ? (
            <div className="empty-state">当前 task 还没有可对比 run。</div>
          ) : (
            selectedTaskRuns.map((item) => (
              <button className={item.run_id === run.run_id ? "task-compare-row active" : "task-compare-row"} key={item.run_id} onClick={() => onSelectRun(item.run_id)} type="button">
                <span>
                  <strong>{displayRunModel(item)}</strong>
                  <em>{isLocalBaselineRun(item) ? "本地兜底，不纳入真实模型排序" : item.model}</em>
                </span>
                <span className={`mini-status ${statusTone(item.status)}`}>#{item.run_id} {translateStatus(item.status)}</span>
                <span>{formatTokens(item.usage?.total_tokens ?? 0)}</span>
                <span>{formatCurrency(item.usage?.estimated_cost_usd ?? 0)}</span>
                <span>{translateFailureType(item.failure_type)}</span>
                <span>{compactPath(item.artifacts_dir)}</span>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">
          <Play size={18} />
          <h3>运行控制</h3>
        </div>
        <label className="form-row">
          <span>Run ID</span>
          <input value={runIdInput} onChange={(event) => onSetRunIdInput(event.target.value)} />
        </label>
        <div className="button-row">
          <button className="primary-btn" onClick={onRefreshRun} disabled={busy} type="button">
            <RefreshCw size={16} />
            加载 run
          </button>
          <button className="ghost-btn" onClick={onRetry} disabled={busy || !failure} type="button">
            <RotateCcw size={16} />
            带上下文重试
          </button>
          <button className="danger-btn" onClick={onCancel} disabled={busy} type="button">
            <Square size={14} />
            取消
          </button>
        </div>
      </div>

      <div className="panel run-panel">
        <div className="panel-title">
          <Activity size={18} />
          <h3>运行状态</h3>
        </div>
        <div className={`run-status ${statusTone(run.status)}`}>{translateStatus(run.status)}</div>
        <div className="timeline">
          {timeline.map((step) => (
            <div className={`timeline-step ${step.state}`} key={`${step.status}-${step.label}`}>
              <span />
              <strong>{step.label}</strong>
              <em>{translateStatus(step.status)}</em>
            </div>
          ))}
        </div>
        <dl className="detail-list">
          <div>
            <dt>任务</dt>
            <dd>#{run.task_id}</dd>
          </div>
          <div>
            <dt>模式</dt>
            <dd>{run.mode}</dd>
          </div>
          <div>
            <dt>模型</dt>
            <dd>{run.model}</dd>
          </div>
          <div>
            <dt>Provider</dt>
            <dd>{run.model_provider ?? "-"}</dd>
          </div>
          <div>
            <dt>Harness</dt>
            <dd>{run.harness_run_id ?? "pending"}</dd>
          </div>
          <div>
            <dt>耗时</dt>
            <dd>{duration}</dd>
          </div>
          <div>
            <dt>Token</dt>
            <dd>{formatTokens(run.usage?.total_tokens ?? 0)}</dd>
          </div>
          <div>
            <dt>失败类型</dt>
            <dd>{translateFailureType(run.failure_type)}</dd>
          </div>
        </dl>
      </div>

      <div className="panel">
        <div className="panel-title">
          <ShieldCheck size={18} />
          <h3>诊断</h3>
        </div>
        {failure ? (
          <div className="failure-box">
            <strong>{failure.title}</strong>
            <p>{failure.message}</p>
            <ul>
              {failure.actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="success-box">
            <strong>当前不需要失败上下文</strong>
            <p>可以进入“证据”查看补丁、评分卡、轨迹和测试输出。</p>
          </div>
        )}
      </div>

      <div className="panel wide">
        <div className="panel-title">
          <Workflow size={18} />
          <h3>Agent Loop 策略</h3>
        </div>
        {strategy ? (
          <>
            <div className="strategy-grid">
              <div>
                <span>策略档位</span>
                <strong>{translateStrategyTier(strategy.tier)}</strong>
              </div>
              <div>
                <span>最大步数</span>
                <strong>{strategy.max_steps ?? "-"}</strong>
              </div>
              <div>
                <span>上下文预算</span>
                <strong>{formatTokens(strategy.prompt_char_budget ?? 0)}</strong>
              </div>
              <div>
                <span>实际步数</span>
                <strong>{agentSteps.length}</strong>
              </div>
            </div>
            {strategy.rationale && strategy.rationale.length > 0 && (
              <ul className="compact-list">
                {strategy.rationale.map((item) => (
                  <li key={item}>{translateStrategyRationale(item)}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className="empty-state">暂无 Agent loop 策略详情。离线 baseline 或旧 run 可能没有 api_agent_run.json。</div>
        )}
      </div>

      <div className="panel wide">
        <div className="panel-title">
          <TerminalSquare size={18} />
          <h3>Agent Steps 摘要</h3>
        </div>
        {visibleSteps.length > 0 ? (
          <div className="agent-step-list">
            {visibleSteps.map((step) => (
              <div className="agent-step" key={`${step.index}-${step.action}`}>
                <span>#{step.index}</span>
                <strong>{translateAgentAction(step.action)}</strong>
                <em>{step.observation?.ok === false ? "失败" : "完成"}</em>
                <small>{summarizeObservation(step.observation)}</small>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">暂无 step 摘要。打开“证据”的“轨迹”标签可以查看原始 trace。</div>
        )}
      </div>
    </section>
  );
}

function EvidencePage({
  artifact,
  artifactKind,
  busy,
  run,
  runIdInput,
  sourceFile,
  sourceSnapshot,
  onLoadArtifact,
  onLoadSource,
  onSelectArtifactKind,
  onSelectRun,
  onSelectSourceFile,
}: {
  artifact: string;
  artifactKind: ArtifactKind;
  busy: boolean;
  run: Run;
  runIdInput: string;
  sourceFile: string;
  sourceSnapshot: RunSource | null;
  onLoadArtifact: (kind?: ArtifactKind) => void;
  onLoadSource: () => void;
  onSelectArtifactKind: (kind: ArtifactKind) => void;
  onSelectRun: (runId: number) => void;
  onSelectSourceFile: (path: string) => void;
}) {
  return (
    <section className="page-grid">
      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <FileCode2 size={18} />
            <h3>run #{run.run_id} 的证据产物</h3>
          </div>
          <button className="ghost-btn compact" onClick={() => onSelectRun(Number(runIdInput || run.run_id))} disabled={busy} type="button">
            <RefreshCw size={16} />
            选择 Run ID
          </button>
        </div>
        <div className="tabs">
          {artifactKinds.map((kind) => (
            <button
              className={artifactKind === kind ? "tab active" : "tab"}
              key={kind}
              onClick={() => {
                onSelectArtifactKind(kind);
                onLoadArtifact(kind);
              }}
              type="button"
            >
              {artifactLabels[kind]}
            </button>
          ))}
        </div>
        <pre className="code-pane">{artifact}</pre>
      </div>

      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <FileCode2 size={18} />
            <h3>隔离源码快照</h3>
          </div>
          <button className="ghost-btn compact" onClick={onLoadSource} disabled={busy} type="button">
            <RefreshCw size={16} />
            加载源码
          </button>
        </div>
        {sourceSnapshot && sourceSnapshot.files.length > 0 ? (
          <>
            <label className="form-row">
              <span>文件</span>
              <select value={sourceFile} onChange={(event) => onSelectSourceFile(event.target.value)}>
                {sourceSnapshot.files.map((file) => (
                  <option key={file.path} value={file.path}>
                    {file.path}
                  </option>
                ))}
              </select>
            </label>
            <pre className="code-pane compact-code">{sourceSnapshot.files.find((file) => file.path === sourceFile)?.content ?? ""}</pre>
          </>
        ) : (
          <div className="empty-state">run 完成并生成产物后，可以加载源码快照。</div>
        )}
      </div>
    </section>
  );
}

function CostPage({ busy, cost, demoStatus, onLoadCost, onRefreshGate }: { busy: boolean; cost: CostMetrics; demoStatus: DemoStatus | null; onLoadCost: () => void; onRefreshGate: () => void }) {
  const localRows = cost.by_model.filter((item) => item.model.toLowerCase().includes("scripted"));
  const realRows = buildPrimaryCostRows(cost);
  return (
    <section className="page-grid two-col">
      <MetricCard label="运行数" value={String(cost.total_runs)} icon={Activity} tone="active" />
      <MetricCard label="Token 数" value={formatTokens(cost.total_tokens)} icon={FileCode2} tone="queued" />
      <MetricCard label="估算成本" value={formatCurrency(cost.estimated_cost_usd)} icon={CircleDollarSign} tone="success" />
      <div className="panel wide">
        <div className="panel-title">
          <ShieldCheck size={18} />
          <h3>预算闸门</h3>
        </div>
        <p className="muted">真实模型调用由后端闸门控制。当前闸门：{demoStatus?.allow_real_llm_calls ? "已开启" : "关闭或未知"}。</p>
        <div className="button-row">
          <button className="ghost-btn compact" onClick={onLoadCost} disabled={busy} type="button">
            <RefreshCw size={16} />
            刷新成本
          </button>
          <button className="ghost-btn compact" onClick={onRefreshGate} disabled={busy} type="button">
            <ShieldCheck size={16} />
            检查闸门
          </button>
        </div>
      </div>
      <div className="panel wide">
        <div className="panel-title">
          <CircleDollarSign size={18} />
          <h3>真实模型成本</h3>
        </div>
        <div className="model-list">
          {realRows.map((item) => (
            <div className={item.runs === 0 ? "model-row muted-row" : "model-row"} key={item.model}>
              <strong>{item.label}</strong>
              <span>{item.runs} 次运行</span>
              <span>{formatTokens(item.tokens)} tokens</span>
              <span>{formatCurrency(item.estimated_cost_usd)}</span>
            </div>
          ))}
        </div>
      </div>
      {localRows.length > 0 && (
        <div className="panel wide muted-panel">
          <div className="panel-title">
            <TerminalSquare size={18} />
            <h3>本地兜底运行</h3>
          </div>
          <p className="muted">scripted 只用于离线回路验证，不作为 dpsk / 5.4 / 5.5 的能力或成本比较对象。</p>
          <div className="model-list">
            {localRows.map((item) => (
              <div className="model-row muted-row" key={item.model}>
                <strong>{item.model}</strong>
                <span>{item.runs} 次运行</span>
                <span>{formatTokens(item.tokens)} tokens</span>
                <span>{formatCurrency(item.estimated_cost_usd)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function buildPrimaryCostRows(cost: CostMetrics) {
  const rows = cost.by_model.filter((item) => !item.model.toLowerCase().includes("scripted"));
  const specs = [
    { label: "DeepSeek API", aliases: ["deepseek", "dpsk"] },
    { label: "NewAPI 5.4", aliases: ["newapi-5.4", "newapi 5.4", "gpt-5.4", "5.4"] },
    { label: "NewAPI 5.5", aliases: ["newapi-5.5", "newapi 5.5", "gpt-5.5", "5.5"] },
  ];
  const primary = specs.map((spec) => {
    const matched = rows.filter((item) => spec.aliases.some((alias) => item.model.toLowerCase().includes(alias)));
    return {
      label: spec.label,
      model: spec.label,
      runs: matched.reduce((sum, item) => sum + item.runs, 0),
      tokens: matched.reduce((sum, item) => sum + item.tokens, 0),
      estimated_cost_usd: matched.reduce((sum, item) => sum + item.estimated_cost_usd, 0),
    };
  });
  const primaryAliases = specs.flatMap((spec) => spec.aliases);
  const extra = rows
    .filter((item) => !primaryAliases.some((alias) => item.model.toLowerCase().includes(alias)))
    .map((item) => ({ ...item, label: item.model }));
  return [...primary, ...extra];
}

function DemoStatePanel({ demoState, error, onSelectRun, run }: { demoState: DemoState | null; error: string | null; onSelectRun: (runId: number) => void; run: Run }) {
  const latestRuns = demoState?.latest_runs ?? [];
  const updatedAt = demoState ? new Date(demoState.generated_at).toLocaleTimeString("en-US", { hour12: false }) : "waiting";

  return (
    <div className="panel wide live-state-panel">
      <div className="panel-title">
        <Wifi size={18} />
        <h3>运行态</h3>
      </div>
      <div className="live-state-grid">
        <div className={`live-state-card ${error ? "danger" : "success"}`}>
          <span>后端连接</span>
          <strong>{error ? "离线" : demoState ? "在线" : "检测中"}</strong>
          <small>{error ?? `更新于 ${updatedAt}`}</small>
        </div>
        <div className="live-state-card">
          <span>任务数</span>
          <strong>{demoState?.tasks.count ?? 0}</strong>
          <small>{formatIdList(demoState?.tasks.ids ?? [])}</small>
        </div>
        <div className="live-state-card">
          <span>运行数</span>
          <strong>{demoState?.runs.count ?? 0}</strong>
          <small>{formatIdList(demoState?.runs.ids ?? [])}</small>
        </div>
        <div className="live-state-card muted-card">
          <span>当前选择</span>
          <strong>run #{run.run_id}</strong>
          <small>{run.model}</small>
        </div>
      </div>
      <div className="live-run-strip">
        {latestRuns.length === 0 ? (
          <div className="empty-state">暂无真实运行。提交评测后，这里会显示最新 run。</div>
        ) : (
          latestRuns.map((item) => (
            <button className="live-run-pill" key={item.run_id} onClick={() => onSelectRun(item.run_id)} type="button">
              <span className={`mini-status ${statusTone(item.status)}`}>#{item.run_id} {translateStatus(item.status)}</span>
              <strong>task #{item.task_id}</strong>
              <small>{item.model} / {item.harness_run_id ?? "pending"}</small>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, icon: Icon, tone }: { label: string; value: string; icon: typeof Activity; tone: string }) {
  return (
    <div className={`metric-card ${tone}`}>
      <Icon size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TextField({ label, value, onChange, textarea = false, tall = false }: { label: string; value: string; onChange: (value: string) => void; textarea?: boolean; tall?: boolean }) {
  return (
    <label className="form-row">
      <span>{label}</span>
      {textarea ? <textarea className={tall ? "tall" : ""} value={value} onChange={(event) => onChange(event.target.value)} /> : <input value={value} onChange={(event) => onChange(event.target.value)} />}
    </label>
  );
}

type FailureExplanation = {
  title: string;
  message: string;
  actions: string[];
};

function explainFailure(run: Run): FailureExplanation | null {
  if (!["fail", "timeout", "cancelled"].includes(run.status)) {
    return null;
  }
  if (run.status === "timeout") {
    return {
      title: "运行超时",
      message: "模型或测试命令超过了允许的执行窗口。",
      actions: ["查看 trace", "缩小任务范围", "带失败上下文重试"],
    };
  }
  if (run.failure_type === "NoPatch") {
    return {
      title: "没有有效补丁",
      message: "Agent 没有修改允许范围内的源码文件。",
      actions: ["查看工具调用", "检查任务范围", "带失败上下文重试"],
    };
  }
  if (run.failure_type === "TestFailed" || run.failure_type === "Regression") {
    return {
      title: "验收失败",
      message: "补丁修改了代码，但测试或回归检查失败。",
      actions: ["打开测试结果", "查看 patch.diff", "带 trace 和测试输出重试"],
    };
  }
  return {
    title: translateFailureType(run.failure_type),
    message: explainFailureMessage(run.failure_type, run.error_message),
    actions: ["打开证据页", "刷新运行状态", "必要时重试"],
  };
}

function filterHistory(history: EvaluationHistoryItem[], query: string, statusFilter: string): EvaluationHistoryItem[] {
  const normalized = query.trim().toLowerCase();
  return history.filter((item) => {
    const matchesStatus = statusFilter === "all" || item.status === statusFilter;
    if (!matchesStatus) {
      return false;
    }
    if (!normalized) {
      return true;
    }
    const searchable = [
      item.name,
      item.description,
      item.status,
      item.latest_failure_type ?? "",
      item.latest_error_message ?? "",
      ...item.models,
      ...Object.keys(item.failure_types ?? {}),
      ...item.runs.flatMap((run) => [run.model, run.model_provider ?? "", run.failure_type ?? "", run.error_message ?? ""]),
    ]
      .join(" ")
      .toLowerCase();
    return searchable.includes(normalized);
  });
}

function historyFailureTitle(item: EvaluationHistoryItem): string {
  if (item.latest_failure_type) {
    return `最近失败：${translateFailureType(item.latest_failure_type)}`;
  }
  return "有模型评测失败";
}

function historyFailureMessage(item: EvaluationHistoryItem): string {
  return explainFailureMessage(item.latest_failure_type ?? null, item.latest_error_message ?? null);
}

function explainFailureMessage(failureType: string | null, errorMessage: string | null): string {
  const raw = errorMessage ?? "";
  const normalized = raw.toLowerCase();
  if (failureType === "ApiNotConfigured") {
    return "这次没有真正调用模型。通常是未勾选真实调用、后端闸门关闭，或 provider key 没有被运行进程读到。";
  }
  if (failureType === "ProviderTransient" || normalized.includes("429") || normalized.includes("too many requests")) {
    if (normalized.includes("429") || normalized.includes("too many requests")) {
      return appendRawFailure("模型服务返回 429 Too Many Requests，说明当前 provider 限流或请求过多。可以稍后重试、降低并发，或换一个模型 profile。", raw);
    }
    return appendRawFailure("模型 provider 临时不可用或渠道异常。平台已记录失败证据，可以稍后重试或切换模型。", raw);
  }
  if (failureType === "ApiRuntimeError") {
    return "模型调用或 Agent 工具循环执行失败。建议打开 trace 和 report 看具体在哪一步中断。";
  }
  if (failureType === "TestFailed" || failureType === "Regression") {
    return "模型生成了补丁，但 pytest 或回归检查没有通过。建议查看 test-result 和 patch。";
  }
  return raw || "请查看评分卡、轨迹和测试输出。";
}

function appendRawFailure(message: string, raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return message;
  }
  return `${message} 原始反馈：${trimmed.slice(0, 260)}${trimmed.length > 260 ? "..." : ""}`;
}

function formatIdList(ids: number[]): string {
  if (ids.length === 0) {
    return "无";
  }
  if (ids.length <= 12) {
    return ids.join(", ");
  }
  return `${ids.slice(0, 12).join(", ")} ...`;
}

function compactPath(value: string | null): string {
  if (!value) {
    return "未生成";
  }
  const normalized = value.split("\\").join("/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 2) {
    return value;
  }
  return `.../${parts.slice(-2).join("/")}`;
}

function translateStatus(status: string): string {
  const labels: Record<string, string> = {
    pending: "排队中",
    running: "运行中",
    pass: "通过",
    fail: "失败",
    timeout: "超时",
    cancelled: "已取消",
  };
  return labels[status] ?? status;
}

function runStatusTone(status: string): string {
  return ["pending", "running", "pass", "fail", "timeout", "cancelled"].includes(status) ? statusTone(status as Run["status"]) : "muted";
}

function translateFailureType(value: string | null): string {
  if (!value || value === "None") {
    return "无";
  }
  const labels: Record<string, string> = {
    NoPatch: "无有效补丁",
    TestFailed: "测试失败",
    Regression: "回归失败",
    ScopeViolation: "越权修改",
    ApiNotConfigured: "API 未配置",
    ProviderTransient: "模型服务临时失败",
    ApiRuntimeError: "模型执行失败",
    Timeout: "超时",
  };
  return labels[value] ?? value;
}

function translateStrategyTier(value?: string): string {
  const labels: Record<string, string> = {
    simple: "简单任务",
    standard: "标准任务",
    deep: "复杂任务",
  };
  return value ? labels[value] ?? value : "未知";
}

function translateStrategyRationale(value: string): string {
  const labels: Record<string, string> = {
    "small repo, one editable file, short goal": "仓库小、单文件修改、目标短，适合减少轮次和 token。",
    "multi-file or larger task context": "任务上下文较大，需要保留标准诊断空间。",
    "broad edit/test surface": "修改面或测试面较宽，需要更多步骤确认影响范围。",
    "retry has failure context to diagnose": "这是带失败上下文的重试，需要先诊断上次失败。",
    "goal contains higher-complexity engineering terms": "目标包含异步、缓存、并发等复杂工程语义。",
    "explicit fixed loop budget": "使用固定 loop 预算。",
    "legacy fixed loop budget": "旧 run 使用固定 loop 预算。",
  };
  return labels[value] ?? value;
}

function translateAgentAction(value: string): string {
  const labels: Record<string, string> = {
    read_file: "读取文件",
    write_file: "重写文件",
    edit_file: "局部编辑",
    run_command: "运行命令",
    search_repo: "搜索代码",
    inspect_symbols: "查看符号",
    finish: "结束",
    invalid: "协议重试",
  };
  return labels[value] ?? value;
}

function summarizeObservation(observation?: Record<string, unknown>): string {
  if (!observation) {
    return "暂无 observation";
  }
  if (typeof observation.error === "string") {
    return observation.error.slice(0, 180);
  }
  if (typeof observation.path === "string") {
    return observation.path;
  }
  if (typeof observation.command === "string") {
    return `${observation.command} / exit=${String(observation.exit_code ?? "-")}`;
  }
  if (Array.isArray(observation.hits)) {
    return `命中 ${observation.hits.length} 条`;
  }
  if (typeof observation.summary === "string") {
    return observation.summary.slice(0, 180);
  }
  return "已记录结构化 observation";
}

function formatRunDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) {
    return "-";
  }
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return "-";
  }
  return `${((end - start) / 1000).toFixed(1)}s`;
}

function translateHistoryStatus(status: string): string {
  const labels: Record<string, string> = {
    running: "进行中",
    pass: "全部通过",
    partial: "部分通过",
    fail: "需处理",
    empty: "无运行",
  };
  return labels[status] ?? status;
}

function historyTone(status: string): string {
  const tones: Record<string, string> = {
    running: "active",
    pass: "success",
    partial: "warning",
    fail: "danger",
    empty: "muted",
  };
  return tones[status] ?? "muted";
}

function pageTitle(active: NavItem): string {
  const titles: Record<NavItem, string> = {
    overview: "看板",
    evaluate: "创建多模型评测",
    history: "历史评测",
    runs: "运行监控",
    artifacts: "证据浏览器",
    cost: "成本与预算",
  };
  return titles[active];
}

export default App;
