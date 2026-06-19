import { useEffect, useState } from "react";
import {
  Activity,
  Archive,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  FileCode2,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Square,
  TerminalSquare,
} from "lucide-react";
import {
  cancelRun,
  createCustomTask,
  createRun,
  createTask,
  getArtifact,
  getCostMetrics,
  getDemoStatus,
  getEvaluationSummary,
  getRun,
  getRunSource,
  listRuns,
  retryRun,
} from "./api";
import { demoArtifact, demoCost, demoEvaluation, demoRun, getDemoArtifact, type ArtifactKind } from "./mockData";
import { buildEvaluationRequest, buildFreshIdempotencyKey, evaluationProfiles } from "./runProfiles";
import {
  formatCurrency,
  formatPercent,
  formatTokens,
  runTimeline,
  statusTone,
  type CostMetrics,
  type DemoStatus,
  type EvaluationSummary,
  type Run,
  type RunCatalogItem,
  type RunSource,
} from "./domain";

type NavItem = "evaluation" | "runs" | "custom" | "artifacts" | "cost";

const navItems: Array<{ id: NavItem; label: string }> = [
  { id: "evaluation", label: "Evaluation" },
  { id: "runs", label: "Run Control" },
  { id: "custom", label: "Custom Task" },
  { id: "artifacts", label: "Artifacts" },
  { id: "cost", label: "Cost" },
];

const artifactKinds: ArtifactKind[] = ["report", "patch", "scorecard", "test-result", "trace"];

type CustomTaskDraft = {
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
  name: "custom config merge",
  goal: "Fix load_config so nested headers merge without dropping defaults, and do not mutate DEFAULTS.",
  source_filename: "config_loader.py",
  source_code: `DEFAULTS = {
    "timeout_seconds": 5,
    "headers": {"accept": "application/json"},
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


def test_defaults_are_not_mutated():
    load_config({"headers": {"x-debug": "1"}})
    assert "x-debug" not in DEFAULTS["headers"]
`,
  acceptance_command: "python -m pytest -q",
  },
  {
    name: "retry after rate limit",
    goal: "Make should_retry return true for HTTP 429 while keeping the max-attempt guard.",
    source_filename: "http_client.py",
    source_code: `RETRYABLE_STATUSES = {500, 502, 503, 504}


def should_retry(status_code, attempt, max_attempts):
    if attempt >= max_attempts:
        return False
    return status_code in RETRYABLE_STATUSES
`,
    test_filename: "test_http_client.py",
    test_code: `from http_client import should_retry


def test_retries_rate_limit_response():
    assert should_retry(429, attempt=1, max_attempts=3)


def test_stops_at_max_attempts():
    assert not should_retry(429, attempt=3, max_attempts=3)
`,
    acceptance_command: "python -m pytest -q",
  },
  {
    name: "parse duration safely",
    goal: "Fix parse_duration so missing or malformed input returns 0 instead of crashing.",
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
];

const defaultCustom = customExamples[0];

function App() {
  const [active, setActive] = useState<NavItem>("evaluation");
  const [run, setRun] = useState<Run>(demoRun);
  const [cost, setCost] = useState<CostMetrics>(demoCost);
  const [evaluation, setEvaluation] = useState<EvaluationSummary>(demoEvaluation);
  const [artifactKind, setArtifactKind] = useState<ArtifactKind>("scorecard");
  const [artifact, setArtifact] = useState(demoArtifact);
  const [runIdInput, setRunIdInput] = useState("1");
  const [runCatalog, setRunCatalog] = useState<RunCatalogItem[]>([]);
  const [sourceSnapshot, setSourceSnapshot] = useState<RunSource | null>(null);
  const [sourceFile, setSourceFile] = useState("");
  const [notice, setNotice] = useState(
    "Dashboard starts with safe sample data. Start the backend, then click Refresh dashboard to load live runs.",
  );
  const [busy, setBusy] = useState(false);
  const [profileId, setProfileId] = useState(evaluationProfiles[0].id);
  const [custom, setCustom] = useState(defaultCustom);
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [allowRealLlmIntent, setAllowRealLlmIntent] = useState(true);

  const selectedProfile = evaluationProfiles.find((profile) => profile.id === profileId) ?? evaluationProfiles[0];
  const selectedProfileNeedsRealLlm = selectedProfile.mode === "api";
  const serverAllowsRealLlm = demoStatus?.allow_real_llm_calls === true;
  const canSubmitRealLlm = allowRealLlmIntent;
  const effectiveRealLlmRequest = selectedProfileNeedsRealLlm && allowRealLlmIntent;
  const selectedTone = statusTone(run.status);
  const timeline = runTimeline(run.status);
  const failure = explainFailure(run);

  useEffect(() => {
    void refreshDemoStatus(false);
    void handleRefreshRunCatalog(false);
  }, []);

  async function refreshDemoStatus(showNotice = true) {
    try {
      const status = await getDemoStatus();
      setDemoStatus(status);
      if (showNotice) {
        setNotice(
          status.allow_real_llm_calls
            ? "Server allows real LLM calls. The frontend request-side authorization switch is available before submitting."
            : "Server LLM gate is disabled. The frontend switch can stay on, but the backend will reject real DeepSeek calls.",
        );
      }
    } catch (error) {
      if (showNotice) {
        setNotice(error instanceof Error ? `Could not load demo status: ${error.message}` : "Could not load demo status.");
      }
    }
  }

  async function runLive<T>(action: () => Promise<T>, onSuccess: (value: T) => void, message: string | ((value: T) => string)) {
    setBusy(true);
    try {
      const value = await action();
      onSuccess(value);
      setNotice(typeof message === "function" ? message(value) : message);
    } catch (error) {
      setNotice(error instanceof Error ? `API call failed: ${error.message}` : "API call failed. Check backend service.");
    } finally {
      setBusy(false);
    }
  }

  function syncRunCatalog(items: RunCatalogItem[]) {
    setRunCatalog(items);
    const selectedRunId = Number(runIdInput || run.run_id);
    const selected = items.find((item) => item.run_id === selectedRunId);
    if (selected) {
      setRun(selected);
    }
  }

  async function handleRefreshEvaluation() {
    await runLive(
      getEvaluationSummary,
      (value) => {
        setEvaluation(value);
        void handleRefreshRunCatalog(false);
      },
      "Loaded live Evaluation Dashboard from /evaluation/summary.",
    );
  }

  async function handleRefreshRunCatalog(showNotice = true) {
    if (!showNotice) {
      try {
        const items = await listRuns();
        syncRunCatalog(items);
      } catch {
        // Keep the current visible workflow stable; explicit refresh reports errors.
      }
      return;
    }

    await runLive(
      listRuns,
      (items) => {
        syncRunCatalog(items);
        if (items.length > 0) {
          setRunIdInput(String(items[0].run_id));
        }
      },
      "Loaded live run catalog from /runs. Click a run to inspect its artifacts and source.",
    );
  }

  async function handleSelectRun(runId: number) {
    setRunIdInput(String(runId));
    await runLive(
      () => getRun(runId),
      (value) => {
        setRun(value);
        setActive("runs");
      },
      `Selected run #${runId}. Use Artifacts to inspect patch, trace, scorecard, and source.`,
    );
  }

  async function handleCreateRun() {
    if (selectedProfile.id === "retry-context") {
      await handleRetryWithContext();
      return;
    }
    if (selectedProfileNeedsRealLlm && !canSubmitRealLlm) {
      setNotice(realCallBlockedMessage(serverAllowsRealLlm));
      return;
    }
    const request = buildEvaluationRequest(selectedProfile);
    const runRequest = {
      ...request.run,
      allow_llm_calls: selectedProfileNeedsRealLlm ? canSubmitRealLlm : false,
    };
    await runLive(
      async () => {
        const task = await createTask(request.task);
        const created = await createRun({ task_id: task.task_id, ...runRequest }, buildFreshIdempotencyKey(request.idempotencyKey));
        setRunIdInput(String(created.run_id));
        void handleRefreshRunCatalog(false);
        return created;
      },
      setRun,
      `${selectedProfile.label} submitted. mode=${runRequest.mode}, model=${runRequest.model}, allow_llm_calls=${runRequest.allow_llm_calls}`,
    );
  }

  async function handleCreateCustomTask() {
    await runLive(
      async () => {
        const status = demoStatus ?? await getDemoStatus();
        setDemoStatus(status);
        const task = await createCustomTask(custom);
        if (!status.allow_real_llm_calls || !canSubmitRealLlm) {
          return {
            run: null,
            taskId: task.task_id,
            harnessTaskPath: task.harness_task_path,
            serverAllowsRealLlm: status.allow_real_llm_calls,
          };
        }
        const created = await createRun(
          {
            task_id: task.task_id,
            mode: "api",
            model: "deepseek-v4-flash",
            allow_llm_calls: canSubmitRealLlm,
            timeout_seconds: 180,
          },
          buildFreshIdempotencyKey("custom"),
        );
        setRunIdInput(String(created.run_id));
        void handleRefreshRunCatalog(false);
        return {
          run: created,
          taskId: task.task_id,
          harnessTaskPath: task.harness_task_path,
          serverAllowsRealLlm: status.allow_real_llm_calls,
        };
      },
      (value) => {
        if (value.run) {
          setRun(value.run);
        }
      },
      (value) =>
        value.run
          ? "Custom task created and submitted to the guarded DeepSeek API path."
          : value.serverAllowsRealLlm
            ? "Custom task created. Real DeepSeek run was not submitted because the frontend request switch is off."
            : "Custom task created. Real DeepSeek run was not submitted because the backend LLM gate is disabled.",
    );
  }

  async function handleRefreshRun() {
    const id = Number(runIdInput || run.run_id);
    await runLive(() => getRun(id), setRun, `Refreshed run #${id}.`);
  }

  async function handleCancelRun() {
    await runLive(() => cancelRun(run.run_id), setRun, `Cancel request sent for run #${run.run_id}.`);
  }

  async function handleRetryWithContext() {
    if (run.mode === "api" && !canSubmitRealLlm) {
      setNotice(realCallBlockedMessage(serverAllowsRealLlm));
      return;
    }
    await runLive(
      () => retryRun(run.run_id, { allow_llm_calls: run.mode === "api" ? canSubmitRealLlm : false, timeout_seconds: run.timeout_seconds ?? 180 }),
      (retried) => {
        setRun(retried);
        setRunIdInput(String(retried.run_id));
        void handleRefreshRunCatalog(false);
      },
      "Retry with context created. Refresh the dashboard after it finishes to compare first attempt and retry.",
    );
  }

  async function handleLoadArtifact(kind = artifactKind) {
    setArtifact(getDemoArtifact(kind));
    setBusy(true);
    try {
      const liveArtifact = await getArtifact(run.run_id, kind);
      setArtifact(liveArtifact);
      setNotice(`Loaded live ${kind} for run #${run.run_id}.`);
    } catch {
      setNotice(`No live ${kind} for run #${run.run_id}; showing the safe sample artifact.`);
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadSource() {
    setBusy(true);
    try {
      const source = await getRunSource(run.run_id);
      setSourceSnapshot(source);
      setSourceFile(source.files[0]?.path ?? "");
      setNotice(`Loaded source snapshot for run #${run.run_id}.`);
    } catch (error) {
      setSourceSnapshot(null);
      setSourceFile("");
      setNotice(error instanceof Error ? `No source snapshot for run #${run.run_id}: ${error.message}` : `No source snapshot for run #${run.run_id}.`);
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadCost() {
    await runLive(getCostMetrics, setCost, "Loaded backend cost metrics.");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">OA</div>
          <div>
            <strong>OpenAgent</strong>
            <span>Interview Console</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Console navigation">
          {navItems.map((item) => (
            <button className={active === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setActive(item.id)} type="button">
              {item.label}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <ShieldCheck size={18} />
          <span>Real DeepSeek runs require server-side authorization and stop at the 1 CNY budget gate.</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Coding-Agent Evaluation Platform</p>
            <h1>Quantitative Evaluation Dashboard</h1>
          </div>
          <div className={`status-pill ${selectedTone}`}>
            <span />
            run #{run.run_id} / {run.status}
          </div>
        </header>

        <section className="notice">
          <TerminalSquare size={18} />
          <span>{notice}</span>
        </section>

        {active === "evaluation" && (
          <EvaluationPage evaluation={evaluation} busy={busy} onRefresh={handleRefreshEvaluation} onSelectRun={handleSelectRun} />
        )}

        {active === "runs" && (
          <section className="page-grid two-col">
            <div className="panel wide">
              <div className="panel-title with-action">
                <div>
                  <Archive size={18} />
                  <h3>Run Catalog</h3>
                </div>
                <button className="ghost-btn compact" onClick={() => void handleRefreshRunCatalog()} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  Refresh runs
                </button>
              </div>
              <p className="muted">These are live backend runs. Select one before loading artifacts or explaining evidence in an interview.</p>
              <div className="run-catalog">
                {runCatalog.length === 0 ? (
                  <div className="empty-state">No live runs loaded yet. Start an evaluation or refresh the catalog.</div>
                ) : (
                  runCatalog.map((item) => (
                    <button
                      className={item.run_id === run.run_id ? "run-card active" : "run-card"}
                      key={item.run_id}
                      onClick={() => void handleSelectRun(item.run_id)}
                      type="button"
                    >
                      <span className={`mini-status ${statusTone(item.status)}`}>#{item.run_id} {item.status}</span>
                      <strong>{item.task_name}</strong>
                      <em>{item.mode} / {item.model}</em>
                      <small>harness: {item.harness_run_id ?? "pending"}</small>
                      <small>artifacts: {compactPath(item.artifacts_dir)}</small>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="panel">
              <div className="panel-title">
                <Play size={18} />
                <h3>Evaluation Profile</h3>
              </div>
              <p className="muted">Run the same benchmark through different execution strategies, then return to the Dashboard for comparison.</p>
              <label className="form-row">
                <span>Profile</span>
                <select id="eval-profile" value={profileId} onChange={(event) => setProfileId(event.target.value as typeof profileId)}>
                  {evaluationProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className={`profile-summary ${selectedProfile.mode}`}>
                <strong>{selectedProfile.label}</strong>
                <span>{selectedProfile.description}</span>
                <em>{selectedProfile.budgetHint}</em>
              </div>
              <div className={`real-call-box ${serverAllowsRealLlm ? "server-on" : "server-off"}`}>
                <label className="toggle-row">
                  <input
                    checked={effectiveRealLlmRequest}
                    disabled={!selectedProfileNeedsRealLlm}
                    onChange={(event) => setAllowRealLlmIntent(event.target.checked)}
                    type="checkbox"
                  />
                  <span>Request real DeepSeek API call</span>
                </label>
                <p>
                  Backend gate: {serverAllowsRealLlm ? "allows real calls" : "disabled, will reject real calls"}.
                  Frontend request: {effectiveRealLlmRequest ? "allow_llm_calls=true" : "allow_llm_calls=false"}.
                </p>
                <button className="ghost-btn compact" onClick={() => void refreshDemoStatus()} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  Check server gate
                </button>
              </div>
              <div className="button-row">
                <button className="primary-btn" onClick={handleCreateRun} disabled={busy} type="button">
                  <Play size={16} />
                  {selectedProfile.id === "retry-context" ? "Retry current run" : "Start evaluation"}
                </button>
                <button className="ghost-btn" onClick={handleRefreshRun} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  Refresh
                </button>
                <button className="danger-btn" onClick={handleCancelRun} disabled={busy} type="button">
                  <Square size={14} />
                  Cancel
                </button>
              </div>
              <label className="form-row">
                <span>Run ID</span>
                <input value={runIdInput} onChange={(event) => setRunIdInput(event.target.value)} />
              </label>
            </div>

            <div className="panel run-panel">
              <div className="panel-title">
                <Activity size={18} />
                <h3>Run #{run.run_id}</h3>
              </div>
              <div className={`run-status ${selectedTone}`}>{run.status}</div>
              <div className="timeline">
                {timeline.map((step) => (
                  <div className={`timeline-step ${step.state}`} key={`${step.status}-${step.label}`}>
                    <span />
                    <strong>{step.label}</strong>
                    <em>{step.status}</em>
                  </div>
                ))}
              </div>
              <dl className="detail-list">
                <div><dt>task</dt><dd>{runCatalog.find((item) => item.run_id === run.run_id)?.task_name ?? `#${run.task_id}`}</dd></div>
                <div><dt>mode</dt><dd>{run.mode}</dd></div>
                <div><dt>model</dt><dd>{run.model}</dd></div>
                <div><dt>harness run</dt><dd>{run.harness_run_id ?? "pending"}</dd></div>
                <div><dt>artifacts</dt><dd>{compactPath(run.artifacts_dir)}</dd></div>
                <div><dt>failure</dt><dd>{run.failure_type ?? "None"}</dd></div>
                <div><dt>cost</dt><dd>{run.usage ? formatCurrency(run.usage.estimated_cost_usd) : "none"}</dd></div>
              </dl>
              {failure && (
                <div className="failure-box">
                  <strong>{failure.title}</strong>
                  <p>{failure.message}</p>
                  <button className="ghost-btn compact" onClick={handleRetryWithContext} disabled={busy} type="button">
                    <RotateCcw size={16} />
                    Retry with context
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {active === "custom" && (
          <section className="page-grid two-col">
            <div className="panel">
              <div className="panel-title">
                <FileCode2 size={18} />
                <h3>Custom Task</h3>
              </div>
              <p className="muted">Create a tiny isolated Harness task from source code, tests, and an acceptance command.</p>
              <label className="form-row">
                <span>Stable demo example</span>
                <select
                  value={custom.name}
                  onChange={(event) => {
                    const next = customExamples.find((example) => example.name === event.target.value);
                    if (next) {
                      setCustom(next);
                    }
                  }}
                >
                  {customExamples.map((example) => (
                    <option key={example.name} value={example.name}>
                      {example.name}
                    </option>
                  ))}
                </select>
              </label>
              <TextField label="Task name" value={custom.name} onChange={(value) => setCustom({ ...custom, name: value })} />
              <TextField label="Goal" value={custom.goal} onChange={(value) => setCustom({ ...custom, goal: value })} textarea />
              <TextField label="Source filename" value={custom.source_filename} onChange={(value) => setCustom({ ...custom, source_filename: value })} />
              <TextField label="Source code" value={custom.source_code} onChange={(value) => setCustom({ ...custom, source_code: value })} textarea tall />
            </div>
            <div className="panel">
              <TextField label="Test filename" value={custom.test_filename} onChange={(value) => setCustom({ ...custom, test_filename: value })} />
              <TextField label="Test code" value={custom.test_code} onChange={(value) => setCustom({ ...custom, test_code: value })} textarea tall />
              <TextField label="Acceptance command" value={custom.acceptance_command} onChange={(value) => setCustom({ ...custom, acceptance_command: value })} />
              <button className="primary-btn" onClick={handleCreateCustomTask} disabled={busy} type="button">
                <Play size={16} />
                Create custom task and run DeepSeek
              </button>
              <p className="muted small">If real API calls are disabled or the 1 CNY budget is exhausted, the backend returns a clear refusal.</p>
            </div>
          </section>
        )}

        {active === "artifacts" && (
          <section className="page-grid">
            <div className="panel wide">
              <div className="panel-title with-action">
                <div>
                  <Archive size={18} />
                  <h3>Artifacts for run #{run.run_id}</h3>
                </div>
                <button className="ghost-btn compact" onClick={() => void handleSelectRun(Number(runIdInput || run.run_id))} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  Select Run ID
                </button>
              </div>
              <div className="tabs">
                {artifactKinds.map((kind) => (
                  <button
                    className={artifactKind === kind ? "tab active" : "tab"}
                    key={kind}
                    onClick={() => {
                      setArtifactKind(kind);
                      void handleLoadArtifact(kind);
                    }}
                    type="button"
                  >
                    {kind}
                  </button>
                ))}
              </div>
              <pre className="code-pane">{artifact}</pre>
            </div>
            <div className="panel wide">
              <div className="panel-title with-action">
                <div>
                  <FileCode2 size={18} />
                  <h3>Source Snapshot</h3>
                </div>
                <button className="ghost-btn compact" onClick={handleLoadSource} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  Load source
                </button>
              </div>
              <p className="muted">This is the isolated repository snapshot used by the selected run. Pair it with patch.diff and scorecard when explaining evidence.</p>
              {sourceSnapshot && sourceSnapshot.files.length > 0 ? (
                <>
                  <label className="form-row">
                    <span>File</span>
                    <select value={sourceFile} onChange={(event) => setSourceFile(event.target.value)}>
                      {sourceSnapshot.files.map((file) => (
                        <option key={file.path} value={file.path}>
                          {file.path}
                        </option>
                      ))}
                    </select>
                  </label>
                  <pre className="code-pane compact-code">
                    {sourceSnapshot.files.find((file) => file.path === sourceFile)?.content ?? ""}
                  </pre>
                </>
              ) : (
                <div className="empty-state">Load source after selecting a completed run with artifacts.</div>
              )}
            </div>
          </section>
        )}

        {active === "cost" && (
          <section className="page-grid two-col">
            <MetricCard label="Total runs" value={String(cost.total_runs)} icon={Activity} tone="active" />
            <MetricCard label="Total tokens" value={formatTokens(cost.total_tokens)} icon={FileCode2} tone="queued" />
            <MetricCard label="Estimated cost" value={formatCurrency(cost.estimated_cost_usd)} icon={CircleDollarSign} tone="success" />
            <div className="panel">
              <div className="panel-title">
                <ShieldCheck size={18} />
                <h3>Real API Budget Gate</h3>
              </div>
              <p className="muted">The backend caps real DeepSeek calls at 1 CNY for the interview demo.</p>
              <button className="ghost-btn compact" onClick={handleLoadCost} disabled={busy} type="button">
                <RefreshCw size={16} />
                Load backend cost
              </button>
              <div className="model-list">
                {cost.by_model.map((item) => (
                  <div className="model-row" key={item.model}>
                    <strong>{item.model}</strong>
                    <span>{item.runs} runs</span>
                    <span>{formatTokens(item.tokens)} tokens</span>
                    <span>{formatCurrency(item.estimated_cost_usd)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function EvaluationPage({
  evaluation,
  busy,
  onRefresh,
  onSelectRun,
}: {
  evaluation: EvaluationSummary;
  busy: boolean;
  onRefresh: () => void;
  onSelectRun: (runId: number) => void;
}) {
  const totals = evaluation.summary;
  return (
    <section className="page-grid">
      <div className="panel wide">
        <div className="panel-title with-action">
          <div>
            <BarChart3 size={18} />
            <h3>Evaluation Run Summary</h3>
          </div>
          <button className="ghost-btn compact" onClick={onRefresh} disabled={busy} type="button">
            <RefreshCw size={16} />
            Refresh dashboard
          </button>
        </div>
        <div className="metric-grid">
          <MetricCard label="benchmarks" value={String(totals.total)} icon={Activity} tone="active" />
          <MetricCard label="passed / failed" value={`${totals.passed} / ${totals.failed}`} icon={CheckCircle2} tone="success" />
          <MetricCard label="pass rate" value={formatPercent(totals.pass_rate)} icon={BarChart3} tone="success" />
          <MetricCard label="avg score" value={totals.avg_score.toFixed(1)} icon={CheckCircle2} tone="queued" />
          <MetricCard label="patch lines" value={String(totals.total_patch_lines)} icon={FileCode2} tone="active" />
          <MetricCard label="changed files" value={String(totals.total_changed_files)} icon={Archive} tone="queued" />
          <MetricCard label="tests passed" value={String(totals.tests_passed)} icon={CheckCircle2} tone="success" />
          <MetricCard label="tokens / cost" value={`${formatTokens(totals.tokens)} / ${formatCurrency(totals.total_cost_usd)}`} icon={CircleDollarSign} tone="warning" />
        </div>
      </div>

      <div className="panel wide">
        <div className="panel-title">
          <BarChart3 size={18} />
          <h3>Profile Comparison</h3>
        </div>
        <div className="comparison-grid">
          {evaluation.profiles.map((profile) => (
            <div className="profile-summary" key={profile.profile}>
              <strong>{profile.profile}</strong>
              <span>{profile.passed}/{profile.total} passed, pass rate {formatPercent(profile.pass_rate)}, avg score {profile.avg_score.toFixed(1)}</span>
              <em>{profile.patch_lines} patch lines, {profile.changed_files} files, {formatTokens(profile.tokens)} tokens, {formatCurrency(profile.estimated_cost_usd)}</em>
            </div>
          ))}
        </div>
      </div>

      <div className="panel wide">
        <div className="panel-title">
          <Archive size={18} />
          <h3>Task-Level Comparison</h3>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>task_id</th>
                <th>profile</th>
                <th>status</th>
                <th>score</th>
                <th>patch_lines</th>
                <th>changed_files</th>
                <th>tests</th>
                <th>cost</th>
                <th>failure_type</th>
                <th>report</th>
              </tr>
            </thead>
            <tbody>
              {evaluation.tasks.map((row) => (
                <tr key={`${row.run_id}-${row.profile}`}>
                  <td>{row.task_id}</td>
                  <td>{row.profile}</td>
                  <td>{row.status}</td>
                  <td>{row.score}</td>
                  <td>{row.patch_lines}</td>
                  <td>{row.changed_files}</td>
                  <td>{row.tests_passed ? "pass" : "fail"}</td>
                  <td>{formatCurrency(row.estimated_cost_usd)}</td>
                  <td>{row.failure_type}</td>
                  <td>
                    {row.report_link ? (
                      <button className="link-btn" onClick={() => onSelectRun(row.run_id)} disabled={busy} type="button">
                        run #{row.run_id}
                      </button>
                    ) : (
                      "none"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel wide">
        <div className="panel-title">
          <RotateCcw size={18} />
          <h3>Retry Closure</h3>
        </div>
        {evaluation.retry_comparisons.length === 0 ? (
          <p className="muted">No retry comparison yet. Run a DeepSeek attempt, retry it with context, then refresh this dashboard.</p>
        ) : (
          <div className="comparison-grid">
            {evaluation.retry_comparisons.map((item) => (
              <div className="profile-summary" key={item.task_id}>
                <strong>{item.task_id}</strong>
                <span>{item.first_attempt_status} {"->"} {item.retry_status} / fail-to-pass: {item.fail_to_pass ? "yes" : "no"}</span>
                <em>retry cost {formatCurrency(item.retry_cost)}, patch lines {item.retry_patch_lines}, failure type {item.first_failure_type} {"->"} {item.retry_failure_type}</em>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
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

function TextField({
  label,
  value,
  onChange,
  textarea = false,
  tall = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  textarea?: boolean;
  tall?: boolean;
}) {
  return (
    <label className="form-row">
      <span>{label}</span>
      {textarea ? (
        <textarea className={tall ? "tall" : ""} value={value} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <input value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
  );
}

function realCallBlockedMessage(serverAllowsRealLlm: boolean): string {
  return serverAllowsRealLlm
    ? "Real DeepSeek call blocked: turn on the frontend request switch before submitting this API run."
    : "Real DeepSeek request switch is off. Turn it on to send allow_llm_calls=true; the backend LLM gate may still reject the call.";
}

function compactPath(value: string | null): string {
  if (!value) {
    return "not generated";
  }
  const normalized = value.split("\\").join("/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 2) {
    return value;
  }
  return `.../${parts.slice(-2).join("/")}`;
}

function explainFailure(run: Run): { title: string; message: string } | null {
  if (!["fail", "timeout", "cancelled"].includes(run.status)) {
    return null;
  }
  if (run.status === "timeout") {
    return { title: "Run timed out", message: "Open test-result and trace, then retry with a larger timeout or smaller task scope." };
  }
  if (run.failure_type === "NoPatch") {
    return { title: "No patch produced", message: "The agent did not change an allowed file. Retry with context after inspecting trace." };
  }
  if (run.failure_type === "TestFailed") {
    return { title: "Tests failed", message: "The patch exists but acceptance failed. Retry can carry the failure evidence forward." };
  }
  return { title: run.failure_type ?? "Run failed", message: run.error_message ?? "Check scorecard, test-result, and trace before retrying." };
}

export default App;
