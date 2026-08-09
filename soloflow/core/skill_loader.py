"""Skill 文件加载器。

支持从 SKILL.md 文件（YAML frontmatter + Markdown body）加载和保存。
兼容 agentskills.io 社区标准格式，同时扩展了 SoloFlow 的 CoSTAR 字段。
"""

from pathlib import Path

import yaml

from soloflow.models.skill import (
    CoSTAR,
    SkillConfig,
    SkillFile,
    SkillIteration,
    SkillMeta,
)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter + Markdown body。

    格式：
    ---
    key: value
    ---
    Markdown body...
    """
    text = text.strip()
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    yaml_str = parts[1].strip()
    body = parts[2].strip()

    if yaml_str:
        frontmatter = yaml.safe_load(yaml_str) or {}
    else:
        frontmatter = {}

    return frontmatter, body


# load_skill 已知的全部 frontmatter 键（用于区分"未知扩展字段"）
_KNOWN_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "version",
        "description",
        "author",
        "license",
        "tags",
        "model",
        "provider",
        "temperature",
        "max_tokens",
        "context",
        "objective",
        "style",
        "tone",
        "audience",
        "response_format",
        "rules",
        "depends_on",
        "examples",
        "tests",
        "iteration_version",
        "iteration_score",
        "iteration_evaluated_at",
        "iteration_changelog",
    }
)


def _build_frontmatter(skill: SkillFile) -> str:
    """将 SkillFile 序列化为 YAML frontmatter 字符串。

    保证无损 round-trip（BUG-SKILL-001 修复）：
    - 写回 examples / tests / iteration.changelog（此前丢失）
    - 合并 extra_frontmatter 中的未知扩展字段（向前兼容）
    - 已知字段优先，未被占用的未知字段原样保留
    """
    data = {
        # 标准 SKILL.md 字段
        "name": skill.meta.name,
        "version": skill.meta.version,
        "description": skill.meta.description,
        "author": skill.meta.author,
        "license": skill.meta.license,
        "tags": skill.meta.tags,
        # LLM 配置
        "model": skill.config.model,
        "provider": skill.config.provider,
        "temperature": skill.config.temperature,
        "max_tokens": skill.config.max_tokens,
        # CoSTAR 字段
        "context": skill.costar.context or None,
        "objective": skill.costar.objective or None,
        "style": skill.costar.style or None,
        "tone": skill.costar.tone or None,
        "audience": skill.costar.audience or None,
        "response_format": skill.costar.response_format or None,
        # 规则
        "rules": skill.rules or None,
        # 示例与测试（BUG-SKILL-001: 此前未写回）
        "examples": [ex.model_dump() for ex in skill.examples] or None,
        "tests": [t.model_dump() for t in skill.tests] or None,
        # 依赖
        "depends_on": skill.dependencies or None,
        # 迭代元数据（仅当有迭代记录时写入）
        "iteration_version": skill.iteration.version or None,
        "iteration_score": skill.iteration.score,
        "iteration_evaluated_at": skill.iteration.evaluated_at,
        "iteration_changelog": skill.iteration.changelog or None,
    }
    # 移除 None / 空值
    data = {k: v for k, v in data.items() if v is not None and v != [] and v != ""}
    # 合并未知扩展字段（已知字段优先，避免覆盖）
    for k, v in skill.extra_frontmatter.items():
        if k not in data:
            data[k] = v
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_skill(path: str | Path) -> SkillFile:
    """从文件路径加载一个 Skill。

    Args:
        path: SKILL.md 文件或包含 SKILL.md 的目录路径。

    Returns:
        解析后的 SkillFile 对象。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: YAML 解析失败或格式不合法。
    """
    path = Path(path)

    # 如果是目录，找目录下的 SKILL.md
    if path.is_dir():
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(f"目录中未找到 SKILL.md: {path}")
        path = skill_md

    if not path.exists():
        raise FileNotFoundError(f"Skill 文件不存在: {path}")

    if path.suffix not in (".md", ".yml", ".yaml"):
        raise ValueError(f"不支持的文件格式: {path.suffix}，请使用 .md 或 .yml")

    text = path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)

    if "name" not in frontmatter:
        # 尝试用文件名作为 name
        frontmatter["name"] = path.stem.lower().replace("_", "-")

    # 构建 SkillFile
    skill = SkillFile(
        meta=SkillMeta(
            name=frontmatter.get("name", path.stem),
            version=str(frontmatter.get("version", "0.1.0")),
            author=str(frontmatter.get("author", "unknown")),
            description=str(frontmatter.get("description", "")),
            license=str(frontmatter.get("license", "MIT")),
            tags=frontmatter.get("tags", []),
        ),
        costar=CoSTAR(
            context=str(frontmatter.get("context", "")),
            objective=str(frontmatter.get("objective", "")),
            style=str(frontmatter.get("style", "")),
            tone=str(frontmatter.get("tone", "")),
            audience=str(frontmatter.get("audience", "")),
            response_format=str(frontmatter.get("response_format", "")),
        ),
        config=SkillConfig(
            model=str(frontmatter.get("model", "deepseek-v4-flash")),
            provider=str(frontmatter.get("provider", "deepseek")),
            temperature=float(frontmatter.get("temperature", 0.7)),
            max_tokens=int(frontmatter.get("max_tokens", 4096)),
        ),
        rules=frontmatter.get("rules", []),
        examples=frontmatter.get("examples", []),
        tests=frontmatter.get("tests", []),
        body=body,
        dependencies=frontmatter.get("depends_on", []),
        iteration=SkillIteration(
            version=int(frontmatter.get("iteration_version", 0)),
            score=frontmatter.get("iteration_score"),
            evaluated_at=frontmatter.get("iteration_evaluated_at"),
            changelog=frontmatter.get("iteration_changelog", []),
        ),
        # 保留无法映射到已知字段的扩展键，避免 load → save 丢失
        extra_frontmatter={
            k: v for k, v in frontmatter.items() if k not in _KNOWN_FRONTMATTER_KEYS
        },
    )

    return skill


def save_skill(skill: SkillFile, path: str | Path) -> Path:
    """将 SkillFile 保存为 SKILL.md 文件。

    Args:
        skill: SkillFile 对象。
        path: 目标路径（目录或 .md 文件）。

    Returns:
        实际写入的文件路径。
    """
    path = Path(path)

    if path.suffix == "" or path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        path = path / "SKILL.md"

    frontmatter = _build_frontmatter(skill)
    content = f"---\n{frontmatter}---\n\n{skill.body}"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")

    return path


def list_skills(skills_dir: str | Path) -> list[dict]:
    """列出目录下所有可用的 Skill。

    扫描 skills_dir 下的所有目录（每个目录包含 SKILL.md）。

    Returns:
        包含 name, path, description 的字典列表。
    """
    skills_dir = Path(skills_dir)
    if not skills_dir.is_dir():
        return []

    results = []
    # 递归搜索 skills_dir 下所有包含 SKILL.md 的目录
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        try:
            skill = load_skill(skill_md)
            results.append(
                {
                    "name": skill.meta.name,
                    "path": str(skill_md),
                    "version": skill.meta.version,
                    "description": skill.meta.description,
                    "tags": skill.meta.tags,
                }
            )
        except Exception:
            # 跳过无法解析的 Skill
            continue

    return results


def list_available_skills(
    project_dir: str | Path = "skills",
    *,
    include_project: bool = True,
    include_global: bool = True,
    include_bundled: bool = True,
) -> list[dict]:
    """List discoverable Skills with project/user overrides taking precedence."""
    from soloflow.core.assets import bundled_asset_dir

    sources: list[tuple[str, Path]] = []
    if include_project:
        sources.append(("project", Path(project_dir)))
    if include_global:
        sources.append(("global", Path.home() / ".soloflow" / "skills"))
    if include_bundled:
        sources.append(("bundled", bundled_asset_dir("skills")))

    results: list[dict] = []
    seen: set[str] = set()
    for source, directory in sources:
        for skill in list_skills(directory):
            if skill["name"] in seen:
                continue
            seen.add(skill["name"])
            results.append({**skill, "source": source})
    return results


def find_skill(name_or_path: str, project_dir: str | Path | None = None) -> Path:
    """按名称或路径查找 Skill 文件。

    查找顺序：
    1. 直接路径（文件或目录）
    2. 项目 skills/ 目录下递归搜索（按目录名匹配）
    3. 全局 ~/.soloflow/skills/ 目录下递归搜索
    4. wheel 内置 Skill 目录下递归搜索

    Args:
        name_or_path: Skill 名称或路径。
        project_dir: 项目根目录（默认当前工作目录）。

    Returns:
        SKILL.md 文件路径。

    Raises:
        FileNotFoundError: 未找到。
    """
    import os as _os

    # 1. 直接路径
    direct = Path(name_or_path)
    if direct.exists():
        if direct.is_file():
            return direct
        if direct.is_dir():
            skill_md = direct / "SKILL.md"
            if skill_md.exists():
                return skill_md

    # 2. 项目 skills/ 递归搜索
    base = Path(project_dir) if project_dir else Path(_os.getcwd())
    project_skills = base / "skills"
    if project_skills.is_dir():
        for skill_md in sorted(project_skills.rglob("SKILL.md")):
            if skill_md.parent.name == name_or_path:
                return skill_md

    # 3. 全局 skills/ 递归搜索
    global_skills = Path.home() / ".soloflow" / "skills"
    if global_skills.is_dir():
        for skill_md in sorted(global_skills.rglob("SKILL.md")):
            if skill_md.parent.name == name_or_path:
                return skill_md

    # 4. wheel 内置 Skill（项目和用户资产均可覆盖）
    from soloflow.core.assets import bundled_asset_dir

    bundled_skills = bundled_asset_dir("skills")
    if bundled_skills.is_dir():
        for skill_md in sorted(bundled_skills.rglob("SKILL.md")):
            if skill_md.parent.name == name_or_path:
                return skill_md

    raise FileNotFoundError(f"Skill not found: {name_or_path}")


def validate_skill(skill: SkillFile, strict: bool = False) -> list[str]:
    """校验 Skill 的完整性。

    Args:
        skill: SkillFile 对象。
        strict: 是否启用严格模式（要求 CoSTAR 必填字段 + 检查依赖版本）。

    Returns:
        问题列表，空列表表示通过。
    """
    issues = []

    # 基础校验
    if not skill.meta.name:
        issues.append("缺少 name")
    if not skill.meta.description:
        issues.append("缺少 description（建议填写以便 Skill 发现）")

    # 严格模式：CoSTAR 核心字段必填
    if strict:
        if not skill.costar.context:
            issues.append("[严格模式] 缺少 context（背景信息）")
        if not skill.costar.objective:
            issues.append("[严格模式] 缺少 objective（目标）")

    # body 不能为空
    if not skill.body.strip():
        issues.append("Markdown body 为空（至少需要包含 Instructions 部分）")

    # 依赖版本检查
    if skill.dependencies:
        dep_issues = validate_dependencies(skill.dependencies)
        if strict:
            issues.extend(dep_issues)
        elif dep_issues:
            issues.append(f"依赖版本问题: {len(dep_issues)} 项（用 --strict 查看详情）")

    return issues


def validate_dependencies(dependencies: list[str]) -> list[str]:
    """校验 Skill 的依赖是否满足版本约束。

    对每个依赖项查找已安装的 Skill，检查版本兼容性。

    Args:
        dependencies: 依赖规格字符串列表（如 ["code-reviewer@>=1.0.0"]）。

    Returns:
        问题列表，空列表表示全部满足。
    """
    from soloflow.models.skill import check_version_compatible, parse_dependency_spec

    issues = []

    for spec in dependencies:
        name, constraint, target_version = parse_dependency_spec(spec)

        # 查找已安装的 Skill
        try:
            dep_path = find_skill(name)
            dep_skill = load_skill(dep_path)
        except (FileNotFoundError, Exception):
            issues.append(f"依赖 '{name}' 未找到（{spec}）")
            continue

        # 检查版本兼容性
        if not check_version_compatible(dep_skill.meta.version, constraint, target_version):
            constraint_str = (
                f"{constraint}{target_version}" if constraint and target_version else "any"
            )
            issues.append(
                f"依赖 '{name}' 版本不兼容: "
                f"需要 {constraint_str}，实际 {dep_skill.meta.version} ({spec})"
            )

    return issues
