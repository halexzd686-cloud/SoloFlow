"""Skill 自我迭代引擎。

通过 LLM 评估 → 改进 → 再评估的循环，自动优化 Skill 的 prompt。
这是 SoloFlow 最具差异化的功能。

改进要点 (v0.7):
- 健壮的 JSON 提取（多种 LLM 输出格式）
- 迭代产物保存到 .soloflow/iterations/
- 分数停滞自动提前终止
- 更精准的评估 prompt
"""

import datetime
import json
import re
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from soloflow.core.skill_loader import save_skill
from soloflow.llm.client import call_llm
from soloflow.models.skill import SkillFile

console = Console()

ITER_DIR = Path(".soloflow/iterations")

EVALUATOR_PROMPT = """你是一位严格的 AI 输出质量评估专家。

请评估以下 Skill 的输出质量，给出精确的评分和改进建议。

## Skill 定义
{skill_prompt}

## 测试输入
{test_input}

## AI 输出
{test_output}

## 评估标准（每项 0.0-1.0 分）

评分锚点：
- 0.9-1.0: 优秀，可直接用于生产环境
- 0.7-0.9: 良好，有少量可改进空间
- 0.5-0.7: 一般，有明显缺陷需要改进
- 0.3-0.5: 较差，多项标准不达标
- 0.0-0.3: 不合格，输出完全不符合要求

1. **规则遵循度 (rule_compliance)**: Skill 中声明的 rules 是否被严格遵守？
   - 1.0 = 每条规则都完美遵循
   - 0.5 = 大部分遵循但有例外
   - 0.0 = 完全忽略规则

2. **CoSTAR 匹配度 (costar_match)**: 输出是否匹配 Context/Objective/Style/Tone/Audience？
   - 特别注意 Tone（语气）和 Audience（受众）是否匹配

3. **结构清晰度 (structure)**: 输出结构是否清晰、有逻辑？读者能否快速找到关键信息？
   - 好结构: 有标题层级、有摘要/结论、段落长度合理

4. **内容有用性 (usefulness)**: 输出是否具体、可操作、有深度？
   - 具体 > 泛泛而谈，有案例 > 纯理论，有数据 > 纯观点

5. **去 AI 味 (ai_smell)**: 输出是否自然，避免了 AI 常见的模板化表达？
   - 低分标志: "As an AI", "Certainly!", "I hope this helps", 过度礼貌,
     套路化开头("在当今..."), 不必要的免责声明
   - 高分标志: 自然的人类写作风格，直接、有态度、有个性

## 输出格式（严格 JSON）

```json
{{
  "score": 0.85,
  "rule_compliance": 0.9,
  "costar_match": 0.8,
  "structure": 0.9,
  "usefulness": 0.8,
  "ai_smell": 0.7,
  "issues": ["具体问题1: 第三段使用了'在当今时代'的套路开头", "具体问题2: ..."],
  "suggestions": ["具体可执行的改进建议1", "具体可执行的改进建议2"]
}}
```

**重要**:
- score 应为五项子分数的加权平均（rule_compliance 权重 0.25，其余各 0.1875）
- issues 必须引用输出中的具体内容，不要泛泛而谈
- suggestions 必须是可执行的、具体的改进动作
- 只输出 JSON，不要其他任何文字"""


IMPROVER_PROMPT = """你是一位 AI Prompt 工程专家，专门优化 Skill/System Prompt。

请根据评估反馈，改进以下 Skill 的 Markdown body 部分。**不要修改 YAML frontmatter**。

## 当前 Skill
{skill_prompt}

## 评估反馈
- 综合评分: {score}/1.0
- 规则遵循度: {rule_compliance}
- CoSTAR 匹配度: {costar_match}
- 结构清晰度: {structure}
- 内容有用性: {usefulness}
- 去 AI 味: {ai_smell}（越高越好 = 越自然）

**发现的问题:**
{issues}

**改进建议:**
{suggestions}

## 改进原则（按优先级）

1. **针对性修复**: 逐条回应 issues 中的具体问题。每条 issue 必须在 body 中有对应的改进措施。

2. **增强约束力**:
   - 模糊表述 → 可测量标准（"段落简短" → "每段不超过 4 行"）
   - 可选建议 → 强制规则（"建议使用案例" → "每个观点必须附带一个具体案例"）
   - 抽象任务 → 具体步骤（"分析市场" → "1.市场规模 2.增长率 3.主要玩家 4.趋势"）

3. **实例驱动**:
   - 每个关键规则附带正例和反例
   - 提供输出模板/格式示例
   - 标注"失败模式"：常见错误及如何避免

4. **保持定位**: 不改变 Skill 的核心目的、受众和风格。只增强，不替换。

5. **控制长度**: body 不应超过 1500 字符。如果增加内容，先删除冗余。

6. **去 AI 味加固**:
   - 明确禁止 AI 模板化表达（列一个禁止清单）
   - 鼓励有态度的、直接的表达
   - 提示"像人类专家一样说话，不像客服"

## 输出

直接输出改进后的完整 Markdown body（**只输出 body 内容**，不含 YAML frontmatter，不含解释文字）。"""


def _extract_json(text: str) -> dict | None:
    """从 LLM 输出中健壮地提取 JSON。

    处理多种格式：
    - 纯 JSON
    - ```json ... ```
    - ``` ... ```
    - 混杂了其他文字的 JSON
    - 带注释的 JSON（去除 // 和 /* */ 注释）
    """
    if not text:
        return None

    # 方法 1: ```json 代码块
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if m:
        result = _try_parse_json(m.group(1).strip())
        if result is not None:
            return result

    # 方法 2: ``` 代码块
    m = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if m:
        result = _try_parse_json(m.group(1).strip())
        if result is not None:
            return result

    # 方法 3: 查找 { ... } 对（最外层）
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        result = _try_parse_json(m.group(0).strip())
        if result is not None:
            return result

    return None


def _try_parse_json(text: str) -> dict | None:
    """尝试多种方式解析 JSON，包括修复常见格式错误。

    处理：
    - 标准 JSON
    - 尾随逗号
    - 单引号替代双引号
    - // 注释
    """
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 去除 // 注释
    cleaned = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 去除尾随逗号（在 } 或 ] 之前）
    cleaned = re.sub(r",\s*(\}|\])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试替换单引号为双引号（保守：只替换 key 和简单 value）
    try:
        fixed = re.sub(r"'([^']*)'(\s*:)", r'"\1"\2', cleaned)
        fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return None


def _save_iteration_artifact(
    skill_name: str,
    round_num: int,
    phase: str,
    content: str,
) -> Path:
    """保存迭代产物到 .soloflow/iterations/<skill>/round_<N>_<phase>.md。"""
    dir_path = ITER_DIR / skill_name / f"round_{round_num:02d}"
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{phase}.md"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def iterate_skill(
    skill: SkillFile,
    skill_path: Path,
    count: int = 3,
    test_inputs: list[str] | None = None,
    dry_run: bool = False,
    early_stop_threshold: float = 0.02,
) -> SkillFile:
    """对 Skill 进行 N 轮自我迭代优化。

    Args:
        skill: 原始 Skill 对象。
        skill_path: Skill 文件路径（用于保存迭代结果）。
        count: 最大迭代轮数。
        test_inputs: 测试输入列表。
        dry_run: 仅模拟，不实际调用 LLM。
        early_stop_threshold: 连续两轮分数提升低于此值则提前终止。

    Returns:
        迭代优化后的 Skill 对象。
    """
    if test_inputs is None:
        test_inputs = [
            f"请用 {skill.meta.name} 技能完成一个示例任务，展示你的专业能力。",
            "请详细说明你的工作流程和方法论。",
            "请处理一个边缘情况的输入。",
        ]

    console.print(
        Panel.fit(
            f"[bold cyan]Skill 自我迭代[/bold cyan]\n"
            f"目标: {skill.meta.name} v{skill.meta.version}\n"
            f"迭代轮数: {count}\n"
            f"测试用例: {len(test_inputs)} 个\n"
            f"提前终止阈值: {early_stop_threshold}",
            border_style="cyan",
        )
    )

    if dry_run:
        console.print("[yellow]Dry run 模式 —— 仅模拟迭代流程[/yellow]")

    table = Table(title="迭代记录")
    table.add_column("轮次", style="cyan")
    table.add_column("评分", style="yellow")
    table.add_column("规则", style="dim")
    table.add_column("结构", style="dim")
    table.add_column("有用", style="dim")
    table.add_column("AI味", style="dim")
    table.add_column("问题")
    table.add_column("耗时")

    current = skill
    best_body = skill.body  # 追踪最佳版本，防止退化
    best_score = -1.0
    start_version = current.iteration.version or 0
    prev_score = -1.0

    for round_num in range(1, count + 1):
        console.print(f"\n[bold]── 第 {round_num}/{count} 轮迭代 ──[/bold]")

        round_start = time.time()

        # 阶段 1: 测试当前 Skill
        scores = []
        all_issues = []
        all_suggestions = []
        detail_scores = {
            "rule_compliance": [],
            "costar_match": [],
            "structure": [],
            "usefulness": [],
            "ai_smell": [],
        }

        for ti, test_input in enumerate(test_inputs, 1):
            console.print(f"[dim]测试 {ti}/{len(test_inputs)}...[/dim]")

            if dry_run:
                test_output = f"[模拟输出] 对 '{test_input[:50]}...' 的响应"
            else:
                full_prompt = f"{current.full_prompt}\n\n---\n\n# Task\n\n{test_input}"
                try:
                    test_output = call_llm(
                        prompt=full_prompt,
                        model=current.config.model,
                        provider=current.config.provider,
                        temperature=0.3,
                        max_tokens=current.config.max_tokens,
                    )
                except RuntimeError as e:
                    console.print(f"[red]测试执行失败: {e}[/red]")
                    # 保存中间结果再退出
                    save_skill(current, skill_path)
                    return current
                except ImportError as e:
                    console.print(f"[red]依赖缺失: {e}[/red]")
                    return current

            # 阶段 2: 评估
            eval_prompt = EVALUATOR_PROMPT.format(
                skill_prompt=current.full_prompt,
                test_input=test_input,
                test_output=test_output,
            )

            if dry_run:
                score = 0.8
                issues = ["[示例] 输出不够具体"]
                suggestions = ["增加具体案例要求"]
                for k in detail_scores:
                    detail_scores[k].append(0.8)
            else:
                try:
                    eval_result = call_llm(
                        prompt=eval_prompt,
                        model=current.config.model,
                        provider=current.config.provider,
                        temperature=0.2,
                        max_tokens=1024,
                    )
                    parsed = _extract_json(eval_result)
                    if parsed:
                        score = float(parsed.get("score", 0.5))
                        issues = parsed.get("issues", [])
                        suggestions = parsed.get("suggestions", [])
                        for k in detail_scores:
                            detail_scores[k].append(float(parsed.get(k, score)))
                    else:
                        console.print("[yellow]评估 JSON 解析失败，使用默认值[/yellow]")
                        _save_iteration_artifact(
                            current.meta.name, round_num, f"eval_{ti}_raw", eval_result
                        )
                        score = 0.5
                        issues = ["评估解析失败"]
                        suggestions = ["改进评估 prompt"]
                        for k in detail_scores:
                            detail_scores[k].append(0.5)
                except RuntimeError as e:
                    console.print(f"[yellow]评估 LLM 调用失败: {e}[/yellow]")
                    score = 0.5
                    issues = [f"评估失败: {e}"]
                    suggestions = ["检查 API Key 和网络连接"]
                    for k in detail_scores:
                        detail_scores[k].append(0.5)

            # 保存测试输出
            if not dry_run:
                _save_iteration_artifact(
                    current.meta.name, round_num, f"test_{ti}_output", test_output
                )
                _save_iteration_artifact(
                    current.meta.name, round_num, f"test_{ti}_eval", eval_prompt
                )

            scores.append(score)
            all_issues.extend(issues)
            all_suggestions.extend(suggestions)

        avg_score = sum(scores) / len(scores) if scores else 0
        avg_details = {k: sum(v) / len(v) if v else 0 for k, v in detail_scores.items()}

        # ── 追踪最佳版本（防止退化）──
        if avg_score > best_score:
            best_score = avg_score
            best_body = current.body
            console.print(f"[dim]  新最佳评分: {best_score:.3f}[/dim]")
        elif avg_score < best_score - 0.05 and round_num > 1:
            # 分数明显退化，回退到最佳版本
            console.print(
                f"[yellow]  评分退化 ({avg_score:.3f} < {best_score:.3f})，回退到最佳版本[/yellow]"
            )
            current.body = best_body

        # 阶段 3: 改进（最后一轮不改，只评估）
        if round_num < count:
            improve_prompt = IMPROVER_PROMPT.format(
                skill_prompt=current.full_prompt,
                score=f"{avg_score:.2f}",
                rule_compliance=f"{avg_details.get('rule_compliance', 0):.2f}",
                costar_match=f"{avg_details.get('costar_match', 0):.2f}",
                structure=f"{avg_details.get('structure', 0):.2f}",
                usefulness=f"{avg_details.get('usefulness', 0):.2f}",
                ai_smell=f"{avg_details.get('ai_smell', 0):.2f}",
                issues="\n".join(f"- {i}" for i in all_issues[:5]),
                suggestions="\n".join(f"- {s}" for s in all_suggestions[:5]),
            )

            # 保存改进 prompt 供审查
            if not dry_run:
                _save_iteration_artifact(
                    current.meta.name, round_num, "improve_prompt", improve_prompt
                )

            if not dry_run:
                try:
                    improved_body = call_llm(
                        prompt=improve_prompt,
                        model=current.config.model,
                        provider=current.config.provider,
                        temperature=0.4,
                        max_tokens=2048,
                    )
                    # 清理可能的 markdown 代码块包裹
                    improved_body = improved_body.strip()
                    if improved_body.startswith("```"):
                        improved_body = re.sub(r"^```\w*\n", "", improved_body)
                        improved_body = re.sub(r"\n```$", "", improved_body)
                    current.body = improved_body

                    _save_iteration_artifact(
                        current.meta.name, round_num, "improved_body", improved_body
                    )
                except RuntimeError as e:
                    console.print(f"[red]改进失败: {e}[/red]")
                    continue

        # 更新迭代元数据
        current.iteration.version = start_version + round_num
        current.iteration.score = avg_score
        current.iteration.evaluated_at = datetime.datetime.now().isoformat()
        current.iteration.changelog.append(
            f"v{start_version + round_num}: 评分 {avg_score:.2f}, "
            f"修复 {len(all_issues)} 个问题, {len(all_suggestions)} 条建议"
        )

        # 保存
        if not dry_run:
            save_skill(current, skill_path)

        elapsed = time.time() - round_start
        table.add_row(
            str(round_num),
            f"{avg_score:.2f}",
            f"{avg_details.get('rule_compliance', 0):.2f}",
            f"{avg_details.get('structure', 0):.2f}",
            f"{avg_details.get('usefulness', 0):.2f}",
            f"{avg_details.get('ai_smell', 0):.2f}",
            str(len(all_issues)),
            f"{elapsed:.1f}s",
        )

        # 提前终止检查
        if prev_score >= 0 and (avg_score - prev_score) < early_stop_threshold:
            console.print(
                f"\n[yellow]分数提升 {avg_score - prev_score:.3f} < "
                f"{early_stop_threshold}，提前终止[/yellow]"
            )
            break
        prev_score = avg_score

    console.print(table)

    # 最终汇总
    console.print(
        f"\n[green]✓ 迭代完成[/green] "
        f"({start_version} → {current.iteration.version}), "
        f"最终评分: {current.iteration.score:.2f}"
    )

    if not dry_run:
        artifacts_path = ITER_DIR / current.meta.name
        console.print(f"[dim]迭代产物: {artifacts_path}[/dim]")

    return current
