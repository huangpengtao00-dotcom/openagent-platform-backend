# 5 个演示模板

这些模板用于明天现场演示。用法：进入 `New Evaluation`，粘贴源码和目标，点击“分析源码”，让后端自动判断难度并生成评测草稿。不要手动选择难度。

建议现场只跑 1-3 个任务，避免真实模型触发 429 或预算限制。完整 15 个 benchmark 作为目录和证据备用。

## 模板 1：Easy - Duration Parser

目标：

```text
支持 "10s"、"2m"、"1h"；空值、格式错误或未知单位返回 0，不要抛异常。
```

源码文件：`duration_parser.py`

```python
def parse_duration(value):
    amount = int(value[:-1])
    unit = value[-1]
    if unit == "s":
        return amount
    if unit == "m":
        return amount * 60
    return amount
```

适合展示：

- 后端判断 easy。
- 简单边界条件。
- 模型能否补齐异常处理。

## 模板 2：Easy - Pagination Bounds

目标：

```text
修复分页边界：page 从 1 开始，小于 1 时按 1 处理；page_size 小于 1 时返回空列表。
```

源码文件：`pager.py`

```python
def page_items(items, page, page_size):
    start = page * page_size
    end = start + page_size
    return items[start:end]
```

适合展示：

- off-by-one。
- 输入边界。
- 简短 patch。

## 模板 3：Medium - Config Merge

目标：

```text
合并用户配置和默认配置，保留嵌套 headers，不能修改 DEFAULTS。
```

源码文件：`config_loader.py`

```python
DEFAULTS = {
    "timeout": 3,
    "headers": {"User-Agent": "OpenAgent", "Accept": "application/json"},
}


class ConfigLoader:
    def __init__(self, defaults=None):
        self.defaults = defaults or DEFAULTS

    def load_config(self, user_config):
        if user_config is None:
            return self.defaults
        if not isinstance(user_config, dict):
            raise ValueError("user_config must be a dict")
        config = self.defaults
        for key, value in user_config.items():
            config[key] = value
        return config


def load_config(user_config):
    return ConfigLoader().load_config(user_config)
```

适合展示：

- 后端判断 medium。
- 类、分支、嵌套 dict、可变默认值风险。
- 横向比较不同模型 patch 质量。

## 模板 4：Medium - Artifact Search Filters

目标：

```text
支持按 status 和 tag 过滤；分页不能越界；缺少 tags 字段时按空列表处理。
```

源码文件：`artifact_search.py`

```python
ARTIFACTS = [
    {"id": 1, "status": "pass", "tags": ["patch", "trace"]},
    {"id": 2, "status": "fail", "tags": ["cost"]},
    {"id": 3, "status": "pass"},
]


class ArtifactSearch:
    def __init__(self, rows=None):
        self.rows = rows or ARTIFACTS

    def search_artifacts(self, status=None, tag=None, page=1, page_size=10):
        rows = self.rows
        if status:
            rows = [row for row in rows if row["status"] == status]
        if tag:
            rows = [row for row in rows if tag in row["tags"]]
        if page < 1:
            raise ValueError("page must start from 1")
        start = page * page_size
        return rows[start:start + page_size]


def search_artifacts(status=None, tag=None, page=1, page_size=10):
    return ArtifactSearch().search_artifacts(status, tag, page, page_size)
```

适合展示：

- 多条件过滤。
- 缺字段失败反馈。
- 分页逻辑。

## 模板 5：Hard - Async Retry Client

目标：

```text
实现异步请求重试：429 和 timeout 可以重试，最多 retries 次；非 2xx 直接返回错误；成功返回 JSON。
```

源码文件：`async_client.py`

```python
import asyncio


class ApiClient:
    def __init__(self, session, retries=2):
        self.session = session
        self.retries = retries

    async def fetch_json(self, url):
        response = await self.session.get(url)
        if response.status == 429:
            await asyncio.sleep(0.1)
            response = await self.session.get(url)
        if response.status >= 400:
            return {"ok": False, "status": response.status}
        return await response.json()
```

适合展示：

- 后端判断 hard。
- async/await、IO、重试预算、异常处理。
- 解释为什么 hard 任务需要更长 budget、严格 QualityGate 和 retry。
