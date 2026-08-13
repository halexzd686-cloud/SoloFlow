"""工作手册文件加载器。

支持从 PLAYBOOK.md 或 SKILL.md 文件（YAML frontmatter + Markdown body）加载和保存。
兼容 agentskills.io 社区标准格式，同时扩展了 SoloFlow 的 CoSTAR 字段。
"""

from pathlib import Path

import yaml

from soloflow.models.skill import (
    CoSTAR,
    SkillConfig,
    SkillFile,
    SkillMeta,
)

PLAYBOOK_FILENAME = "PLAYBOOK.md"
SKILL_FILENAME = "SKILL.md"


def _definition_files(directory: Path) -> list[Path]:
    """Return supported work-manual files, preferring PLAYBOOK.md."""
    if not directory.is_dir():
        return []
    return sorted(directory.rglob(PLAYBOOK_FILENAME)) + sorted(directory.rglob(SKILL_FILENAME))


def _definition_file(directory: Path) -> Path | None:
    """Find the preferred definition file in a work-manual directory."""
    for filename in (PLAYBOOK_FILENAME, SKILL_FILENAME):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


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
        "base_url",
        "api_key_env",
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
    - 写回 examples / tests
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
        "base_url": skill.config.base_url,
        "api_key_env": skill.config.api_key_env,
        "model": skill.config.model,
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
    }
    # 移除 None / 空值
    data = {k: v for k, v in data.items() if v is not None and v != [] and v != ""}
    # 合并未知扩展字段（已知字段优先，避免覆盖）
    for k, v in skill.extra_frontmatter.items():
        if k not in data:
            data[k] = v
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_skill(path: str | Path) -> SkillFile:
    """从文件路径加载一个工作手册。

    Args:
        path: SKILL.md 文件或包含 SKILL.md 的目录路径。

    Returns:
        解析后的 SkillFile 对象。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: YAML 解析失败或格式不合法。
    """
    path = Path(path)

    # 如果是目录，优先找 PLAYBOOK.md，再兼容 SKILL.md
    if path.is_dir():
        definition = _definition_file(path)
        if definition is None:
            raise FileNotFoundError(f"目录中未找到 PLAYBOOK.md 或 SKILL.md: {path}")
        path = definition

    if not path.exists():
        raise FileNotFoundError(f"工作手册文件不存在: {path}")

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
            base_url=str(frontmatter.get("base_url", "https://api.deepseek.com")),
            api_key_env=str(frontmatter.get("api_key_env", "DEEPSEEK_API_KEY")),
            model=str(frontmatter.get("model", "deepseek-v4-flash")),
            temperature=float(frontmatter.get("temperature", 0.7)),
            max_tokens=int(frontmatter.get("max_tokens", 4096)),
        ),
        rules=frontmatter.get("rules", []),
        examples=frontmatter.get("examples", []),
        tests=frontmatter.get("tests", []),
        body=body,
        # 保留无法映射到已知字段的扩展键，避免 load → save 丢失
        extra_frontmatter={
            k: v for k, v in frontmatter.items() if k not in _KNOWN_FRONTMATTER_KEYS
        },
    )

    return skill


def save_skill(
    skill: SkillFile,
    path: str | Path,
    *,
    filename: str = SKILL_FILENAME,
) -> Path:
    """将 SkillFile 保存为指定文件名，默认使用兼容的 SKILL.md。

    Args:
        skill: SkillFile 对象。
        path: 目标路径（目录或 .md 文件）。

    Returns:
        实际写入的文件路径。
    """
    path = Path(path)

    if path.suffix == "" or path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        path = path / filename

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
    seen_names: set[str] = set()
    # 递归搜索两种格式；同一目录同时存在时优先使用 PLAYBOOK.md。
    for skill_md in _definition_files(skills_dir):
        try:
            skill = load_skill(skill_md)
            if skill.meta.name in seen_names:
                continue
            seen_names.add(skill.meta.name)
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


def save_playbook(skill: SkillFile, path: str | Path) -> Path:
    """Save a new-style work manual as PLAYBOOK.md."""
    return save_skill(skill, path, filename=PLAYBOOK_FILENAME)


def load_playbook(path: str | Path) -> SkillFile:
    """Compatibility-friendly alias for loading a Playbook."""
    return load_skill(path)


def find_playbook(name_or_path: str, project_dir: str | Path | None = None) -> Path:
    """Compatibility-friendly alias for finding a Playbook."""
    return find_skill(name_or_path, project_dir)


def list_available_playbooks(
    project_dir: str | Path | None = None,
    *,
    include_project: bool = True,
    include_global: bool = True,
    include_bundled: bool = True,
) -> list[dict]:
    """Compatibility-friendly alias for listing Playbooks."""
    return list_available_skills(
        project_dir,
        include_project=include_project,
        include_global=include_global,
        include_bundled=include_bundled,
    )


def list_available_skills(
    project_dir: str | Path | None = None,
    *,
    include_project: bool = True,
    include_global: bool = True,
    include_bundled: bool = True,
) -> list[dict]:
    """List discoverable Skills through the shared asset precedence."""
    from soloflow.core.assets import list_asset_paths

    paths = list_asset_paths(
        "skill",
        project_dir,
        include_project=include_project,
        include_user=include_global,
        include_bundled=include_bundled,
    )
    results: list[dict] = []
    for source, path in paths:
        try:
            skill = load_skill(path)
        except Exception:
            continue
        results.append(
            {
                "name": skill.meta.name,
                "path": str(path),
                "version": skill.meta.version,
                "description": skill.meta.description,
                "tags": skill.meta.tags,
                "source": "global" if source == "user" else source,
            }
        )
    return results


def find_skill(name_or_path: str, project_dir: str | Path | None = None) -> Path:
    """Resolve a Skill through the shared asset precedence."""
    from soloflow.core.assets import find_asset

    return find_asset("skill", name_or_path, project_dir)


def validate_skill(skill: SkillFile, strict: bool = False) -> list[str]:
    """校验 Skill 的完整性。

    Args:
        skill: SkillFile 对象。
        strict: 是否启用严格模式（要求 CoSTAR 必填字段）。

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

    return issues
