# 后端设计

OpenAgent Platform Backend 是 Coding Agent 评测平台的控制面。它不重新实现 Agent 修改代码的能力，而是把 Harness 的执行能力服务化，补齐任务创建、异步调度、状态管理、artifact 查询、失败反馈、历史管理和成本统计。

## 系统边界

```text
Platform Backend
  负责：API、数据模型、队列、worker、状态机、artifact API、成本、历史、幂等

OpenAgent Harness
  负责：Agent loop、读取代码、修改代码、运行 pytest、生成 patch/trace/report/scorecard
```

面试时不要把 Harness 细节当作用户入口讲。用户入口是 Evaluation，Harness 是执行引擎。

## 数据模型

| 模型 | 含义 |
|---|---|
| Tenant | 未来账号/组织隔离边界，当前不作为前端主概念 |
| Workspace | 用户任务空间，未来由登录账号自动映射 |
| Task | 一次待修复代码任务，对应 Harness task spec |
| Evaluation | 用户发起的一次评测，聚合一个 Task 和多个 Run |
| Run | 某个模型对某个 Task 的一次执行 |
| Usage | run 的 token 和成本记录 |

关系：

```text
Workspace
  -> Task
      -> Evaluation
      -> Run
          -> Usage
```

## 状态机

```text
pending -> running -> pass
pending -> running -> fail
pending -> running -> timeout
pending/running -> cancelled
```

状态写入数据库，前端通过 run/history/matrix API 查询。失败不是静默吞掉，而是记录 `failure_type`、`error_message` 和 artifact 链接。

## 幂等设计

创建幂等：

- `POST /evaluations` 支持 `Idempotency-Key`。
- 用户重复点击同一次提交时，后端返回已有 Evaluation 和 run。
- 同一个 key 如果 payload 不一致，应返回冲突或复用已有记录，避免制造重复评测。

执行幂等：

- worker 执行前必须通过数据库原子更新 `pending -> running` 抢占 run。
- 如果抢占失败，说明 run 已被其他 worker 执行、取消或完成，当前 worker 跳过。

这两个幂等解决的是不同问题：API 幂等防重复创建，worker 幂等防重复执行。

## QueueBackend

`DBPollingQueueBackend`：

- 默认 fallback。
- worker 扫描最早的 pending run。
- 适合本地 demo 和 SQLite。

`RedisQueueBackend`：

- API 创建 run 后 push `run_id` 到 Redis list。
- worker pop 后必须回查 DB。
- 只有 pending run 才会继续执行。
- 已取消、已完成、不存在的 run 直接跳过。
- 重复入队依赖 DB 原子抢占避免重复执行。

当前 Redis List 是 MVP，不承诺 crash-safe。如果 worker pop 后崩溃，队列项可能丢失。生产化路线：

- pending queue + processing queue
- Redis Streams consumer group
- ack/retry scanner
- dead-letter queue
- run lease/heartbeat

## Worker 执行

```text
dequeue run_id
  -> db.get(run)
  -> skip non-pending
  -> claim pending -> running
  -> call HarnessClient.run_task
  -> parse artifacts and usage
  -> write pass/fail/timeout/cancelled
  -> record evaluation memory
```

取消逻辑：

- pending/running run 可被标记为 `cancelled`。
- 本地 BackgroundTasks 模式可通过进程 registry 终止 Harness subprocess。
- worker 模式下，worker 在执行期间轮询 DB，发现取消后终止自己启动的进程。

## HarnessClient

HarnessClient 是 Platform 和 Harness 的边界：

- 组装 CLI 参数。
- 注入 provider base_url/wire_api/model key 环境变量。
- 控制 timeout。
- 解析 Harness stdout。
- 定位 artifact 目录。
- 解析 usage、scorecard、gate 和失败信息。

Executor：

- `HARNESS_EXECUTOR=local`：本地 subprocess，适合 demo。
- `HARNESS_EXECUTOR=docker`：每次 run 用容器隔离执行环境，适合下一阶段展示。

## Artifact 设计

每个 run 的证据包括：

- `patch.diff`：模型改了什么。
- `test_result.json`：pytest 输出。
- `scorecard.json`：评分、通过状态、失败类型。
- `trace.jsonl`：Agent 每一步轨迹。
- `report.html`：可读报告。
- `api_agent_run.json`：Agent loop 策略和步骤。

这些证据通过 `/runs/{id}/...` API 暴露给前端。它们让结果可审计，而不是只相信模型自述。

## 成本统计

成本按 Platform 的 provider/model 标签聚合：

```text
coalesce(Run.model_provider, Run.model, Usage.model)
```

这样 `newapi-5.4` 和 `newapi-5.5` 不会被底层 usage model 混在一起。前端主展示：

- DeepSeek API
- NewAPI 5.4
- NewAPI 5.5

## 当前边界

- SQLite 是本地 demo 默认数据库，生产可迁移 PostgreSQL。
- Redis List 是异步队列 MVP，不是最终可靠队列。
- tenant/workspace 是后端隔离基础，前端不应把“租户”作为用户操作概念。
- Docker executor 已接入路径，但面试主线应先讲 Evaluation 闭环和证据闭环。

## 面试讲法

> 我把系统拆成控制面、数据面、调度面、执行面和证据面。控制面负责 Evaluation 和 Run 生命周期；数据面记录任务、状态和成本；调度面用 BackgroundTasks 或 QueueBackend 把长任务交给 worker；执行面由 Harness 完成 Agent loop；证据面把 patch、测试、trace、scorecard 和 report 回写给平台。这样项目不只是能调模型，而是能可靠地管理一次多模型评测的完整生命周期。
