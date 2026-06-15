# 面试讲稿

## 30 秒介绍

OpenAgent Platform Backend 是 OpenAgent Harness 的服务化后端层。Harness 负责真正的 Coding Agent 执行，包括工具调用、代码修改、测试验证、trace、scorecard 和 report。Platform 负责把它变成一个可管理的后端服务：任务提交、run 状态机、异步 worker、幂等提交、Redis 限流、缓存治理、artifact 查询和 token/cost 统计。

## 2 分钟项目讲法

这个项目分两层。

第一层是 OpenAgent Harness，它是执行层。给一个 `task.json` 后，Harness 会创建隔离工作区，让模型按 JSON action 调工具，执行局部 patch、pytest 验收和权限检查，最后输出 `patch.diff`、`test_result.json`、`scorecard.json`、`trace.jsonl` 和 `report.html`。

第二层是 OpenAgent Platform Backend，它是控制层。用户通过 `/tasks` 和 `/runs` 提交任务，后端先做幂等判断和限流，再创建 pending run。run 可以用 FastAPI BackgroundTasks 本地执行，也可以由独立 worker 消费 pending run。worker 调 Harness subprocess，执行结束后把状态、artifact 路径和 token/cost 写回数据库。用户再通过 `/runs/{id}/report`、`/patch`、`/scorecard` 和 `/metrics/cost` 查询结果。

这个设计重点不是封装一个大模型 API，而是解决 Agent 落地里的后端问题：任务可追踪、结果可验证、成本可控、重复提交不重复扣费，缓存和限流能防止流量或费用失控。

## 高频追问

### 为什么不直接在 FastAPI 里写 Agent loop？

因为 Harness 是执行平面，Platform 是控制平面。Agent loop 涉及工具权限、上下文压缩、patch、测试和 report，放在 Harness 里更容易复用和评测。Platform 只依赖 CLI 和 artifact contract，这样后端不会和模型执行细节耦合。

### 幂等为什么重要？

真实 LLM run 会花钱。用户重复点击、网络重试或前端超时重发时，如果没有 `Idempotency-Key`，就会重复创建 run 并重复调用模型。现在同一个用户和同一个 key 会返回同一个 run，避免重复扣费。

### 为什么要限流？

Agent run 比普通 API 请求更贵，因为它可能触发模型调用、子进程、测试执行和 artifact 写入。Redis 限流用于控制每个用户每分钟提交次数；Redis 不可用时 fallback 到内存，保证本地演示不崩。

### 缓存治理怎么体现？

- 缓存穿透：不存在的 run id 会做 negative cache。
- 缓存击穿：cache 提供 per-key lock，可用于热点 artifact metadata 回源。
- 缓存雪崩：TTL 加 jitter，避免大量 key 同时过期。

### 为什么要独立 worker？

本地 demo 可以用 BackgroundTasks，但真实系统里 API 进程不应该长期执行耗时 Agent run。独立 worker 让 API 只负责写 pending run，worker 负责消费和执行，后续可以替换成 Celery、RQ、Dramatiq 或 Redis Stream。

### 如何保证 key 安全？

Platform 不存 raw API key。真实调用需要两层开关：环境变量 `ALLOW_REAL_LLM_CALLS=true`，请求体 `allow_llm_calls=true`。key 只从本地 `.env` 或 shell 环境读取，`.env` 被 `.gitignore` 排除。

## 简历口径

OpenAgent Platform Backend：围绕 Coding Agent Harness 构建服务化后端，使用 FastAPI + SQLAlchemy + SQLite/PostgreSQL + Redis + 独立 worker，实现任务提交、run 状态机、幂等提交、限流、缓存治理、artifact 管理和 token/cost 统计；通过 subprocess 对接 DeepSeek Coding Agent Harness，使 Agent 执行结果可追踪、可验证、可控成本。
