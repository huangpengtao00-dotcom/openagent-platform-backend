from app.difficulty_analyzer import CodeDifficultyAnalyzer


def test_simple_function_is_easy():
    result = CodeDifficultyAnalyzer().analyze(
        source_code="def add(a, b):\n    return a + b\n",
        filename="math_utils.py",
        user_goal="fix add for two integers",
        tests="def test_add():\n    assert add(1, 2) == 3\n",
    )

    assert result.difficulty_level == "easy"
    assert result.difficulty_score < 30
    assert result.suggested_strategy["agent_mode"] == "single_agent"


def test_class_exceptions_and_branches_are_medium():
    source = """
class ConfigLoader:
    def load(self, value):
        if value is None:
            raise ValueError("missing")
        if isinstance(value, dict):
            try:
                return value.copy()
            except Exception:
                return {}
        return {"value": value}
"""
    result = CodeDifficultyAnalyzer().analyze(
        source_code=source,
        filename="config_loader.py",
        user_goal="preserve nested defaults when loading config",
        tests="def test_load():\n    assert True\n",
    )

    assert result.difficulty_level == "medium"
    assert "标准 Agent Loop" in result.suggested_strategy["notes"]
    assert any("分支" in reason or "异常" in reason for reason in result.reasons)


def test_io_async_multi_file_missing_tests_and_vague_goal_are_hard():
    source = """
import aiohttp
import redis
from app.storage import save_artifact


class ArtifactWorker:
    async def run(self, queue):
        while True:
            item = await queue.get()
            async with aiohttp.ClientSession() as session:
                response = await session.get(item["url"], timeout=3)
                if response.status == 429:
                    continue
                with open(item["path"], "w") as handle:
                    handle.write(await response.text())
            save_artifact(item)
"""
    result = CodeDifficultyAnalyzer().analyze(
        source_code=source,
        filename="workers/artifact_worker.py",
        user_goal="优化一下",
        tests=None,
    )

    assert result.difficulty_level == "hard"
    assert result.difficulty_score >= 65
    assert {"io_path_boundary", "async_concurrency", "missing_tests", "vague_goal"}.issubset(set(result.risk_factors))
    assert result.suggested_strategy["quality_gate"] == "strict"
