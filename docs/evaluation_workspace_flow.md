# Evaluation 工作流

这份文档只描述当前主线：用户粘贴源码，平台整理评测任务，多模型同时运行，结果按 Evaluation 聚合展示。

## 用户视角

用户只需要理解 4 个概念：

- Workspace：当前账号或项目空间。
- Task：这次要修的代码问题。
- Model Set：参与对比的模型集合。
- Evaluation：一次完整评测，下面挂多个模型 run。

用户不需要理解：

- Harness CLI
- `task.json`
- `profiles.json`
- allowlist
- worker 内部队列
- tenant 表结构

## 主流程

```text
1. 用户粘贴源码、文件名、目标和可选测试
2. POST /evaluation-drafts
3. 后端 CodeDifficultyAnalyzer 判断难度、风险和建议策略
4. 前端展示系统判断，用户确认或继续用提示词调整草稿
5. 用户选择多个模型
6. POST /evaluations
7. 后端创建一个 Evaluation、一个 Harness task、多个 pending run
8. BackgroundTasks 或 Worker 执行 run
9. Harness 生成 patch/test-result/trace/scorecard/report/usage
10. Dashboard/History 展示结果矩阵、失败反馈、成本和证据
```

## API 合同

`POST /evaluation-drafts`

```json
{
  "source_filename": "config_loader.py",
  "source_code": "def load_config(...): ...",
  "instruction": "合并用户配置和默认配置，不能修改 DEFAULTS",
  "current_test_code": "可选，已有测试"
}
```

返回重点：

```json
{
  "name": "load_config 行为修复评测",
  "goal": "修复配置合并逻辑并通过边界测试",
  "test_code": "pytest 测试草稿",
  "difficulty_level": "medium",
  "difficulty_score": 52,
  "difficulty_reasons": ["有类和多个分支", "涉及嵌套 dict 合并"],
  "risk_factors": ["missing_tests", "mutable_defaults"],
  "suggested_strategy": {
    "agent_mode": "standard Agent Loop",
    "validation": "pytest 验证",
    "retry": "允许一次 retry"
  }
}
```

`POST /evaluations`

```json
{
  "name": "Config Merge",
  "goal": "合并用户配置和默认配置，保留嵌套 headers，不能修改 DEFAULTS。",
  "files": [
    {"path": "config_loader.py", "content": "源码"}
  ],
  "test_files": [
    {"path": "test_config_loader.py", "content": "pytest 测试"}
  ],
  "model_profiles": [
    {"name": "DeepSeek API", "mode": "api", "model": "deepseek-v4-flash", "allow_llm_calls": true},
    {"name": "NewAPI 5.4", "mode": "api", "model": "gpt-5.4", "model_provider": "newapi-5.4", "base_url": "https://api.sbbbbbbbbb.xyz/v1", "wire_api": "chat_completions", "allow_llm_calls": true},
    {"name": "NewAPI 5.5", "mode": "api", "model": "gpt-5.5", "model_provider": "newapi-5.5", "base_url": "https://api.sbbbbbbbbb.xyz/v1", "wire_api": "chat_completions", "allow_llm_calls": true}
  ],
  "acceptance_command": "python -m pytest -q",
  "context_summary_files": 16
}
```

请求头：

```text
Idempotency-Key: console-evaluation-<client-generated-id>
X-Workspace-ID: default
```

`Idempotency-Key` 用来防止用户重复点击导致重复创建 Evaluation。`X-Workspace-ID` 是后端隔离边界，未来由登录账号自动映射。

## Evaluation 和 Run 的关系

```text
Evaluation: Config Merge
  Task: config_loader.py 修复任务
    Run: DeepSeek API
    Run: NewAPI 5.4
    Run: NewAPI 5.5
```

这样前端可以按“单次任务”做横向对比，而不是展示一堆散乱 run。

## 执行闭环

```text
API 创建 Evaluation
  -> 生成 Harness TaskSpec
  -> 创建 N 个 pending Run
  -> 入队或 BackgroundTasks 调度
  -> Worker 回查 DB
  -> pending -> running 原子抢占
  -> Harness 执行
  -> Artifact 和 Usage 回写 DB
  -> Matrix/History/Cost 展示
```

本地 demo：

- `AUTO_START_RUNS=true`
- FastAPI `BackgroundTasks` 直接执行

API/worker 分离：

- `AUTO_START_RUNS=false`
- `QUEUE_BACKEND=db|redis`
- `python -m app.worker`

Redis 当前是 List MVP。它能证明 API/worker 边界和重复入队安全，但不是 crash-safe。生产版要升级 Redis Streams、processing queue、ack/retry/dead-letter。

## 面试讲法

> 我把产品边界从 Harness 命令上移到 Evaluation。用户提交源码、目标和模型集合一次，平台自动生成 Harness 可执行任务，拆成多个模型 run，并把 patch、测试、trace、scorecard、成本和历史聚合成一个结果矩阵。这样面试官看到的不是单次模型调用，而是一个可复现、可对比、可追踪的 Coding Agent 评测系统。
