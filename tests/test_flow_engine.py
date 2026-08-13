"""测试 Flow 编排引擎。"""

import pytest

from soloflow.core.flow_engine import _build_dag, _resolve_ref, _topological_sort
from soloflow.llm.client import LLMResult
from soloflow.models.flow import FlowDefinition, FlowStep


def test_resolve_ref_input():
    """测试 $input.xxx 引用解析。"""
    context = {"input": {"topic": "AI"}, "steps": {}}
    assert _resolve_ref("$input.topic", context) == "AI"
    assert _resolve_ref("plain text", context) == "plain text"


def test_resolve_ref_step_output():
    """测试 $steps.xxx.output 引用解析。"""
    context = {"input": {}, "steps": {"research": "research result"}}
    assert _resolve_ref("$steps.research.output", context) == "research result"


def test_resolve_ref_kebab_case_step_output():
    """Flow 允许 kebab-case step id，输出引用必须完整解析连字符。"""
    context = {"input": {}, "steps": {"agent-check": "SOLOFLOW_FLOW_OK"}}
    assert _resolve_ref("$steps.agent-check.output", context) == "SOLOFLOW_FLOW_OK"
    assert _resolve_ref("Result: $steps.agent-check.output", context) == "Result: SOLOFLOW_FLOW_OK"


def test_resolve_ref_inline():
    """测试内联引用。"""
    context = {"input": {"topic": "AI"}, "steps": {}}
    result = _resolve_ref("Write about $input.topic in detail", context)
    assert "AI" in result


def test_build_dag_simple():
    """测试简单 DAG。"""
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
    ]
    adj, rev = _build_dag(steps)
    assert adj["a"] == ["b"]
    assert rev["b"] == ["a"]
    assert adj["b"] == []


def test_build_dag_parallel():
    """测试并行依赖 DAG。"""
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["a"]),
    ]
    adj, rev = _build_dag(steps)
    assert set(adj["a"]) == {"b", "c"}
    assert rev["b"] == ["a"]
    assert rev["c"] == ["a"]


def test_topological_sort_linear():
    """测试线性 DAG 拓扑排序。"""
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["b"]),
    ]
    levels = _topological_sort(steps)
    assert len(levels) == 3
    assert levels[0] == ["a"]
    assert levels[1] == ["b"]
    assert levels[2] == ["c"]


def test_topological_sort_parallel():
    """测试并行层级拓扑排序。"""
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["a"]),
    ]
    levels = _topological_sort(steps)
    assert len(levels) == 2
    assert levels[0] == ["a"]
    assert set(levels[1]) == {"b", "c"}


def test_topological_sort_diamond():
    """测试钻石型 DAG。"""
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["a"]),
        FlowStep(id="d", skill="s4", depends_on=["b", "c"]),
    ]
    levels = _topological_sort(steps)
    assert len(levels) == 3
    assert levels[0] == ["a"]
    assert set(levels[1]) == {"b", "c"}
    assert levels[2] == ["d"]


def test_topological_sort_circular():
    """测试循环依赖检测。"""
    steps = [
        FlowStep(id="a", skill="s1", depends_on=["b"]),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
    ]
    with pytest.raises(ValueError, match="circular"):
        _topological_sort(steps)


def test_flow_definition_parse():
    """测试 Flow YAML 解析。"""
    import yaml

    yaml_str = """
name: test-flow
version: 1.0.0
description: Test flow
steps:
  - id: step1
    skill: market-researcher
  - id: step2
    skill: content-writer
    depends_on:
      - step1
"""
    data = yaml.safe_load(yaml_str)
    flow = FlowDefinition(**data)
    assert flow.name == "test-flow"
    assert len(flow.steps) == 2
    assert flow.steps[1].depends_on == ["step1"]


def test_validate_flow_ok():
    """测试校验通过的 Flow。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="test",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2", depends_on=["a"]),
        ],
    )
    issues = validate_flow(flow)
    assert len(issues) == 0


def test_validate_flow_unknown_dep():
    """测试引用不存在的依赖。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="test",
        steps=[
            FlowStep(id="a", skill="s1", depends_on=["nonexistent"]),
        ],
    )
    issues = validate_flow(flow)
    assert len(issues) > 0
    assert any("nonexistent" in i for i in issues)


def test_validate_flow_circular():
    """测试循环依赖检测。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="test",
        steps=[
            FlowStep(id="a", skill="s1", depends_on=["b"]),
            FlowStep(id="b", skill="s2", depends_on=["a"]),
        ],
    )
    issues = validate_flow(flow)
    assert any("circular" in i.lower() for i in issues)


# ── 失败恢复测试 ──


def test_failed_dependency_causes_skip():
    """测试依赖失败步骤时后续步骤应跳过。

    模拟场景：a→b→c，如果 a 失败，b 应该被跳过（但通过 execute_step 中的
    failed_step_ids 检查实现）。这里测试 _topological_sort 的层级正确性。
    """
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["b"]),
    ]
    levels = _topological_sort(steps)
    assert len(levels) == 3
    # a 在第一层，b 在第二层，c 在第三层
    assert levels[0] == ["a"]
    assert levels[1] == ["b"]
    assert levels[2] == ["c"]


def test_independent_branch_continues_after_failure():
    """测试独立分支在另一分支失败后继续执行。

    a → b → d (分支1)
    a → c     (分支2)
    如果 b 失败，d 应跳过，但 c 应继续正常执行。
    """
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["a"]),
        FlowStep(id="d", skill="s4", depends_on=["b"]),
    ]
    levels = _topological_sort(steps)
    # 层级：a → {b, c} → d
    assert len(levels) == 3
    assert levels[0] == ["a"]
    assert set(levels[1]) == {"b", "c"}
    assert levels[2] == ["d"]


def test_skip_step_not_in_failed_deps():
    """测试未依赖失败步骤的 step 不被跳过。

    验证 _build_dag 正确区分了直接依赖和间接依赖。
    a → b → c, a → d
    b 失败时，c 应该跳过（依赖 b），但 d 不跳过。
    """
    steps = [
        FlowStep(id="a", skill="s1"),
        FlowStep(id="b", skill="s2", depends_on=["a"]),
        FlowStep(id="c", skill="s3", depends_on=["b"]),
        FlowStep(id="d", skill="s4", depends_on=["a"]),
    ]
    adj, rev = _build_dag(steps)
    # c 依赖 b
    assert "b" in rev["c"]
    # d 不依赖 b
    assert "b" not in rev["d"]
    # d 依赖 a
    assert "a" in rev["d"]


# ── 多 Skill / Agent 支持测试 ──


def test_flow_step_with_agent_field():
    """测试 FlowStep 可以指定 agent 字段。"""
    step = FlowStep(
        id="write",
        skill="content-writer",
        agent="writing-agent",
        description="Write with agent role",
    )
    assert step.agent == "writing-agent"
    assert step.skill == "content-writer"


def test_flow_step_agent_optional():
    """测试 FlowStep 的 agent 字段可选。"""
    step = FlowStep(id="research", skill="market-researcher")
    assert step.agent is None


# ── 运行状态持久化测试 ──


def test_run_state_saved():
    """测试运行状态文件被创建。"""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from soloflow.core.flow_engine import _save_run_state

    with tempfile.TemporaryDirectory() as tmp:
        fake_runs_dir = Path(tmp) / ".soloflow" / "runs"
        with patch("soloflow.core.flow_engine.RUNS_DIR", fake_runs_dir):
            steps = {
                "research": {"status": "done", "error": None, "duration": 2.5},
                "write": {"status": "running", "error": None, "duration": 0.0},
            }
            _save_run_state("test-flow", "run-abc123", steps, "running", 5.0, 1000)

            run_file = fake_runs_dir / "run-abc123.json"
            assert run_file.exists()

            import json

            data = json.loads(run_file.read_text(encoding="utf-8"))
            assert data["flow_name"] == "test-flow"
            assert data["status"] == "running"
            assert "research" in data["steps"]
            assert data["steps"]["research"]["status"] == "done"


def test_run_state_multiple_runs():
    """测试多个运行记录共存。"""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from soloflow.core.flow_engine import _save_run_state

    with tempfile.TemporaryDirectory() as tmp:
        fake_runs_dir = Path(tmp) / ".soloflow" / "runs"
        with patch("soloflow.core.flow_engine.RUNS_DIR", fake_runs_dir):
            _save_run_state("flow-a", "run-001", {"s1": {"status": "done"}}, "done", 1.0)
            _save_run_state("flow-b", "run-002", {"s1": {"status": "failed"}}, "failed", 2.0)

            # 两个文件都应存在
            assert (fake_runs_dir / "run-001.json").exists()
            assert (fake_runs_dir / "run-002.json").exists()


# ── Flow 加载测试 ──


def test_load_flow_from_file():
    """测试从 YAML 文件加载 Flow 定义。"""
    import tempfile
    from pathlib import Path

    import yaml

    from soloflow.core.flow_engine import load_flow

    with tempfile.TemporaryDirectory() as tmp:
        flow_data = {
            "name": "test-load-flow",
            "version": "0.2.0",
            "description": "Flow for testing load",
            "steps": [
                {"id": "step1", "skill": "content-writer"},
                {"id": "step2", "skill": "code-reviewer", "depends_on": ["step1"]},
            ],
        }
        flow_path = Path(tmp) / "test.flow.yml"
        flow_path.write_text(
            yaml.dump(flow_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        flow = load_flow(flow_path)
        assert flow.name == "test-load-flow"
        assert flow.version == "0.2.0"
        assert len(flow.steps) == 2
        assert flow.steps[1].depends_on == ["step1"]


def test_load_flow_file_not_found():
    """测试文件不存在时抛异常。"""
    from soloflow.core.flow_engine import load_flow

    with pytest.raises(FileNotFoundError):
        load_flow("nonexistent_flow_file.flow.yml")


def test_load_flow_accepts_playbook_key(tmp_path):
    """Flow 新格式使用 playbook 字段时，内部仍归一化为 skill。"""
    from soloflow.core.flow_engine import load_flow

    flow_path = tmp_path / "playbook-flow.flow.yml"
    flow_path.write_text(
        """
name: playbook-flow
steps:
  - id: write
    playbook: content-writer
""",
        encoding="utf-8",
    )

    flow = load_flow(flow_path)
    assert flow.steps[0].skill == "content-writer"


# ── Dry run 测试 ──


def test_run_flow_dry_run():
    """测试 dry_run 模式不调用 LLM。"""
    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="dry-run-test",
        steps=[
            FlowStep(id="a", skill="content-writer"),
            FlowStep(id="b", skill="code-reviewer", depends_on=["a"]),
        ],
    )
    result = run_flow(flow, dry_run=True)
    assert result.status == "dry_run"
    assert len(result.steps) == 0  # 未执行任何步骤


# ── 输入校验测试 ──


def test_validate_inputs_required_missing():
    """测试缺少必填字段时报错。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "topic": {"type": "string", "required": True, "description": "报告主题"},
        "max_length": {"type": "integer", "required": False, "default": 3000},
    }
    issues = _validate_inputs(schema, {})
    assert any("缺少" in i and "topic" in i for i in issues)


def test_validate_inputs_all_ok():
    """测试所有必填字段都提供时通过。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "topic": {"type": "string", "required": True, "description": "报告主题"},
    }
    issues = _validate_inputs(schema, {"topic": "AI Agent"})
    critical = [i for i in issues if i.startswith("缺少")]
    assert len(critical) == 0


def test_validate_inputs_unknown_key():
    """测试传入未知参数时告警。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "topic": {"type": "string", "required": True, "description": "主题"},
    }
    issues = _validate_inputs(schema, {"topic": "AI", "extra_key": "value"})
    assert any("未知" in i and "extra_key" in i for i in issues)


def test_validate_inputs_empty_schema():
    """测试空 schema 时不做校验。"""
    from soloflow.core.flow_engine import _validate_inputs

    issues = _validate_inputs({}, {"anything": "goes"})
    assert len(issues) == 0


def test_run_flow_fails_on_missing_required():
    """测试缺少必填输入时 run_flow 直接返回 failed。"""
    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="validated-flow",
        input_schema={
            "topic": {"type": "string", "required": True, "description": "Topic"},
        },
        steps=[
            FlowStep(id="a", skill="content-writer"),
        ],
    )
    result = run_flow(flow, inputs={})  # 缺少必填 topic
    assert result.status == "failed"


def test_validate_inputs_default_values():
    """测试 input_schema 默认值生效。"""
    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="default-values-flow",
        input_schema={
            "style": {"type": "string", "required": False, "default": "professional"},
        },
        steps=[
            FlowStep(id="a", skill="content-writer"),
        ],
    )
    # 不传 style 参数时应该使用默认值，不会报 warning
    result = run_flow(flow, dry_run=True)
    assert result.status == "dry_run"


# ── BUG-FLOW-001/002/003: Flow 恢复端到端回归测试 ──


def test_flow_resume_end_to_end(monkeypatch, tmp_path):
    """BUG-FLOW-001/002/003 端到端回归测试。

    场景: A → B → C Flow
    - 第一次运行: A 完成（长输出 > 2000 字符）, B 失败, C skipped
    - 修复 B 后 resume: A 不重复调用, B/C 执行, 返回 done
    - 断言: 原 run_id 复用 + attempt 递增 + resumed_at + 完整 A 输出不丢失
    """
    import json
    from unittest.mock import patch

    import yaml

    from soloflow.core.flow_engine import load_flow, resume_flow, run_flow

    monkeypatch.chdir(tmp_path)
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow_yaml = {
        "name": "resume-e2e",
        "version": "1.0.0",
        "description": "E2E resume test",
        "input_schema": {"topic": {"type": "string", "required": True}},
        "steps": [
            {"id": "a", "skill": "content-writer"},
            {"id": "b", "skill": "code-reviewer", "depends_on": ["a"]},
            {"id": "c", "skill": "market-researcher", "depends_on": ["b"]},
        ],
    }
    (flows_dir / "resume-e2e.flow.yml").write_text(
        yaml.dump(flow_yaml, allow_unicode=True), encoding="utf-8"
    )

    calls = {"a": 0, "b": 0, "c": 0}

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm(prompt, **kwargs):
        if "STEP_A" in prompt:
            calls["a"] += 1
            return LLMResult(content="A" * 3000)  # 长输出，超过 state 摘要 2000 字符截断阈值
        if "STEP_B" in prompt:
            calls["b"] += 1
            if calls["b"] == 1:
                raise RuntimeError("B failed on first attempt")
            return LLMResult(content="B output after resume")
        if "STEP_C" in prompt:
            calls["c"] += 1
            return LLMResult(content="C output")
        return LLMResult(content="fallback")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm),
    ):
        # ── 第一次运行: A 成功, B 失败, C skipped ──
        result1 = run_flow(
            load_flow(flows_dir / "resume-e2e.flow.yml"),
            inputs={"topic": "AI"},
        )
        assert result1.status == "partial"
        assert result1.steps["a"].status == "done"
        assert result1.steps["b"].status == "failed"
        assert result1.steps["c"].status == "skipped"
        assert calls["a"] == 1 and calls["b"] == 1 and calls["c"] == 0
        run_id = result1.run_id
        assert run_id.startswith("run-")

        # A 的完整输出已落盘（.steps/ 目录），state 中只是截断摘要
        runs_dir = tmp_path / ".soloflow" / "runs"
        state = json.loads((runs_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        assert len(state["step_outputs"]["a"]) == 2000  # 摘要截断
        assert (runs_dir / f"{run_id}.steps" / "a.txt").read_text(encoding="utf-8") == "A" * 3000
        assert state["attempt"] == 1
        assert "resumed_at" not in state

        # ── 恢复: B 修复后 resume ──
        result2 = resume_flow(run_id)

        # BUG-FLOW-001: 返回真实的新结果
        assert result2 is not None
        assert result2.status == "done"
        # BUG-FLOW-002: 复用原 run_id
        assert result2.run_id == run_id

        # 关键行为: A 不重复调用, B/C 执行
        assert calls["a"] == 1, "A 不得重复调用"
        assert calls["b"] == 2, "B 应在恢复中重新执行"
        assert calls["c"] == 1, "C 应在恢复中执行"

        # BUG-FLOW-003: 跳过步骤带回完整旧输出与耗时（与首次保存一致）
        assert result2.steps["a"].status == "done"
        assert result2.steps["a"].output == "A" * 3000
        assert result2.steps["a"].duration == state["steps"]["a"]["duration"]
        assert result2.steps["b"].output == "B output after resume"
        assert result2.steps["c"].output == "C output"

        # lineage: attempt 递增 + resumed_at 记录
        state2 = json.loads((runs_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        assert state2["attempt"] == 2
        assert "resumed_at" in state2

        # 原始输入保留
        assert state2["inputs"] == {"topic": "AI"}


# ── GAP-FLOW-004: Flow output 映射 ──


def test_run_flow_output_mapping(monkeypatch, tmp_path):
    """GAP-FLOW-004 回归: flow.output 映射必须解析为正式输出。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    monkeypatch.chdir(tmp_path)

    flow_yaml = {
        "name": "output-map",
        "version": "1.0.0",
        "description": "Output mapping test",
        "steps": [
            {"id": "a", "skill": "content-writer"},
            {"id": "b", "skill": "code-reviewer", "depends_on": ["a"]},
        ],
        "output": {
            "article": "$steps.a.output",
            "review": "$steps.b.output",
            "literal": "fixed-value",
            "input_echo": "$input.topic",
        },
    }
    flow = FlowDefinition.model_validate(flow_yaml)

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm(prompt, **kwargs):
        if "STEP_A" in prompt:
            return LLMResult(content="ARTICLE_CONTENT")
        if "STEP_B" in prompt:
            return LLMResult(content="REVIEW_CONTENT")
        return LLMResult(content="fallback")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm),
    ):
        result = run_flow(flow, inputs={"topic": "AI"})

    assert result.status == "done"
    assert result.outputs["article"] == "ARTICLE_CONTENT"
    assert result.outputs["review"] == "REVIEW_CONTENT"
    assert result.outputs["literal"] == "fixed-value"
    assert result.outputs["input_echo"] == "AI"


def test_run_flow_output_mapping_resume(monkeypatch, tmp_path):
    """GAP-FLOW-004 + resume: 恢复完成后 output 映射基于完整上下文。"""
    import json
    from unittest.mock import patch

    import yaml

    from soloflow.core.flow_engine import load_flow, resume_flow, run_flow

    monkeypatch.chdir(tmp_path)
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow_yaml = {
        "name": "output-resume",
        "version": "1.0.0",
        "description": "Output mapping on resume",
        "steps": [
            {"id": "a", "skill": "content-writer"},
            {"id": "b", "skill": "code-reviewer", "depends_on": ["a"]},
        ],
        "output": {
            "article": "$steps.a.output",
            "review": "$steps.b.output",
        },
    }
    (flows_dir / "output-resume.flow.yml").write_text(
        yaml.dump(flow_yaml, allow_unicode=True), encoding="utf-8"
    )

    calls = {"b": 0}

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm(prompt, **kwargs):
        if "STEP_A" in prompt:
            return LLMResult(content="A_FULL_OUTPUT")
        if "STEP_B" in prompt:
            calls["b"] += 1
            if calls["b"] == 1:
                raise RuntimeError("B fails once")
            return LLMResult(content="B_FINAL_OUTPUT")
        return LLMResult(content="fallback")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm),
    ):
        result1 = run_flow(load_flow(flows_dir / "output-resume.flow.yml"))
        assert result1.status == "partial"

        result2 = resume_flow(result1.run_id)
        assert result2.status == "done"
        # 恢复后 output 映射基于完整上下文（A 的旧输出 + B 的新输出）
        assert result2.outputs["article"] == "A_FULL_OUTPUT"
        assert result2.outputs["review"] == "B_FINAL_OUTPUT"

        # outputs 已持久化到运行记录
        runs_dir = tmp_path / ".soloflow" / "runs"
        state = json.loads((runs_dir / f"{result1.run_id}.json").read_text(encoding="utf-8"))
        assert state["outputs"]["article"] == "A_FULL_OUTPUT"
        assert state["outputs"]["review"] == "B_FINAL_OUTPUT"


# ── GAP-FLOW-005: 输入类型校验 ──


def test_validate_inputs_type_mismatch():
    """GAP-FLOW-005: 类型不匹配必须报错。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "count": {"type": "integer", "required": True},
        "title": {"type": "string", "required": True},
        "enabled": {"type": "boolean", "required": True},
        "tags": {"type": "array", "required": True},
        "ratio": {"type": "number", "required": True},
    }
    issues = _validate_inputs(
        schema,
        {
            "count": "not-an-int",  # 错误
            "title": 123,  # 错误
            "enabled": "yes",  # 错误
            "tags": "a,b",  # 错误
            "ratio": "1.5",  # 错误
        },
    )
    assert any("count" in i and "integer" in i for i in issues)
    assert any("title" in i and "string" in i for i in issues)
    assert any("enabled" in i and "boolean" in i for i in issues)
    assert any("tags" in i and "array" in i for i in issues)
    assert any("ratio" in i and "number" in i for i in issues)


def test_validate_inputs_type_ok():
    """GAP-FLOW-005: 类型正确时通过。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "count": {"type": "integer"},
        "title": {"type": "string"},
        "enabled": {"type": "boolean"},
        "tags": {"type": "array"},
        "ratio": {"type": "number"},
    }
    issues = _validate_inputs(
        schema,
        {
            "count": 3,
            "title": "AI",
            "enabled": True,
            "tags": ["a", "b"],
            "ratio": 1.5,
        },
    )
    assert len(issues) == 0


def test_validate_inputs_enum():
    """GAP-FLOW-005: enum 枚举校验。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "platform": {"type": "string", "enum": ["twitter", "linkedin"]},
    }
    # 合法值通过
    assert _validate_inputs(schema, {"platform": "twitter"}) == []
    # 非法值报错
    issues = _validate_inputs(schema, {"platform": "weibo"})
    assert any("platform" in i and "允许范围" in i for i in issues)


def test_validate_inputs_min_max():
    """GAP-FLOW-005: min/max 范围校验（数值 + 字符串长度）。"""
    from soloflow.core.flow_engine import _validate_inputs

    schema = {
        "count": {"type": "integer", "min": 1, "max": 10},
        "title": {"type": "string", "min": 3, "max": 20},
    }
    assert _validate_inputs(schema, {"count": 5, "title": "hello"}) == []
    issues = _validate_inputs(schema, {"count": 0, "title": "ab"})
    assert any("count" in i and "≥ 1" in i for i in issues)
    assert any("title" in i and "≥ 3" in i for i in issues)


def test_run_flow_rejects_type_error():
    """GAP-FLOW-005: 类型错误导致 run_flow 拒绝执行（failed）。"""
    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="typed-flow",
        input_schema={"count": {"type": "integer", "required": True}},
        steps=[FlowStep(id="a", skill="content-writer")],
    )
    result = run_flow(flow, inputs={"count": "three"})
    assert result.status == "failed"


def test_run_flow_accepts_correct_type():
    """GAP-FLOW-005: 类型正确时正常执行。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="typed-ok",
        input_schema={"count": {"type": "integer", "required": True}},
        steps=[FlowStep(id="a", skill="content-writer")],
    )

    def fake_build_step_prompt(step, context):
        return "PROMPT"

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", return_value=LLMResult(content="output")),
    ):
        result = run_flow(flow, inputs={"count": 3})
    assert result.status == "done"


def test_flow_resume_nothing_to_resume(monkeypatch, tmp_path):
    """BUG-FLOW-001 回归: 全部步骤已完成时 resume 返回 None 且不重复调用。"""
    from unittest.mock import patch

    import yaml

    from soloflow.core.flow_engine import load_flow, resume_flow, run_flow

    monkeypatch.chdir(tmp_path)
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow_yaml = {
        "name": "resume-none",
        "version": "1.0.0",
        "description": "Nothing to resume",
        "steps": [
            {"id": "a", "skill": "content-writer"},
        ],
    }
    (flows_dir / "resume-none.flow.yml").write_text(
        yaml.dump(flow_yaml, allow_unicode=True), encoding="utf-8"
    )

    calls = {"a": 0}

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm(prompt, **kwargs):
        if "STEP_A" in prompt:
            calls["a"] += 1
            return LLMResult(content="A output")
        return LLMResult(content="fallback")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm),
    ):
        result = run_flow(load_flow(flows_dir / "resume-none.flow.yml"))
        assert result.status == "done"

        # 全部完成 → 无可恢复 → None
        assert resume_flow(result.run_id) is None
        assert calls["a"] == 1  # 不得再次调用


# ── BUG-FLOW-008: 步骤级 timeout / retry ──


def test_flow_step_timeout_retry_fields():
    """BUG-FLOW-008: FlowStep 支持 timeout/retries 字段。"""
    step = FlowStep(id="a", skill="s1", timeout=45.0, retries=3)
    assert step.timeout == 45.0
    assert step.retries == 3

    default_step = FlowStep(id="b", skill="s2")
    assert default_step.timeout == 0.0
    assert default_step.retries == 0


def test_flow_step_passes_timeout_and_retries(monkeypatch, tmp_path):
    """BUG-FLOW-008: 步骤级 timeout/retries 透传给 LLM 调用层。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="step-policy",
        steps=[
            FlowStep(id="a", skill="content-writer", timeout=30.0, retries=5),
        ],
    )
    captured = {}

    def fake_build_step_prompt(step, context):
        return "PROMPT"

    def fake_call_llm_full(prompt, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        captured["max_retries"] = kwargs.get("max_retries")
        return LLMResult(content="ok")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result = run_flow(flow)

    assert result.status == "done"
    assert captured["timeout"] == 30.0
    assert captured["max_retries"] == 5


def test_flow_step_default_policy():
    """BUG-FLOW-008: 未配置时使用引擎默认值。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="step-default-policy",
        steps=[FlowStep(id="a", skill="content-writer")],
    )
    captured = {}

    def fake_build_step_prompt(step, context):
        return "PROMPT"

    def fake_call_llm_full(prompt, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        captured["max_retries"] = kwargs.get("max_retries")
        return LLMResult(content="ok")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result = run_flow(flow)

    assert result.status == "done"
    assert captured["timeout"] == 120.0
    assert captured["max_retries"] == 2


# ── P1-003: 失败状态传递到任意深度（真实执行）──


def _run_flow_with_mock(flow, call_side_effect, monkeypatch=None, tmp_path=None):
    """辅助: 用 mock LLM 真实执行 Flow，返回 (result, calls)。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    calls = {"n": 0}

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm_full(prompt, **kwargs):
        calls["n"] += 1
        return call_side_effect(prompt, kwargs)

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result = run_flow(flow)
    return result, calls


def test_failure_propagates_through_chain(monkeypatch, tmp_path):
    """P1-003 回归: A failed → B skipped → C skipped，LLM 只调用 1 次。

    这是 HANDOFF 诊断的原始场景: 旧实现 C 会被错误执行（llm_calls=2）。
    """

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="prop-chain",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2", depends_on=["a"]),
            FlowStep(id="c", skill="s3", depends_on=["b"]),
        ],
    )

    def side_effect(prompt, kwargs):
        raise RuntimeError("A always fails")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "failed"
    assert result.steps["b"].status == "skipped"
    assert result.steps["c"].status == "skipped", "C 不得执行"
    assert calls["n"] == 1, f"LLM 只应调用 1 次，实际 {calls['n']}"


def test_failure_propagates_independent_branch(monkeypatch, tmp_path):
    """P1-003 回归: A→B→D 与 A→C 分支，B 失败时 D 跳过但 C 正常执行。"""

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="prop-branches",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2", depends_on=["a"]),
            FlowStep(id="c", skill="s3", depends_on=["a"]),
            FlowStep(id="d", skill="s4", depends_on=["b"]),
        ],
    )

    def side_effect(prompt, kwargs):
        if "STEP_B" in prompt:
            raise RuntimeError("B fails")
        return LLMResult(content=f"output for {prompt}")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "done"
    assert result.steps["b"].status == "failed"
    assert result.steps["c"].status == "done"
    assert result.steps["c"].output  # C 的输出存在
    assert result.steps["d"].status == "skipped", "D 依赖 B，必须跳过"


def test_any_failed_dependency_blocks(monkeypatch, tmp_path):
    """P1-003 回归: 多依赖任一失败，当前步骤 skipped。"""

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="prop-multi-dep",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
            FlowStep(id="c", skill="s3", depends_on=["a", "b"]),
        ],
    )

    def side_effect(prompt, kwargs):
        if "STEP_B" in prompt:
            raise RuntimeError("B fails")
        return LLMResult(content="ok")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "done"
    assert result.steps["b"].status == "failed"
    assert result.steps["c"].status == "skipped", "任一依赖失败 C 必须跳过"
    assert calls["n"] == 2  # a 和 b，不含 c


def test_failure_propagates_deep_chain(monkeypatch, tmp_path):
    """P1-003: 四层失败链 A→B→C→D，全部阻断。"""

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="prop-deep",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2", depends_on=["a"]),
            FlowStep(id="c", skill="s3", depends_on=["b"]),
            FlowStep(id="d", skill="s4", depends_on=["c"]),
        ],
    )

    def side_effect(prompt, kwargs):
        raise RuntimeError("boom")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "failed"
    assert result.steps["b"].status == "skipped"
    assert result.steps["c"].status == "skipped"
    assert result.steps["d"].status == "skipped"
    assert calls["n"] == 1


# ── P1-002: 同层步骤真实并发（Barrier 证明重叠）──


def test_flow_sibling_steps_run_concurrently(monkeypatch, tmp_path):
    """P1-002 回归: 两个独立同层步骤必须真正重叠执行。

    用 threading.Barrier(2) 证明：若串行，第一个调用会等 Barrier 超时失败；
    只有两个调用同时进入（不同线程），Barrier 才能释放。
    """
    import threading

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="concurrent-siblings",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
        ],
    )

    barrier = threading.Barrier(2)

    def side_effect(prompt, kwargs):
        # 两个线程都到达后同时放行；串行时第一个会等待超时
        barrier.wait(timeout=5)
        return LLMResult(content="ok")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "done"
    assert result.steps["b"].status == "done"
    assert calls["n"] == 2


def test_flow_max_parallel_one_is_serial(monkeypatch, tmp_path):
    """P1-002: max_parallel=1 时同层步骤严格串行（同时活跃数不超过 1）。"""
    import threading
    import time

    from soloflow.core.flow_engine import run_flow

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="serial-limit",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
            FlowStep(id="c", skill="s3"),
        ],
    )

    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def side_effect(prompt, kwargs):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.05)
        with lock:
            active["n"] -= 1
        return LLMResult(content="ok")

    from unittest.mock import patch

    def fake_build_step_prompt(step, context):
        return f"PROMPT_{step.id}"

    def fake_call_llm_full(prompt, **kwargs):
        return side_effect(prompt, kwargs)

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result = run_flow(flow, max_parallel=1)

    assert result.status == "done"
    assert active["max"] == 1, f"max_parallel=1 时最大并发应为 1，实际 {active['max']}"


def test_flow_max_parallel_two_allows_overlap(monkeypatch, tmp_path):
    """P1-002: max_parallel=2 时允许两个调用同时活跃（且不超过 2）。"""
    import threading
    import time
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="parallel-limit",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
            FlowStep(id="c", skill="s3"),
        ],
    )

    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def side_effect(prompt, **kwargs):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.1)
        with lock:
            active["n"] -= 1
        return LLMResult(content="ok")

    def fake_build_step_prompt(step, context):
        return f"PROMPT_{step.id}"

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", side_effect),
    ):
        result = run_flow(flow, max_parallel=2)

    assert result.status == "done"
    assert active["max"] >= 2, f"max_parallel=2 应至少观察到 2 个并发，实际 {active['max']}"
    assert active["max"] <= 2, f"max_parallel=2 不应超过 2 个并发，实际 {active['max']}"


def test_sibling_failure_does_not_cancel_others(monkeypatch, tmp_path):
    """P1-002: 同层一个步骤异常不影响其他独立步骤。"""

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="sibling-fail",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
        ],
    )

    def side_effect(prompt, kwargs):
        if "STEP_A" in prompt:
            raise RuntimeError("A explodes")
        return LLMResult(content="B output")

    result, calls = _run_flow_with_mock(flow, side_effect)

    assert result.steps["a"].status == "failed"
    assert result.steps["b"].status == "done"
    assert result.steps["b"].output == "B output"
    assert calls["n"] == 2


# ── P2-002: parse_input_value 公共输入转换器 ──


def test_parse_input_value_all_types():
    """P2-002: 全部基础类型正确转换。"""
    from soloflow.core.flow_engine import parse_input_value

    assert parse_input_value("hello", {"type": "string"}) == "hello"
    assert parse_input_value("3", {"type": "integer"}) == 3
    assert parse_input_value("3.5", {"type": "number"}) == 3.5
    assert parse_input_value("true", {"type": "boolean"}) is True
    assert parse_input_value("0", {"type": "boolean"}) is False
    assert parse_input_value("no", {"type": "boolean"}) is False
    assert parse_input_value('["a", "b"]', {"type": "array"}) == ["a", "b"]
    assert parse_input_value("x, y", {"type": "array"}) == ["x", "y"]


def test_parse_input_value_invalid_rejected():
    """P2-002: 非法值抛出清晰错误，不静默转换。"""
    import pytest

    from soloflow.core.flow_engine import parse_input_value

    with pytest.raises(ValueError, match="integer"):
        parse_input_value("abc", {"type": "integer"})
    with pytest.raises(ValueError, match="number"):
        parse_input_value("x.y", {"type": "number"})
    # 非法 boolean 不静默变成 False
    with pytest.raises(ValueError, match="boolean"):
        parse_input_value("maybe", {"type": "boolean"})


def test_parse_input_value_unknown_type_passthrough():
    """P2-002: 未知类型原样返回。"""
    from soloflow.core.flow_engine import parse_input_value

    assert parse_input_value("raw", {"type": "weird"}) == "raw"
    assert parse_input_value("raw", {}) == "raw"


# ── P2-003: input_schema 自身校验（validate 阶段发现）──


def test_validate_input_schema_bad_default_type():
    """P2-003: default 类型不匹配在 validate 阶段被发现（不再是死代码）。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="schema-default-bad",
        input_schema={"count": {"type": "integer", "default": "not-an-int"}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues = validate_flow(flow)
    assert any("default" in i and "integer" in i for i in issues)


def test_validate_input_schema_unknown_type():
    """P2-003: 不支持的 type 被拒绝。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="schema-type-bad",
        input_schema={"x": {"type": "datetime"}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues = validate_flow(flow)
    assert any("不受支持" in i for i in issues)


def test_validate_input_schema_enum_rules():
    """P2-003: enum 必须为列表；default 必须在 enum 中。"""
    from soloflow.core.flow_engine import validate_flow

    # enum 不是列表
    flow = FlowDefinition(
        name="schema-enum-not-list",
        input_schema={"p": {"type": "string", "enum": "twitter"}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues = validate_flow(flow)
    assert any("enum" in i and "列表" in i for i in issues)

    # default 不在 enum 中
    flow2 = FlowDefinition(
        name="schema-default-not-in-enum",
        input_schema={"p": {"type": "string", "enum": ["twitter", "linkedin"], "default": "weibo"}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues2 = validate_flow(flow2)
    assert any("不在 enum" in i for i in issues2)


def test_validate_input_schema_min_max():
    """P2-003: min > max 被拒绝；非数字 min/max 被拒绝。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="schema-minmax-inverted",
        input_schema={"n": {"type": "integer", "min": 10, "max": 1}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues = validate_flow(flow)
    assert any("min" in i and "max" in i for i in issues)

    flow2 = FlowDefinition(
        name="schema-minmax-nonnum",
        input_schema={"n": {"type": "integer", "min": "low"}},
        steps=[FlowStep(id="a", skill="s1")],
    )
    issues2 = validate_flow(flow2)
    assert any("min" in i and "数字" in i for i in issues2)


def test_validate_input_schema_ok():
    """P2-003: 合法 schema 通过。"""
    from soloflow.core.flow_engine import validate_flow

    flow = FlowDefinition(
        name="schema-good",
        input_schema={
            "topic": {"type": "string", "required": True},
            "count": {"type": "integer", "default": 3, "min": 1, "max": 10},
            "platform": {"type": "string", "enum": ["a", "b"], "default": "a"},
        },
        steps=[FlowStep(id="a", skill="s1")],
    )
    assert validate_flow(flow) == []


# ── P2-004: resume 后 total_tokens 保持完整 run 累计 ──


def test_resume_preserves_historical_tokens(monkeypatch, tmp_path):
    """P2-004 回归: resume 后 total_tokens 是完整 run 累计（含历史步骤）。

    A 首次执行消耗 100 token 后失败于 B；恢复后 B 消耗 250 token。
    total_tokens 必须 = 100 + 250 = 350，attempt_tokens = 250。
    """
    import json
    from unittest.mock import patch

    import yaml

    from soloflow.core.flow_engine import load_flow, resume_flow, run_flow

    monkeypatch.chdir(tmp_path)
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow_yaml = {
        "name": "token-resume",
        "version": "1.0.0",
        "description": "token resume test",
        "steps": [
            {"id": "a", "skill": "content-writer"},
            {"id": "b", "skill": "code-reviewer", "depends_on": ["a"]},
        ],
    }
    (flows_dir / "token-resume.flow.yml").write_text(
        yaml.dump(flow_yaml, allow_unicode=True), encoding="utf-8"
    )

    calls = {"b": 0}

    def fake_build_step_prompt(step, context):
        return f"PROMPT_FOR_STEP_{step.id.upper()}"

    def fake_call_llm_full(prompt, **kwargs):
        if "STEP_A" in prompt:
            return LLMResult(content="A output", total_tokens=100)
        if "STEP_B" in prompt:
            calls["b"] += 1
            if calls["b"] == 1:
                raise RuntimeError("B fails once")
            return LLMResult(content="B output", total_tokens=250)
        return LLMResult(content="x")

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result1 = run_flow(load_flow(flows_dir / "token-resume.flow.yml"))
        assert result1.status == "partial"
        assert result1.total_tokens == 100  # A 的 100

        result2 = resume_flow(result1.run_id)

    assert result2.status == "done"
    # 恢复后 total_tokens = 历史 100 + 本次 250
    assert result2.steps["a"].tokens == 100, "A 的历史 token 必须保留"
    assert result2.steps["b"].tokens == 250
    assert result2.total_tokens == 350

    # state 记录 attempt_tokens（本次新增）与累计值
    runs_dir = tmp_path / ".soloflow" / "runs"
    state = json.loads((runs_dir / f"{result1.run_id}.json").read_text(encoding="utf-8"))
    assert state["total_tokens"] == 350
    assert state["attempt_tokens"] == 250
    assert state["steps"]["a"]["tokens"] == 100


# ── P2-005: Step ID 路径安全 ──


def test_flow_step_id_rejects_path_traversal():
    """P2-005 回归: 非法 Step ID（路径穿越字符）被拒绝。"""
    import pytest

    from soloflow.models.flow import FlowStep

    # 正常 ID 通过
    assert FlowStep(id="research", skill="s1").id == "research"
    assert FlowStep(id="write-article", skill="s1").id == "write-article"

    # 路径穿越/非法字符被拒绝
    for bad_id in ["../evil", "a/b", "a\b", "a b", "A-uppercase", "1starts-with-digit", ""]:
        with pytest.raises(ValueError, match="kebab-case"):
            FlowStep(id=bad_id, skill="s1")


def test_flow_definition_rejects_bad_step_id():
    """P2-005: 含非法 Step ID 的 Flow 定义被拒绝。"""
    import pytest

    from soloflow.models.flow import FlowDefinition, FlowStep

    with pytest.raises(ValueError):
        FlowDefinition(
            name="bad-flow",
            steps=[FlowStep(id="../escape", skill="s1")],
        )


# ── P1-002: 流式 API 并发语义 ──


def test_stream_mode_serializes_parallelism(monkeypatch, tmp_path):
    """P1-002 回归: 流式模式直接 API 调用 max_parallel>1 被规范化为串行。

    两个同层步骤在流式模式下不得重叠（活动计数 max == 1）。
    """
    import threading
    import time

    from soloflow.core.flow_engine import run_flow

    monkeypatch.chdir(tmp_path)

    flow = FlowDefinition(
        name="stream-serial",
        steps=[
            FlowStep(id="a", skill="s1"),
            FlowStep(id="b", skill="s2"),
        ],
    )

    active = {"n": 0, "max": 0}
    lock = threading.Lock()

    def fake_stream(prompt, **kwargs):
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
        time.sleep(0.05)
        kwargs["on_chunk"]("chunk")
        with lock:
            active["n"] -= 1
        return LLMResult(content="chunk")

    from unittest.mock import patch

    def fake_build_step_prompt(step, context):
        return f"PROMPT_{step.id}"

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_stream),
    ):
        result = run_flow(flow, stream=True, max_parallel=2)

    assert result.status == "done"
    assert active["max"] == 1, f"流式模式必须串行，实际最大并发 {active['max']}"


def test_stream_mode_cli_passthrough():
    """P1-002: CLI 的 --stream 不再重复串行化（引擎统一），run_flow 仍可被 CLI 正常调用。"""
    from soloflow.cli.flow import run as flow_run_cmd  # noqa: F401  (命令可导入)


# ── P1-002: max_parallel 非法值校验 ──


def test_run_flow_is_small_public_entry_point():
    """run_flow 仅接受新运行参数，恢复状态由 resume_flow 独立处理。"""
    import inspect

    from soloflow.core.flow_engine import run_flow

    parameters = list(inspect.signature(run_flow).parameters)
    source_lines = inspect.getsourcelines(run_flow)[0]

    assert parameters == ["flow", "inputs", "max_parallel", "dry_run", "stream"]
    assert len(source_lines) < 150


def test_run_flow_rejects_zero_max_parallel():
    """P1-002 回归: max_parallel=0 立即抛 ValueError（不创建零容量 semaphore 死锁）。"""
    import pytest

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(name="mp-zero", steps=[FlowStep(id="a", skill="s1")])
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel=0)


def test_run_flow_rejects_negative_max_parallel():
    """P1-002 回归: 负数 max_parallel 立即抛 ValueError。"""
    import pytest

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(name="mp-neg", steps=[FlowStep(id="a", skill="s1")])
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel=-1)


def test_run_flow_rejects_non_integer_max_parallel():
    """P1-002 回归: 非整数 max_parallel（如 1.5、'2'）立即抛 ValueError。"""
    import pytest

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(name="mp-float", steps=[FlowStep(id="a", skill="s1")])
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel=1.5)
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel="2")


def test_run_flow_valid_max_parallel_unchanged():
    """P1-002: 正常值 1/2/5 行为不变。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(
        name="mp-valid",
        steps=[FlowStep(id="a", skill="s1"), FlowStep(id="b", skill="s2")],
    )

    def fake_build_step_prompt(step, context):
        return f"PROMPT_{step.id}"

    for mp in (1, 2, 5):
        with (
            patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
            patch("soloflow.core.flow_engine.execute_prompt", return_value=LLMResult(content="ok")),
        ):
            result = run_flow(flow, max_parallel=mp)
        assert result.status == "done"


def test_cli_rejects_zero_parallel(monkeypatch, tmp_path):
    """P1-002 回归: sf flow run --parallel 0 非零退出，不启动任何步骤。"""
    import yaml
    from typer.testing import CliRunner

    from soloflow.cli.main import app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "flows").mkdir()
    (tmp_path / "flows" / "mp-cli.flow.yml").write_text(
        yaml.dump(
            {
                "name": "mp-cli",
                "version": "1.0.0",
                "description": "max_parallel CLI test",
                "steps": [{"id": "a", "skill": "content-writer"}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["flow", "run", "mp-cli", "--parallel", "0"])

    assert result.exit_code != 0
    assert "positive integer" in result.output or "max_parallel" in result.output


# ── P1(收尾): 拒绝布尔值 max_parallel ──


def test_run_flow_rejects_boolean_max_parallel():
    """P1(收尾) 回归: max_parallel=True/False 立即抛 ValueError。

    isinstance(True, int) 为 True，若不加 bool 检查，
    max_parallel=True 会被当作 1 接受。必须显式拒绝。
    """
    import pytest

    from soloflow.core.flow_engine import run_flow

    flow = FlowDefinition(name="mp-bool", steps=[FlowStep(id="a", skill="s1")])
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel=True)
    with pytest.raises(ValueError, match="positive integer"):
        run_flow(flow, max_parallel=False)
