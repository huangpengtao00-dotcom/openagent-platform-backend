from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CodeDifficultyResult:
    difficulty_level: str
    difficulty_score: int
    reasons: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    suggested_strategy: dict[str, object] = field(default_factory=dict)


class CodeDifficultyAnalyzer:
    def analyze(
        self,
        *,
        source_code: str,
        filename: str = "app.py",
        user_goal: str = "",
        tests: str | None = None,
    ) -> CodeDifficultyResult:
        score = 0
        reasons: list[str] = []
        risks: list[str] = []
        lines = [line for line in source_code.splitlines() if line.strip() and not line.strip().startswith("#")]
        line_count = len(lines)
        if line_count >= 160:
            score += 22
            reasons.append("代码行数较多，需要更长上下文。")
        elif line_count >= 80:
            score += 14
            reasons.append("代码超过 80 行，理解成本上升。")
        elif line_count >= 25:
            score += 7
            reasons.append("代码行数适中，需要覆盖主要路径。")

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return CodeDifficultyResult(
                difficulty_level="hard",
                difficulty_score=90,
                reasons=["源码无法被 Python AST 解析，可能粘贴不完整或存在语法问题。"],
                risk_factors=["syntax_error"],
                suggested_strategy=_strategy_for("hard"),
            )

        function_count = _count_nodes(tree, (ast.FunctionDef, ast.AsyncFunctionDef))
        class_count = _count_nodes(tree, (ast.ClassDef,))
        branch_count = _count_nodes(tree, (ast.If, ast.For, ast.While, ast.Try, ast.AsyncFor, ast.Match))
        nesting_depth = _max_nesting_depth(tree)
        import_names = _import_names(tree)

        if function_count >= 6:
            score += 14
            reasons.append(f"函数数量较多：{function_count} 个。")
        elif function_count >= 2:
            score += 7
            reasons.append(f"存在多个函数入口：{function_count} 个。")
        if class_count >= 2:
            score += 16
            reasons.append(f"包含多个类：{class_count} 个。")
        elif class_count == 1:
            score += 10
            reasons.append("包含类或对象状态。")
        if branch_count >= 8:
            score += 16
            reasons.append("分支/循环/异常路径较多。")
        elif branch_count >= 3:
            score += 12
            reasons.append("有多个分支或异常路径。")
        elif branch_count > 0:
            score += 4
            reasons.append("存在基础分支逻辑。")
        if nesting_depth >= 4:
            score += 12
            reasons.append("嵌套深度较高，局部修改更容易引入回归。")
        elif nesting_depth >= 2:
            score += 8
            reasons.append("存在嵌套控制流。")

        lower = source_code.lower()
        if _has_any(lower, ["open(", "pathlib", "os.", "shutil", "file", "artifact"]):
            score += 10
            reasons.append("涉及 IO 或路径处理。")
            risks.append("io_path_boundary")
        if _has_any(lower, ["requests", "http", "urllib", "aiohttp", "429", "timeout"]):
            score += 14
            reasons.append("涉及网络、超时或限流。")
            risks.append("network_or_rate_limit")
        if _has_any(lower, ["sqlite", "sqlalchemy", "database", "db.", "session", "redis"]):
            score += 12
            reasons.append("涉及数据库或 Redis 状态。")
            risks.append("stateful_storage")
        if _has_any(lower, ["async def", "await ", "thread", "lock", "queue", "worker", "concurrent"]):
            score += 16
            reasons.append("涉及异步、并发或 worker 队列。")
            risks.append("async_concurrency")
        if import_names:
            external_imports = [name for name in import_names if name not in _STDLIB_LIKE_IMPORTS]
            if external_imports:
                score += min(12, 4 + len(external_imports) * 2)
                reasons.append("存在外部依赖。")
                risks.append("external_dependencies")

        if not tests or not tests.strip():
            score += 12
            reasons.append("缺少用户提供的测试。")
            risks.append("missing_tests")
        elif "pytest" not in tests and "assert" not in tests:
            score += 6
            reasons.append("测试输入不明显，需要补充可自动验收断言。")
            risks.append("weak_tests")

        goal_text = user_goal.strip()
        if _goal_is_vague(goal_text):
            score += 12
            reasons.append("目标描述较模糊。")
            risks.append("vague_goal")

        if _looks_multi_file(filename, source_code, goal_text):
            score += 12
            reasons.append("修改可能跨多个文件。")
            risks.append("multi_file_change")

        score = max(0, min(100, score))
        if score >= 65:
            level = "hard"
        elif score >= 30:
            level = "medium"
        else:
            level = "easy"
        if not reasons:
            reasons.append("代码短、入口少、分支少，适合快速单 Agent 验证。")
        return CodeDifficultyResult(
            difficulty_level=level,
            difficulty_score=score,
            reasons=reasons[:8],
            risk_factors=risks[:8],
            suggested_strategy=_strategy_for(level),
        )


def _strategy_for(level: str) -> dict[str, object]:
    if level == "easy":
        return {
            "agent_mode": "single_agent",
            "context": "short",
            "iterations": "low",
            "scripted_fallback": True,
            "notes": ["单 Agent", "short context", "低 iteration", "scripted fallback 可用"],
        }
    if level == "medium":
        return {
            "agent_mode": "standard_agent_loop",
            "context": "context_builder",
            "verification": "pytest",
            "retry": 1,
            "notes": ["标准 Agent Loop", "ContextBuilder 检索", "pytest 验证", "允许一次 retry"],
        }
    return {
        "agent_mode": "planner_reviewer_ready",
        "context": "long_budget",
        "quality_gate": "strict",
        "retry": "multi_round",
        "notes": ["更长 budget", "更严格 QualityGate", "多轮 retry", "后续可接 Multi-Agent Planner/Reviewer"],
    }


def _count_nodes(tree: ast.AST, node_types: tuple[type[ast.AST], ...]) -> int:
    return sum(isinstance(node, node_types) for node in ast.walk(tree))


def _max_nesting_depth(node: ast.AST, depth: int = 0) -> int:
    nesting_nodes = (ast.If, ast.For, ast.While, ast.Try, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Match)
    next_depth = depth + 1 if isinstance(node, nesting_nodes) else depth
    children = list(ast.iter_child_nodes(node))
    if not children:
        return next_depth
    return max(_max_nesting_depth(child, next_depth) for child in children)


def _import_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _goal_is_vague(goal: str) -> bool:
    if not goal:
        return True
    compact = re.sub(r"\s+", "", goal.lower())
    vague_terms = ["优化", "改进", "修一下", "有问题", "不好用", "提升", "完善", "fix", "improve", "better"]
    return len(compact) < 12 or any(term in compact for term in vague_terms)


def _looks_multi_file(filename: str, source_code: str, goal: str) -> bool:
    text = f"{filename}\n{source_code}\n{goal}".lower()
    return _has_any(text, ["from app.", "from .", "import app.", "多个文件", "多文件", "cross-file", "multi-file", "service", "router"])


_STDLIB_LIKE_IMPORTS = {
    "abc",
    "argparse",
    "ast",
    "asyncio",
    "collections",
    "contextlib",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "random",
    "re",
    "shlex",
    "statistics",
    "string",
    "subprocess",
    "sys",
    "tempfile",
    "time",
    "typing",
    "uuid",
}
