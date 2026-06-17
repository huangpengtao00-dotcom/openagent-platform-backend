import { useMemo, useState } from "react";
import {
  Activity,
  Archive,
  BarChart3,
  Boxes,
  CheckCircle2,
  CircleDollarSign,
  FileCode2,
  GitBranch,
  Layers3,
  PauseCircle,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
  TerminalSquare,
} from "lucide-react";
import { cancelRun, createRun, createTask, getArtifact, getCostMetrics, getRun } from "./api";
import { demoArtifact, demoCost, demoEvidenceSections, demoRun, getDemoArtifact, type ArtifactKind } from "./mockData";
import { buildEvaluationRequest, evaluationProfiles } from "./runProfiles";
import {
  dataSourceLabel,
  formatCurrency,
  formatTokens,
  runTimeline,
  statusTone,
  type CostMetrics,
  type DataSource,
  type Run,
  type RunStatus,
} from "./domain";

type NavItem = "overview" | "runs" | "artifacts" | "cost" | "evidence";

const navItems: Array<{ id: NavItem; label: string; icon: typeof Boxes }> = [
  { id: "overview", label: "总览", icon: Boxes },
  { id: "runs", label: "运行", icon: Activity },
  { id: "artifacts", label: "产物", icon: Archive },
  { id: "cost", label: "成本", icon: CircleDollarSign },
  { id: "evidence", label: "证据", icon: TerminalSquare },
];

const statuses: RunStatus[] = ["pending", "running", "pass", "fail", "timeout", "cancelled"];
const artifactKinds: ArtifactKind[] = ["report", "patch", "scorecard", "test-result", "trace"];

const initialNotice =
  typeof window !== "undefined" && window.location.protocol === "file:"
    ? "当前为离线展示模式，可直接双击打开；启动后端服务后可使用真实接口演示。"
    : "当前为本地展示模式；启动 FastAPI 后端后，运行、产物和成本按钮会调用真实接口。";

function App() {
  const [active, setActive] = useState<NavItem>("overview");
  const [run, setRun] = useState<Run>(demoRun);
  const [cost, setCost] = useState<CostMetrics>(demoCost);
  const [artifactKind, setArtifactKind] = useState<ArtifactKind>("scorecard");
  const [artifact, setArtifact] = useState(demoArtifact);
  const [runIdInput, setRunIdInput] = useState("1");
  const [notice, setNotice] = useState(initialNotice);
  const [busy, setBusy] = useState(false);
  const [dataSource, setDataSource] = useState<DataSource>("sample");
  const [profileId, setProfileId] = useState(evaluationProfiles[0].id);

  const selectedTone = statusTone(run.status);
  const timeline = runTimeline(run.status);
  const selectedProfile = evaluationProfiles.find((profile) => profile.id === profileId) ?? evaluationProfiles[0];
  const architecture = useMemo(
    () => [
      ["Harness", "执行面", "任务执行、代码修改、测试、trace、报告"],
      ["Platform API", "控制面", "任务、运行、取消、产物、成本统计"],
      ["Worker", "异步层", "消费 pending run 并管理 Harness 子进程"],
      ["Artifacts", "证据层", "report、patch、scorecard、trace"],
    ],
    [],
  );

  async function runLive<T>(action: () => Promise<T>, onSuccess: (value: T) => void, message: string) {
    setBusy(true);
    try {
      const value = await action();
      onSuccess(value);
      setDataSource("live");
      setNotice(message);
    } catch (error) {
      setDataSource("offline");
      setNotice(error instanceof Error ? `接口调用失败：${error.message}` : "接口调用失败，请确认后端服务已启动。");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateRun() {
    const request = buildEvaluationRequest(selectedProfile);
    await runLive(
      async () => {
        const task = await createTask(request.task);
        const createdRun = await createRun({ task_id: task.task_id, ...request.run }, request.idempotencyKey);
        setRunIdInput(String(createdRun.run_id));
        return createdRun;
      },
      setRun,
      `${selectedProfile.label} started: mode=${request.run.mode}, model=${request.run.model}, allow_llm_calls=${request.run.allow_llm_calls}.`,
    );
  }

  async function handleRefreshRun() {
    const id = Number(runIdInput || run.run_id);
    await runLive(() => getRun(id), setRun, `已加载 run #${id}。`);
  }

  async function handleCancelRun() {
    await runLive(() => cancelRun(run.run_id), setRun, `已向 run #${run.run_id} 发送取消请求。`);
  }

  async function handleLoadCost() {
    await runLive(getCostMetrics, setCost, "已加载实时成本统计。");
  }

  async function handleLoadArtifact(kind = artifactKind) {
    setArtifact(getDemoArtifact(kind));
    setDataSource("sample");
    setNotice(`已切换到 ${kind} 脱敏示例产物；如果后端在线，会自动替换为 run #${run.run_id} 的真实内容。`);
    setBusy(true);
    try {
      const liveArtifact = await getArtifact(run.run_id, kind);
      setArtifact(liveArtifact);
      setDataSource("live");
      setNotice(`已加载 run #${run.run_id} 的真实 ${kind}。`);
    } catch {
      setDataSource("offline");
      setNotice(`后端未返回 ${kind}，当前显示脱敏示例产物，适合离线展示。`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">OA</div>
          <div>
            <strong>OpenAgent</strong>
            <span>平台控制台</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="控制台导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={active === item.id ? "nav-item active" : "nav-item"}
                key={item.id}
                onClick={() => setActive(item.id)}
                type="button"
              >
                <Icon size={17} />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="side-note">
          <ShieldCheck size={18} />
          <span>浏览器端不保存密钥；真实模型调用必须经过环境变量和请求参数双重确认。</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">AgentOps 控制面</p>
            <h1>OpenAgent Platform 可视化控制台</h1>
          </div>
          <div className="topbar-actions">
            <div className={`source-pill ${dataSource}`}>{dataSourceLabel(dataSource)}</div>
            <div className={`status-pill ${selectedTone}`}>
              <span />
              run #{run.run_id} · {run.status}
            </div>
          </div>
        </header>

        <section className="notice">
          <TerminalSquare size={18} />
          <span>{notice}</span>
        </section>

        {active === "overview" && (
          <section className="page-grid overview-grid">
            <div className="hero-panel">
              <div className="hero-copy">
                <h2>Harness 负责执行，Platform 负责控制和证据。</h2>
                <p>这个控制台用于展示后端平台的可观察能力：任务提交、异步运行状态、取消控制、产物查看和成本统计。</p>
              </div>
              <div className="flow-map">
                {architecture.map(([name, role, detail], index) => (
                  <div className="flow-node" key={name}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{name}</strong>
                    <em>{role}</em>
                    <p>{detail}</p>
                  </div>
                ))}
              </div>
            </div>

            <MetricCard label="自动化测试" value="25 passed" icon={CheckCircle2} tone="success" />
            <MetricCard label="运行状态" value="6 states" icon={GitBranch} tone="active" />
            <MetricCard label="进程取消" value="enabled" icon={PauseCircle} tone="warning" />
            <MetricCard label="成本保护" value="double opt-in" icon={ShieldCheck} tone="queued" />

            <div className="panel wide">
              <div className="panel-title">
                <Layers3 size={18} />
                <h3>架构边界</h3>
              </div>
              <div className="boundary">
                <div>
                  <strong>OpenAgent Harness</strong>
                  <p>负责 agent loop、代码修改、工具调用、测试执行、评分和 HTML 报告。</p>
                </div>
                <div>
                  <strong>OpenAgent Platform Backend</strong>
                  <p>负责 FastAPI 资源、运行状态、worker 编排、产物访问和成本聚合。</p>
                </div>
                <div>
                  <strong>OpenAgent Console</strong>
                  <p>负责浏览器端展示和操作入口，不保存密钥，也不承载执行逻辑。</p>
                </div>
              </div>
            </div>
          </section>
        )}

        {active === "runs" && (
          <section className="page-grid two-col">
            <div className="panel">
              <div className="panel-title">
                <Play size={18} />
                <h3>评测控制</h3>
              </div>
              <p className="muted">选择一个 Harness 任务样例。scripted 是零成本基线；api 会触发真实 DeepSeek 评测，仍受后端双重开关保护。</p>
              <div className="form-row">
                <label htmlFor="eval-profile">Evaluation profile</label>
                <select
                  id="eval-profile"
                  value={profileId}
                  onChange={(event) => setProfileId(event.target.value as typeof profileId)}
                >
                  {evaluationProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className={`profile-summary ${selectedProfile.mode}`}>
                <strong>{selectedProfile.mode === "api" ? "真实 API 评测" : "安全 scripted 评测"}</strong>
                <span>{selectedProfile.description}</span>
                <em>{selectedProfile.budgetHint}</em>
              </div>
              <div className="form-row">
                <label htmlFor="run-id">Task / Run ID</label>
                <input id="run-id" value={runIdInput} onChange={(event) => setRunIdInput(event.target.value)} />
              </div>
              <div className="button-row">
                <button className="primary-btn" onClick={handleCreateRun} disabled={busy} type="button">
                  <Play size={16} />
                  启动所选评测
                </button>
                <button className="ghost-btn" onClick={handleRefreshRun} disabled={busy} type="button">
                  <RefreshCw size={16} />
                  刷新状态
                </button>
                <button className="danger-btn" onClick={handleCancelRun} disabled={busy} type="button">
                  <Square size={14} />
                  取消运行
                </button>
              </div>
            </div>

            <div className="panel run-panel">
              <div className="panel-title">
                <Activity size={18} />
                <h3>Run #{run.run_id}</h3>
              </div>
              <div className={`run-status ${selectedTone}`}>{run.status}</div>
              <div className="timeline" aria-label="运行状态时间线">
                {timeline.map((step) => (
                  <div className={`timeline-step ${step.state}`} key={`${step.status}-${step.label}`}>
                    <span />
                    <strong>{step.label}</strong>
                    <em>{step.status}</em>
                  </div>
                ))}
              </div>
              <dl className="detail-list">
                <div><dt>task</dt><dd>#{run.task_id}</dd></div>
                <div><dt>mode</dt><dd>{run.mode}</dd></div>
                <div><dt>model</dt><dd>{run.model}</dd></div>
                <div><dt>timeout</dt><dd>{run.timeout_seconds}s</dd></div>
                <div><dt>harness</dt><dd>{run.harness_run_id ?? "未分配"}</dd></div>
                <div><dt>usage</dt><dd>{run.usage ? formatCurrency(run.usage.estimated_cost_usd) : "暂无"}</dd></div>
              </dl>
              <div className="status-strip">
                {statuses.map((status) => (
                  <span className={`mini-status ${statusTone(status)}`} key={status}>{status}</span>
                ))}
              </div>
            </div>
          </section>
        )}

        {active === "artifacts" && (
          <section className="page-grid">
            <div className="panel wide">
              <div className="panel-title with-action">
                <div>
                  <FileCode2 size={18} />
                  <h3>运行产物</h3>
                </div>
                <span className={`source-pill ${dataSource}`}>{dataSourceLabel(dataSource)}</span>
              </div>
              <p className="muted artifact-help">示例产物来自本地 Harness 运行记录的脱敏片段；后端在线时会优先显示真实接口返回。</p>
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
          </section>
        )}

        {active === "cost" && (
          <section className="page-grid two-col">
            <MetricCard label="总运行数" value={String(cost.total_runs)} icon={Activity} tone="active" />
            <MetricCard label="总 token" value={formatTokens(cost.total_tokens)} icon={BarChart3} tone="queued" />
            <MetricCard label="预估成本" value={formatCurrency(cost.estimated_cost_usd)} icon={CircleDollarSign} tone="success" />
            <div className="panel">
              <div className="panel-title">
                <CircleDollarSign size={18} />
                <h3>按模型统计</h3>
              </div>
              <button className="ghost-btn compact" onClick={handleLoadCost} disabled={busy} type="button">
                <RefreshCw size={16} />
                加载实时统计
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

        {active === "evidence" && (
          <section className="page-grid evidence-page">
            {demoEvidenceSections.map((section) => (
              <div className="panel evidence-section" key={section.title}>
                <div className="panel-title">
                  <TerminalSquare size={18} />
                  <h3>{section.title}</h3>
                </div>
                <ul>
                  {section.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

function MetricCard({ label, value, icon: Icon, tone }: { label: string; value: string; icon: typeof Boxes; tone: string }) {
  return (
    <div className={`metric-card ${tone}`}>
      <Icon size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
