"""Flow 编排引擎。

核心算法：
1. 解析 Flow YAML → 构建 DAG
2. 拓扑排序 → 确定执行顺序
3. 并行调度 → 依赖满足的步骤并发执行
4. 变量解析 → $input.xxx / $steps.xxx.output
"""

import datetime
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel

from soloflow.core.agent_runner import (
    load_agent,
    load_skills_for_agent,
    render_agent_prompt,
    resolve_llm_config,
)
from soloflow.core.runner import execute_prompt, render_skill_prompt
from soloflow.core.skill_loader import find_skill, load_skill
from soloflow.models.flow import (
    FlowDefinition,
    FlowResult,
    FlowStep,
    StepResult,
)

console = Console()

# 最大并行步骤数
MAX_PARALLEL = 5


def parse_input_value(raw: str, spec: dict) -> Any:
    """按 schema type 解析 CLI/TUI 输入值（P2-002/006 统一转换器）。

    行为:
    - string: 原字符串。
    - integer: int(raw)，失败抛 ValueError。
    - number: float(raw)，失败抛 ValueError。
    - boolean: 只接受 true/false/1/0/yes/no（大小写不敏感），
      非法值抛 ValueError（不静默变成 False）。
    - array: 优先 JSON 数组（'["a","b"]'），回退逗号分隔。
    - 未知类型: 原样返回。

    Args:
        raw: 用户输入的原始字符串。
        spec: input_schema 中该字段的规格字典。

    Returns:
        转换后的值。

    Raises:
        ValueError: 类型转换失败（含非法 boolean）。
    """
    field_type = spec.get("type", "string") if isinstance(spec, dict) else "string"

    if field_type == "string":
        return raw
    if field_type == "integer":
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"参数应为 integer，无法解析 '{raw}'")
    if field_type == "number":
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"参数应为 number，无法解析 '{raw}'")
    if field_type == "boolean":
        low = raw.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
        raise ValueError(f"参数应为 boolean (true/false/1/0/yes/no)，无法解析 '{raw}'")
    if field_type == "array":
        try:
            val = json.loads(raw)
            if isinstance(val, list):
                return val
        except (json.JSONDecodeError, TypeError):
            pass
        return [item.strip() for item in raw.split(",") if item.strip()]

    return raw  # 未知类型原样返回


# 运行记录存储目录
RUNS_DIR = Path(".soloflow/runs")


def datetime_now_iso() -> str:
    """当前 UTC 时间的 ISO 字符串（辅助保存恢复标记）。"""
    return datetime.datetime.now(datetime.UTC).isoformat()


# 兜底 LLM 配置（Skill 加载失败时使用）
_DEFAULT_LLM_MODEL = "deepseek-v4-flash"
_DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
_DEFAULT_LLM_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEFAULT_LLM_TEMPERATURE = 0.7
_DEFAULT_LLM_MAX_TOKENS = 4096


def _default_llm_config(skill_config) -> tuple[str, str, str, float, int]:
    """从 Skill 配置或默认值解析 LLM 配置（skill_config 可为 None）。"""
    if skill_config is not None:
        return (
            skill_config.base_url,
            skill_config.api_key_env,
            skill_config.model,
            skill_config.temperature,
            skill_config.max_tokens,
        )
    return (
        _DEFAULT_LLM_BASE_URL,
        _DEFAULT_LLM_API_KEY_ENV,
        _DEFAULT_LLM_MODEL,
        _DEFAULT_LLM_TEMPERATURE,
        _DEFAULT_LLM_MAX_TOKENS,
    )


def _save_run_state(
    flow_name: str,
    run_id: str,
    steps: dict[str, dict],
    status: str,
    total_duration: float = 0.0,
    total_tokens: int = 0,
    step_outputs: dict[str, str] = None,
    inputs: dict[str, Any] = None,
    attempt: int = 1,
    outputs: dict[str, Any] = None,
    attempt_tokens: int = 0,
    step_data: dict[str, Any] = None,
    approvals: dict[str, Any] = None,
) -> None:
    """将 Flow 运行状态持久化到 .soloflow/runs/<run-id>.json。

    Rich 视图读取这些文件以显示实时进度。
    恢复执行时需 step_outputs 和 inputs 重建上下文。

    BUG-FLOW-003 修复：state JSON 中的 step_outputs 是截断摘要（TUI 展示用），
    完整输出写入 .soloflow/runs/<run_id>.steps/<step_id>.txt，
    恢复时优先读取完整产物，避免上游长输出丢失。
    """
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = RUNS_DIR / f"{run_id}.json"
    data = {
        "flow_name": flow_name,
        "run_id": run_id,
        "status": status,
        "steps": steps,
        "total_duration": total_duration,
        # P2-004: total_tokens 是完整 run 的累计（含历史），
        # attempt_tokens 是本次执行新增的 token 数
        "total_tokens": total_tokens,
        "attempt_tokens": attempt_tokens,
        "attempt": attempt,
    }
    if attempt > 1:
        # 恢复执行标记（BUG-FLOW-002 lineage: 复用原 run_id，记录恢复时间）
        data["resumed_at"] = datetime_now_iso()
    if step_outputs:
        # 完整输出落盘（供恢复引擎读取）
        steps_dir = RUNS_DIR / f"{run_id}.steps"
        steps_dir.mkdir(parents=True, exist_ok=True)
        for step_id, output in step_outputs.items():
            (steps_dir / f"{step_id}.txt").write_text(output, encoding="utf-8")
        # 摘要截断 2000 字符（实时视图展示用）
        data["step_outputs"] = {k: v[:2000] for k, v in step_outputs.items()}
    if step_data:
        data["step_data"] = step_data
    if inputs:
        data["inputs"] = inputs
    if outputs:
        data["outputs"] = {
            k: v if isinstance(v, (dict, list, bool, int, float)) else str(v)[:2000]
            for k, v in outputs.items()
        }
    if approvals:
        data["approvals"] = approvals
    run_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_step_outputs(run_id: str) -> dict[str, str]:
    """加载运行记录的完整步骤输出（优先完整文件，回退 JSON 摘要）。

    BUG-FLOW-003 修复：恢复时从这里取完整上游输出，而不是截断摘要。
    """
    outputs: dict[str, str] = {}
    steps_dir = RUNS_DIR / f"{run_id}.steps"
    if steps_dir.is_dir():
        for out_file in sorted(steps_dir.glob("*.txt")):
            try:
                outputs[out_file.stem] = out_file.read_text(encoding="utf-8")
            except OSError:
                continue
    if outputs:
        return outputs

    # 回退：JSON 摘要（旧格式运行记录）
    run_file = RUNS_DIR / f"{run_id}.json"
    if run_file.exists():
        try:
            saved = json.loads(run_file.read_text(encoding="utf-8"))
            return {k: v for k, v in saved.get("step_outputs", {}).items()}
        except (json.JSONDecodeError, OSError):
            pass
    return outputs


def _load_step_data(run_id: str) -> dict[str, Any]:
    """Load structured JSON data produced by completed Flow steps."""
    run_file = RUNS_DIR / f"{run_id}.json"
    if not run_file.exists():
        return {}
    try:
        saved = json.loads(run_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    data = saved.get("step_data", {})
    return data if isinstance(data, dict) else {}


def _stringify_ref_value(value: Any) -> str:
    """Render a reference value for prompt text while preserving JSON structure."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _resolve_value(ref: str, context: dict) -> Any:
    """Resolve a reference to its native value for conditions and outputs."""
    if not isinstance(ref, str):
        return ref

    if ref.startswith("$input.") and re.fullmatch(r"\$input\.[\w-]+", ref):
        key = ref[7:]
        return context.get("input", {}).get(key, ref)

    step_match = re.fullmatch(
        r"\$steps\.([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.(output|data)"
        r"(?:\.([\w-]+(?:\.[\w-]+)*))?",
        ref,
    )
    if step_match:
        step_id, source, path = step_match.groups()
        if source == "output":
            value: Any = context.get("steps", {}).get(step_id, ref)
        else:
            value = context.get("step_data", {}).get(step_id, ref)
        if path and value != ref:
            for part in path.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return None
        return value

    if "$" in ref:
        result = ref
        for match in re.finditer(r"\$input\.([\w-]+)", result):
            value = context.get("input", {}).get(match.group(1), match.group(0))
            result = result.replace(match.group(0), _stringify_ref_value(value))
        for match in re.finditer(
            r"\$steps\.([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.(output|data)"
            r"(?:\.([\w-]+(?:\.[\w-]+)*))?",
            result,
        ):
            value = _resolve_value(match.group(0), context)
            result = result.replace(match.group(0), _stringify_ref_value(value))
        return result

    return ref


def _resolve_ref(ref: str, context: dict) -> str:
    """解析变量引用。

    支持的引用格式：
    - $input.xxx → context["input"]["xxx"]
    - $steps.<step_id>.output → context["steps"][step_id]
    - 普通字符串 → 直接返回

    Args:
        ref: 可能包含引用的字符串。
        context: 包含 input 和 steps 的上下文字典。

    Returns:
        解析后的字符串。
    """
    return _stringify_ref_value(_resolve_value(ref, context))


def _build_dag(steps: list[FlowStep]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """构建 DAG。

    Returns:
        (adjacency, reverse_adjacency)
        adjacency: step_id → [下游步骤]
        reverse_adjacency: step_id → [上游步骤（依赖）]
    """
    adjacency: dict[str, list[str]] = {s.id: [] for s in steps}
    reverse_adjacency: dict[str, list[str]] = {s.id: [] for s in steps}

    for step in steps:
        for dep in step.depends_on:
            if dep in adjacency:
                adjacency[dep].append(step.id)
                reverse_adjacency[step.id].append(dep)

    return adjacency, reverse_adjacency


def _topological_sort(steps: list[FlowStep]) -> list[list[str]]:
    """拓扑排序，返回分层执行计划。

    同一层的步骤可以并行执行（依赖全部满足）。

    Returns:
        [[step_id, ...], [step_id, ...]] —— 每层一组，按序执行。
    """
    adjacency, reverse = _build_dag(steps)

    # 计算每个节点的入度
    in_degree = {s.id: len(s.depends_on) for s in steps}

    # 找到所有入度为 0 的起始节点
    stack = [s_id for s_id, deg in in_degree.items() if deg == 0]
    levels: list[list[str]] = []

    while stack:
        # 当前层 = 所有入度为 0 的节点（可以并行执行）
        levels.append(sorted(stack))
        next_stack = []

        for node in stack:
            for downstream in adjacency.get(node, []):
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    next_stack.append(downstream)

        stack = next_stack

    # 检查是否有未处理的节点（循环依赖）
    remaining = sum(in_degree.values())
    if remaining > 0:
        unresolved = [s_id for s_id, deg in in_degree.items() if deg > 0]
        raise ValueError(f"Flow contains circular dependency: {unresolved}")

    return levels


def _build_step_prompt(step: FlowStep, context: dict) -> str:
    """Resolve Flow inputs and delegate prompt rendering to the shared Runner."""
    resolved_inputs = {}
    for key, value in step.input.mapping.items():
        resolved_inputs[key] = _resolve_ref(value, context)

    if resolved_inputs:
        task = "\n".join(f"**{key}**: {value}" for key, value in resolved_inputs.items())
    else:
        task = "Execute the task as defined in your instructions."

    if step.agent:
        try:
            agent = load_agent(step.agent)
            loaded_skills = load_skills_for_agent(agent)
            if loaded_skills:
                prompt = render_agent_prompt(agent, loaded_skills, task)
                return _append_output_contract(prompt, step)
        except (ImportError, FileNotFoundError) as e:
            console.print(
                f"[yellow]Warning: Agent '{step.agent}' not found, "
                f"falling back to skill '{step.skill}' ({e})[/yellow]"
            )

    prompt = render_skill_prompt(load_skill(find_skill(step.skill)), task)
    return _append_output_contract(prompt, step)


def _append_output_contract(prompt: str, step: FlowStep) -> str:
    """Tell an LLM step how to produce machine-readable JSON when requested."""
    if step.output_format != "json":
        return prompt
    schema = step.output_schema or {"type": "object"}
    return (
        f"{prompt}\n\n# Output Contract\n"
        "Return only valid JSON. Do not wrap it in Markdown fences or add commentary.\n"
        f"The JSON must follow this schema: {json.dumps(schema, ensure_ascii=False)}"
    )


def _parse_condition_literal(raw: str) -> Any:
    """Parse the small set of literals supported by Flow conditions."""
    value = raw.strip()
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "none"):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value


def _evaluate_condition(expression: str | None, context: dict) -> bool:
    """Evaluate a deliberately small, safe condition language.

    Supported forms are ``<reference> == <literal>``,
    ``<reference> != <literal>``, and a bare reference for truthiness.
    Arbitrary Python expressions are intentionally not evaluated.
    """
    if not expression:
        return True

    reference = (
        r"\$(?:input\.[\w-]+|steps\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
        r"\.(?:output|data)(?:\.[\w-]+)*)"
    )
    match = re.fullmatch(
        rf"\s*(?P<ref>{reference})\s*(?:(?P<op>==|!=)\s*(?P<literal>.+))?\s*",
        expression,
    )
    if not match:
        raise ValueError(
            "条件格式不支持；请使用 `$steps.review.data.approved == true` 或一个可解析引用"
        )

    actual = _resolve_value(match.group("ref"), context)
    if not match.group("op"):
        return bool(actual) and actual != match.group("ref")

    expected = _parse_condition_literal(match.group("literal"))
    if match.group("op") == "==":
        return actual == expected
    return actual != expected


def _validate_output_schema(value: Any, schema: dict[str, Any], path: str = "$") -> str | None:
    """Validate the useful subset of JSON Schema needed by Flow outputs."""
    if not schema:
        return None
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected in type_ok and not type_ok[expected]:
        return f"{path} 应为 {expected}，实际是 {type(value).__name__}"

    if isinstance(value, dict):
        for required in schema.get("required", []):
            if required not in value:
                return f"{path}.{required} 缺少必填字段"
        for key, child_schema in schema.get("properties", {}).items():
            if key in value and isinstance(child_schema, dict):
                issue = _validate_output_schema(value[key], child_schema, f"{path}.{key}")
                if issue:
                    return issue
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            issue = _validate_output_schema(item, schema["items"], f"{path}[{index}]")
            if issue:
                return issue
    return None


def _parse_structured_output(content: str, schema: dict[str, Any]) -> Any:
    """Parse and validate a JSON step result, accepting accidental code fences."""
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate[3:-3]
        candidate = candidate.rsplit("```", 1)[0].strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(f"步骤要求 JSON 输出，但模型返回的内容无法解析: {error.msg}") from error
    issue = _validate_output_schema(value, schema)
    if issue:
        raise ValueError(f"步骤 JSON 输出不符合 output_schema: {issue}")
    return value


def load_flow(path: str | Path) -> FlowDefinition:
    """从 YAML 文件加载 Flow 定义。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Flow file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FlowDefinition(**data)


def validate_flow(flow: FlowDefinition) -> list[str]:
    """校验 Flow 定义。"""
    issues = []

    # 检查步骤 ID 唯一性
    ids = [s.id for s in flow.steps]
    if len(ids) != len(set(ids)):
        issues.append("Duplicate step IDs found")

    # 检查依赖引用有效性
    valid_ids = set(ids)
    for step in flow.steps:
        for dep in step.depends_on:
            if dep not in valid_ids:
                issues.append(f"Step '{step.id}' depends on unknown step '{dep}'")

    # 检查循环依赖
    try:
        _topological_sort(flow.steps)
    except ValueError as e:
        issues.append(str(e))

    # P2-003: input_schema 自身定义校验（不依赖用户输入）
    if flow.input_schema:
        issues.extend(_validate_input_schema(flow.input_schema))

    return issues


# input_schema 支持的 type 值 → Python 类型检查器
_VALID_INPUT_TYPES = {"string", "integer", "number", "boolean", "array"}


def _check_input_type(key: str, value: Any, expected: str) -> str | None:
    """检查单个输入值的类型。返回错误消息或 None。"""
    if expected == "string":
        return (
            None
            if isinstance(value, str)
            else f"参数 '{key}' 应为 string，实际是 {type(value).__name__}"
        )
    if expected == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
        return None if ok else f"参数 '{key}' 应为 integer，实际是 {type(value).__name__}"
    if expected == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return None if ok else f"参数 '{key}' 应为 number，实际是 {type(value).__name__}"
    if expected == "boolean":
        return (
            None
            if isinstance(value, bool)
            else f"参数 '{key}' 应为 boolean，实际是 {type(value).__name__}"
        )
    if expected == "array":
        return (
            None
            if isinstance(value, list)
            else f"参数 '{key}' 应为 array，实际是 {type(value).__name__}"
        )
    return None  # 未知类型不校验


def _validate_inputs(input_schema: dict[str, Any], inputs: dict[str, Any]) -> list[str]:
    """根据 Flow 的 input_schema 校验用户输入。

    GAP-FLOW-005 增强: 除 required/未知 key 外，校验:
    - type（string/integer/number/boolean/array）
    - enum 枚举
    - min/max（数值范围或字符串长度）
    - default 值与声明的类型一致

    Args:
        input_schema: Flow 定义的 input_schema
            （key → {type, required, description, default, enum, min, max}）。
        inputs: 用户实际传入的输入。

    Returns:
        问题列表，空列表表示通过。
    """
    if not input_schema:
        return []

    issues = []
    provided_keys = set(inputs.keys())
    schema_keys = set(input_schema.keys())

    # 1. 检查必填字段
    for key, spec in input_schema.items():
        if isinstance(spec, dict) and spec.get("required") and key not in provided_keys:
            issues.append(f"缺少必填参数: '{key}' — {spec.get('description', '')}")
        elif key not in provided_keys:
            issues.append(f"[info]可选参数 '{key}' 未提供 — {spec.get('description', '')}")

    # 2. 检查未知参数
    for key in provided_keys:
        if key not in schema_keys:
            issues.append(f"未知输入参数: '{key}'（不在 input_schema 中定义）")

    # 3. 类型 / 枚举 / 范围校验（GAP-FLOW-005）
    for key, spec in input_schema.items():
        if not isinstance(spec, dict):
            continue
        value = inputs.get(key)
        if key not in provided_keys:
            continue

        expected_type = spec.get("type")
        if expected_type and expected_type in _VALID_INPUT_TYPES:
            type_err = _check_input_type(key, value, expected_type)
            if type_err:
                issues.append(type_err)

        # enum 枚举
        enum_values = spec.get("enum")
        if enum_values and value not in enum_values:
            issues.append(f"参数 '{key}' 取值 {value!r} 不在允许范围内: {enum_values}")

        # min/max: 数值或字符串长度
        min_val = spec.get("min")
        max_val = spec.get("max")
        if min_val is not None or max_val is not None:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if min_val is not None and value < min_val:
                    issues.append(f"参数 '{key}' 应 ≥ {min_val}，实际是 {value}")
                if max_val is not None and value > max_val:
                    issues.append(f"参数 '{key}' 应 ≤ {max_val}，实际是 {value}")
            elif isinstance(value, str):
                if min_val is not None and len(value) < min_val:
                    issues.append(f"参数 '{key}' 长度应 ≥ {min_val}，实际是 {len(value)}")
                if max_val is not None and len(value) > max_val:
                    issues.append(f"参数 '{key}' 长度应 ≤ {max_val}，实际是 {len(value)}")

    return issues


def _validate_input_schema(input_schema: dict[str, Any]) -> list[str]:
    """校验 input_schema 自身定义是否合法（P2-003 修复）。

    运行前在 validate 阶段检查（不依赖用户输入）：
    - type 是否受支持。
    - default 是否匹配 type。
    - enum 是否为列表。
    - default 是否在 enum 中。
    - min/max 类型正确且 min <= max。

    Returns:
        问题列表，空列表表示通过。
    """
    issues = []

    for key, spec in input_schema.items():
        if not isinstance(spec, dict):
            issues.append(f"schema 参数 '{key}' 必须是对象（{type(spec).__name__}）")
            continue

        field_type = spec.get("type", "string")
        if field_type not in _VALID_INPUT_TYPES:
            issues.append(
                f"schema 参数 '{key}' 的类型 '{field_type}' 不受支持"
                f"（支持: {', '.join(sorted(_VALID_INPUT_TYPES))}）"
            )

        # default 与类型匹配
        if "default" in spec:
            default_val = spec["default"]
            if field_type in _VALID_INPUT_TYPES:
                default_err = _check_input_type(key, default_val, field_type)
                if default_err:
                    issues.append(f"schema 参数 '{key}' 的 default 不匹配类型: {default_err}")

        # enum 必须是列表
        if "enum" in spec and not isinstance(spec["enum"], list):
            issues.append(f"schema 参数 '{key}' 的 enum 必须是列表")

        # default 必须在 enum 中
        if "default" in spec and isinstance(spec.get("enum"), list) and spec["enum"]:
            if spec["default"] not in spec["enum"]:
                issues.append(
                    f"schema 参数 '{key}' 的 default {spec['default']!r} "
                    f"不在 enum 中: {spec['enum']}"
                )

        # min/max 类型正确且 min <= max
        min_val = spec.get("min")
        max_val = spec.get("max")
        for bound_name, bound in (("min", min_val), ("max", max_val)):
            if bound is not None and not isinstance(bound, (int, float)):
                issues.append(f"schema 参数 '{key}' 的 {bound_name} 必须是数字")
        if (
            isinstance(min_val, (int, float))
            and isinstance(max_val, (int, float))
            and min_val > max_val
        ):
            issues.append(f"schema 参数 '{key}' 的 min ({min_val}) 大于 max ({max_val})")

    return issues


def _execute_flow(
    flow: FlowDefinition,
    inputs: dict[str, Any],
    max_parallel: int,
    dry_run: bool,
    stream: bool,
    *,
    context: dict[str, Any],
    resume_skip: set[str],
    run_id: str,
    attempt: int,
) -> FlowResult:
    """Execute a prepared new or resumed Flow run."""

    # P1-002/P1(收尾): 校验 max_parallel 必须是正整数。
    # - max_parallel=0 会创建零容量 semaphore 导致步骤永久等待（死锁）。
    # - 负数/浮点数/字符串会抛意外异常。
    # - bool 是 int 的子类（isinstance(True, int) == True），必须显式拒绝，
    #   否则 max_parallel=True 会被当作 1 接受，违背正整数契约。
    # 必须在创建 semaphore 之前立即明确报错。
    if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
        raise ValueError(f"max_parallel must be a positive integer, got {max_parallel!r}")

    # P1-002: 流式 API 并发语义 —— 流式分支同步迭代同步 generator，
    # 会阻塞 event loop 无法真实并发。明确契约：流式模式只允许串行执行。
    # 先确保输入合法，再将大于 1 的值规范化为 1（CLI 行为由引擎统一）。
    if stream and max_parallel > 1:
        console.print(
            f"[yellow]流式模式仅支持串行执行，max_parallel={max_parallel} 已规范化为 1[/yellow]"
        )
        max_parallel = 1

    result = FlowResult(flow_name=flow.name, run_id=run_id, status="running")

    user_inputs = inputs

    # ── 输入校验 ──
    if flow.input_schema:
        input_issues = _validate_inputs(flow.input_schema, user_inputs)
        # critical: 缺少必填 / 类型错误 / 枚举越界 / 范围越界 → 拒绝执行
        # info: 可选未提供 / 未知 key / schema 自身问题 → 仅提示
        critical = [
            i for i in input_issues if not i.startswith("[info]") and not i.startswith("未知")
        ]
        info = [i for i in input_issues if i.startswith("[info]") or i.startswith("未知")]
        if critical:
            for msg in critical:
                console.print(f"[red]Input Error: {msg}[/red]")
            result.status = "failed"
            return result
        for msg in info:
            console.print(f"[dim]{msg}[/dim]")

    # 顶层代码中运行时的 loop 引用
    import asyncio as _asyncio_mod

    # 拓扑排序
    try:
        levels = _topological_sort(flow.steps)
    except ValueError as e:
        result.status = "failed"
        console.print(f"[red]Error: {e}[/red]")
        return result

    # 显示执行计划
    step_map = {s.id: s for s in flow.steps}

    console.print(
        Panel.fit(
            f"[bold cyan]{flow.name}[/bold cyan] v{flow.version}\n"
            f"{flow.description}\n\n"
            f"Steps: {len(flow.steps)} | Levels: {len(levels)}",
            border_style="cyan",
        )
    )

    # 显示分层计划
    for level_idx, level in enumerate(levels, 1):
        step_descs = []
        for sid in level:
            s = step_map[sid]
            skill_info = "approval / 人工确认" if s.type == "approval" else s.skill
            if s.agent:
                skill_info = f"{skill_info} (agent: {s.agent})"
            deps = f" [{', '.join(s.depends_on)}]" if s.depends_on else ""
            step_descs.append(f"  {sid}: {skill_info}{deps}")
        console.print(f"[bold]Level {level_idx}:[/bold]")
        for d in step_descs:
            console.print(d)

    if dry_run:
        console.print("\n[yellow]Dry run — showing plan only.[/yellow]")
        result.status = "dry_run"
        return result

    # 逐层执行
    t0 = time.time()
    semaphore = _asyncio_mod.Semaphore(max_parallel)
    # P2-004: 本次 attempt 新增 token 累计器
    attempt_tokens_acc = {"n": 0}

    for step in flow.steps:
        result.steps[step.id] = StepResult(step_id=step.id, status="pending")

    def persist_progress() -> None:
        """Persist current state for recovery and the read-only live view."""
        step_outputs = {
            sid: item.output
            for sid, item in result.steps.items()
            if item.status == "done" and item.output
        }
        steps_state = {
            sid: {
                "status": item.status,
                "error": item.error,
                "duration": item.duration,
                "tokens": item.tokens,
                "skill": step_map[sid].skill,
                "type": step_map[sid].type,
                "depends_on": step_map[sid].depends_on,
            }
            for sid, item in result.steps.items()
        }
        step_data = {
            sid: item.data
            for sid, item in result.steps.items()
            if item.status == "done" and item.data is not None
        }
        _save_run_state(
            flow.name,
            run_id,
            steps_state,
            result.status,
            time.time() - t0,
            result.total_tokens,
            step_outputs=step_outputs,
            inputs=user_inputs,
            attempt=attempt,
            outputs=result.outputs,
            attempt_tokens=attempt_tokens_acc["n"],
            step_data=step_data,
            approvals=context.get("_approvals", {}),
        )

    persist_progress()

    async def execute_step(step: FlowStep) -> StepResult:
        """异步执行单个步骤。"""
        async with semaphore:
            sr = StepResult(step_id=step.id, status="running")
            result.steps[step.id] = sr
            persist_progress()
            t1 = time.time()

            # 断点恢复：跳过已完成的步骤
            if step.id in resume_skip:
                # BUG-FLOW-003 修复：跳过步骤必须带回旧输出和耗时，
                # 否则新 FlowResult 缺失已完成步骤的产物。
                # P2-004: 同时恢复历史 token，total_tokens 保持完整 run 累计。
                sr.status = "done"
                sr.duration = context.get("_resume_durations", {}).get(step.id, 0.0)
                sr.output = context.get("steps", {}).get(step.id)
                sr.data = context.get("step_data", {}).get(step.id)
                sr.tokens = context.get("_resume_tokens", {}).get(step.id, 0)
                console.print(
                    f"\n[bold]>>> {step.id}[/bold] [{step.skill}] "
                    f"[dim]SKIPPED (already completed)[/dim]"
                )
                return sr

            # P1-003 修复: 所有依赖必须 done 才能执行。
            # 之前用 failed_step_ids 推断（skipped 不加入集合），
            # 导致 A failed → B skipped → C 仍执行。
            # 现在直接检查已完成依赖结果，状态来源唯一，
            # failed/skipped 可传递到任意深度。
            blocked_deps = []
            for dep in step.depends_on:
                dep_result = result.steps.get(dep)
                if dep_result is None or dep_result.status != "done":
                    blocked_deps.append(dep)
            if blocked_deps:
                sr.status = "skipped"
                sr.error = f"Skipped: dependency not done — {', '.join(blocked_deps)}"
                console.print(
                    f"\n[bold]>>> {step.id}[/bold] [{step.skill}] "
                    f"[yellow]SKIPPED (dep not done: {', '.join(blocked_deps)})[/yellow]"
                )
                sr.duration = 0
                return sr

            # 条件节点：只执行安全的小表达式，不执行任意 Python。
            if step.when:
                try:
                    condition_met = _evaluate_condition(step.when, context)
                except ValueError as error:
                    sr.status = "failed"
                    sr.error = str(error)
                    sr.duration = time.time() - t1
                    console.print(f"  [red]Condition error in {step.id}: {error}[/red]")
                    return sr
                if not condition_met:
                    sr.status = "skipped"
                    sr.error = f"Skipped: condition not met — {step.when}"
                    sr.duration = time.time() - t1
                    console.print(
                        f"\n[bold]>>> {step.id}[/bold] [yellow]SKIPPED (condition not met)[/yellow]"
                    )
                    return sr

            if step.type == "approval":
                approval = context.get("_approvals", {}).get(step.id)
                if not approval:
                    sr.status = "waiting_approval"
                    sr.error = "Waiting for human approval"
                    result.status = "waiting_approval"
                    sr.duration = time.time() - t1
                    console.print(
                        f"\n[bold]>>> {step.id}[/bold] [yellow]WAITING FOR HUMAN APPROVAL[/yellow]"
                    )
                    console.print(
                        f"  [dim]Use: sf flow approve {run_id} --step {step.id} "
                        "or sf flow reject {run_id} --step {step.id}[/dim]"
                    )
                    return sr

                approved = approval.get("decision") == "approved"
                sr.data = {
                    "approved": approved,
                    "note": approval.get("note", ""),
                }
                sr.output = json.dumps(sr.data, ensure_ascii=False)
                sr.status = "done" if approved else "rejected"
                sr.error = None if approved else "Rejected by human reviewer"
                sr.duration = time.time() - t1
                console.print(
                    f"  [{'green' if approved else 'red'}]Human decision: "
                    f"{'approved' if approved else 'rejected'}[/{'green' if approved else 'red'}]"
                )
                return sr

            console.print(f"\n[bold]>>> {step.id}[/bold] [{step.skill}]")

            if step.depends_on:
                console.print(f"  [dim]deps: {', '.join(step.depends_on)}[/dim]")

            # 构建 prompt
            prompt = _build_step_prompt(step, context)

            # 尝试加载 Skill 配置
            try:
                skill_path = find_skill(step.skill)
                skill = load_skill(skill_path)
                skill_config = skill.config
            except Exception:
                skill_config = None

            if step.agent:
                # BUG-AGENT-002 修复: Agent 步骤使用统一的配置解析
                # （Agent config 覆盖 Skill config，None=继承）
                try:
                    from soloflow.models.skill import SkillConfig

                    agent_def = load_agent(step.agent)
                    fallback = skill_config or SkillConfig()
                    base_url, api_key_env, model, temperature, max_tokens_val = resolve_llm_config(
                        agent_def.config, fallback
                    )
                except Exception:
                    base_url, api_key_env, model, temperature, max_tokens_val = _default_llm_config(
                        skill_config
                    )
            else:
                base_url, api_key_env, model, temperature, max_tokens_val = _default_llm_config(
                    skill_config
                )

            # BUG-FLOW-008: 步骤级 timeout/retry（0 = 使用引擎默认）
            step_timeout = step.timeout or 120.0
            step_retries = step.retries if step.retries > 0 else 2

            try:
                if stream:
                    console.print("  [dim]streaming...[/dim]")
                    llm_result = execute_prompt(
                        prompt,
                        base_url=base_url,
                        api_key_env=api_key_env,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens_val,
                        stream=True,
                        on_chunk=lambda chunk: console.print(chunk, end="", highlight=False),
                        timeout=step_timeout,
                    )
                    console.print()
                else:
                    # P1-002 修复: asyncio.to_thread 让 LLM 调用在真实线程中执行，
                    # 同层步骤真正并发。之前直接同步调用阻塞 event loop，
                    # asyncio.gather 实际是串行执行。
                    llm_result = await _asyncio_mod.to_thread(
                        execute_prompt,
                        prompt,
                        base_url=base_url,
                        api_key_env=api_key_env,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens_val,
                        timeout=step_timeout,
                        max_retries=step_retries,
                    )
                sr.output = llm_result.content
                sr.tokens = llm_result.total_tokens
                if step.output_format == "json":
                    sr.data = _parse_structured_output(llm_result.content, step.output_schema)
                sr.status = "done"
            except Exception as e:
                sr.status = "failed"
                sr.error = str(e)
                console.print(f"  [red]Error in {step.id}: {e}[/red]")

            sr.duration = time.time() - t1
            console.print(f"  [dim]{step.id}: {sr.status} ({sr.duration:.1f}s)[/dim]")

            return sr

    async def run_level(level: list[str]) -> None:
        """并发执行一层中的所有步骤。

        失败恢复逻辑：
        - 依赖失败步骤的步骤会被跳过（在 execute_step 中处理）
        - 不依赖失败步骤的步骤继续正常执行
        """
        tasks = [execute_step(step_map[sid]) for sid in level]
        step_results = await _asyncio_mod.gather(*tasks, return_exceptions=True)

        for sr in step_results:
            if isinstance(sr, StepResult):
                result.steps[sr.step_id] = sr
                # GAP-LLM-001: 累计真实 token usage
                result.total_tokens += sr.tokens or 0
                if sr.status == "failed":
                    result.status = "partial"
                elif sr.status == "skipped":
                    result.status = "partial"
                elif sr.status == "waiting_approval":
                    result.status = "waiting_approval"
                elif sr.status == "rejected":
                    result.status = "rejected"
                elif sr.status == "done":
                    context["steps"][sr.step_id] = sr.output if sr.output else ""
                    if sr.data is not None:
                        context.setdefault("step_data", {})[sr.step_id] = sr.data

                # P2-004: 本次 attempt 新增 token（跳过步骤的 tokens 是历史值，不计入）
                if sr.step_id not in resume_skip and sr.status == "done":
                    attempt_tokens_acc["n"] += sr.tokens or 0

                persist_progress()
            else:
                console.print(f"[red]Unexpected error: {sr}[/red]")
                result.status = "failed"

    # 运行所有层级
    async def run_all():
        for level_idx, level in enumerate(levels):
            console.print(f"\n[bold]--- Level {level_idx + 1}/{len(levels)} ---[/bold]")
            await run_level(level)
            if result.status in {"waiting_approval", "rejected"}:
                break

    try:
        if stream:
            _asyncio_mod.run(run_all())
        else:
            from soloflow.live_view import live_flow

            with live_flow(run_id, RUNS_DIR):
                _asyncio_mod.run(run_all())
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        result.status = "failed"

    result.total_duration = time.time() - t0

    # GAP-FLOW-004: 解析 flow.output 映射为正式输出
    if flow.output:
        for out_key, ref in flow.output.items():
            try:
                if isinstance(ref, str) and re.fullmatch(
                    r"\$steps\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.data(?:\.[\w-]+)*", ref
                ):
                    result.outputs[out_key] = _resolve_value(ref, context)
                else:
                    result.outputs[out_key] = _resolve_ref(str(ref), context)
            except Exception:
                result.outputs[out_key] = str(ref)  # 解析失败时保留原始引用

    # 汇总
    done_count = sum(1 for sr in result.steps.values() if sr.status == "done")
    fail_count = sum(1 for sr in result.steps.values() if sr.status == "failed")
    skip_count = sum(1 for sr in result.steps.values() if sr.status == "skipped")
    waiting_count = sum(1 for sr in result.steps.values() if sr.status == "waiting_approval")

    if result.status == "running":
        result.status = "done" if fail_count == 0 else "partial"

    status_color = "green" if result.status == "done" else "yellow"
    status_text = (
        f"Status: [bold]{result.status}[/bold]\n"
        f"Done: {done_count} | Failed: {fail_count} | Skipped: {skip_count} | "
        f"Waiting: {waiting_count} | "
        f"Duration: {result.total_duration:.1f}s"
    )

    console.print(Panel.fit(status_text, border_style=status_color))

    persist_progress()

    return result


def _new_flow_context(flow: FlowDefinition, inputs: dict[str, Any]) -> dict[str, Any]:
    """Build a clean context for a new run, including schema defaults."""
    context: dict[str, Any] = {"input": {}, "steps": {}, "step_data": {}, "_approvals": {}}
    if flow.input_schema:
        for key, spec in flow.input_schema.items():
            if isinstance(spec, dict) and "default" in spec:
                context["input"][key] = spec["default"]
    context["input"].update(inputs)
    return context


def run_flow(
    flow: FlowDefinition,
    inputs: dict[str, Any] | None = None,
    max_parallel: int = MAX_PARALLEL,
    dry_run: bool = False,
    stream: bool = False,
) -> FlowResult:
    """Start a new Flow run.

    Resume state is intentionally handled only by :func:`resume_flow`, keeping
    this public entry point limited to user-facing execution options.
    """
    user_inputs = inputs or {}
    return _execute_flow(
        flow,
        user_inputs,
        max_parallel,
        dry_run,
        stream,
        context=_new_flow_context(flow, user_inputs),
        resume_skip=set(),
        run_id=f"run-{uuid.uuid4().hex[:12]}",
        attempt=1,
    )


def resume_flow(
    run_id: str, max_parallel: int = MAX_PARALLEL, dry_run: bool = False, stream: bool = False
) -> FlowResult | None:
    """从之前的运行记录恢复 Flow 执行。

    加载 .soloflow/runs/<run_id>.json，跳过已完成的步骤，
    仅执行 pending/failed 的步骤。

    修复（BUG-FLOW-001/002/003）:
    - BUG-FLOW-001: 返回 run_flow 的真实新结果，而不是旧构造结果。
    - BUG-FLOW-002: 恢复复用原 run ID，attempt 递增，记录 resumed_at。
    - BUG-FLOW-003: 从 .steps/ 完整产物目录加载上游输出，跳过步骤
      的 StepResult 带回旧输出与耗时，恢复上下文完整。

    Args:
        run_id: 运行 ID。
        max_parallel: 最大并行步骤数。
        dry_run: 仅预览。
        stream: 流式输出。

    Returns:
        恢复后的真实 FlowResult 或 None（运行记录不存在/无效/无可恢复）。
    """
    run_file = RUNS_DIR / f"{run_id}.json"
    if not run_file.exists():
        console.print(f"[red]运行记录不存在: {run_id}[/red]")
        _list_runnable_ids()
        return None

    try:
        saved = json.loads(run_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        console.print(f"[red]运行记录损坏: {run_id}[/red]")
        return None

    flow_name = saved.get("flow_name", "")
    saved_steps = saved.get("steps", {})
    saved_inputs = saved.get("inputs", {})
    prev_attempt = int(saved.get("attempt", 1))

    from soloflow.core.assets import find_flow_path

    try:
        flow_path = find_flow_path(flow_name)
    except FileNotFoundError:
        console.print(f"[red]Flow 文件不存在: {flow_name}[/red]")
        return None

    flow = load_flow(flow_path)
    console.print(f"[bold]Resuming: {flow_name} (run: {run_id})[/bold]")

    completed = [sid for sid, s in saved_steps.items() if s.get("status") == "done"]
    pending = [sid for sid, s in saved_steps.items() if s.get("status") not in ("done",)]
    failed = [sid for sid, s in saved_steps.items() if s.get("status") == "failed"]

    console.print(
        f"  Completed: {len(completed)} — {', '.join(completed) if completed else 'none'}"
    )
    console.print(f"  Failed: {len(failed)} — {', '.join(failed) if failed else 'none'}")
    console.print(f"  Pending: {len(pending)} — {', '.join(pending) if pending else 'none'}")

    if not pending and not failed:
        console.print("[green]All steps completed. Nothing to resume.[/green]")
        return None

    # 完整输出（BUG-FLOW-003: 优先 .steps/ 完整产物，回退 JSON 摘要）
    full_outputs = _load_step_outputs(run_id)
    full_step_data = _load_step_data(run_id)
    # 旧步骤耗时（供跳过步骤带回）
    old_durations = {
        sid: float(sdata.get("duration", 0.0) or 0.0) for sid, sdata in saved_steps.items()
    }
    # P2-004: 旧步骤 token（供跳过步骤带回，保持 total_tokens 完整累计）
    old_tokens = {sid: int(sdata.get("tokens", 0) or 0) for sid, sdata in saved_steps.items()}

    context = {
        "input": saved_inputs,
        "steps": full_outputs,
        "step_data": full_step_data,
        "_approvals": saved.get("approvals", {}),
        "_resume_durations": old_durations,
        "_resume_tokens": old_tokens,
    }

    return _execute_flow(
        flow,
        saved_inputs,
        max_parallel,
        dry_run,
        stream,
        context=context,
        resume_skip=set(completed),
        run_id=run_id,
        attempt=prev_attempt + 1,
    )


def decide_approval(
    run_id: str, step_id: str, *, approved: bool, note: str = ""
) -> FlowResult | None:
    """Record a human decision and resume the paused Flow."""
    run_file = RUNS_DIR / f"{run_id}.json"
    if not run_file.exists():
        console.print(f"[red]运行记录不存在: {run_id}[/red]")
        return None

    try:
        saved = json.loads(run_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        console.print(f"[red]运行记录损坏: {run_id}[/red]")
        return None

    step_state = saved.get("steps", {}).get(step_id)
    if not isinstance(step_state, dict) or step_state.get("status") != "waiting_approval":
        console.print(f"[red]步骤不是待审批状态: {step_id}[/red]")
        return None

    saved.setdefault("approvals", {})[step_id] = {
        "decision": "approved" if approved else "rejected",
        "note": note,
        "decided_at": datetime_now_iso(),
    }
    # 将审批节点重新置为 pending，交给统一恢复流程执行并传播结果。
    step_state["status"] = "pending"
    step_state["error"] = None
    saved["status"] = "pending"
    run_file.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return resume_flow(run_id)


def _list_runnable_ids() -> None:
    """列出可恢复的运行 ID。"""
    if not RUNS_DIR.is_dir():
        return
    runs = sorted(RUNS_DIR.glob("*.json"))
    if runs:
        console.print("[dim]可恢复的运行:[/dim]")
        for f in runs:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                status = data.get("status", "?")
                steps = data.get("steps", {})
                done = sum(
                    1 for s in steps.values() if isinstance(s, dict) and s.get("status") == "done"
                )
                console.print(
                    f"  {f.stem} — {data.get('flow_name', '?')} "
                    f"[{status}] ({done}/{len(steps)} done)"
                )
            except Exception:
                console.print(f"  {f.stem} — 无法读取")
