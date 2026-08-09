"""测试 Skill 自我迭代引擎。"""

import tempfile
from pathlib import Path

from soloflow.core.auto_iter import _extract_json, iterate_skill
from soloflow.models.skill import CoSTAR, SkillConfig, SkillFile, SkillMeta


def test_extract_json_pure():
    """测试纯 JSON 提取。"""
    result = _extract_json('{"score": 0.85, "issues": ["a", "b"]}')
    assert result is not None
    assert result["score"] == 0.85
    assert len(result["issues"]) == 2


def test_extract_json_code_block():
    """测试 ```json ... ``` 包裹的 JSON。"""
    text = """
Some text before...
```json
{"score": 0.92, "issues": ["issue1"], "suggestions": ["fix1"]}
```
Some text after...
"""
    result = _extract_json(text)
    assert result is not None
    assert result["score"] == 0.92


def test_extract_json_plain_code_block():
    """测试 ``` ... ``` 包裹的 JSON。"""
    text = """
```
{"score": 0.78, "issues": ["a"], "suggestions": ["b"]}
```
"""
    result = _extract_json(text)
    assert result is not None
    assert result["score"] == 0.78


def test_extract_json_embedded():
    """测试嵌入在其他文字中的 JSON。"""
    text = 'Here is the evaluation: {"score": 0.65, "issues": ["x"]} Thanks!'
    result = _extract_json(text)
    assert result is not None
    assert result["score"] == 0.65


def test_extract_json_invalid():
    """测试无效内容返回 None。"""
    result = _extract_json("This is not JSON at all.")
    assert result is None


def test_extract_json_empty():
    """测试空字符串。"""
    result = _extract_json("")
    assert result is None
    result = _extract_json(None)
    assert result is None


def test_iterate_skill_dry_run():
    """测试 dry_run 模式迭代。"""
    skill = SkillFile(
        meta=SkillMeta(name="test-iter-skill", description="测试迭代"),
        costar=CoSTAR(
            context="You are a helpful assistant.",
            objective="Answer questions clearly.",
        ),
        config=SkillConfig(),
        body="## Instructions\n\nProvide concise answers.",
    )

    with tempfile.TemporaryDirectory() as tmp:
        skill_path = Path(tmp) / "SKILL.md"
        # 先保存
        from soloflow.core.skill_loader import save_skill

        save_skill(skill, skill_path)

        result = iterate_skill(
            skill,
            skill_path,
            count=2,
            test_inputs=["What is AI?"],
            dry_run=True,
        )

        # dry_run 应该返回原始的 skill（不修改）
        assert result.meta.name == "test-iter-skill"
        # 迭代版本应该已更新
        assert result.iteration.version > 0


def test_iterate_skill_artifact_saved():
    """测试迭代产物目录创建。"""
    from soloflow.core.auto_iter import _save_iteration_artifact

    with tempfile.TemporaryDirectory() as tmp:
        # 使用 mock 的 ITER_DIR
        import soloflow.core.auto_iter as ai

        orig = ai.ITER_DIR
        try:
            ai.ITER_DIR = Path(tmp)
            path = _save_iteration_artifact("test-skill", 1, "test_1_output", "Sample output")
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "Sample output" in content
        finally:
            ai.ITER_DIR = orig
