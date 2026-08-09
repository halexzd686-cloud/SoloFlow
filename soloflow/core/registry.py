"""Skill Registry —— Git 驱动的社区技能市场。

设计理念（类比 Homebrew）：
- 一个中央 GitHub 仓库作为 registry 索引
- `registry.yaml` 列出所有可用的 Skill 及其来源
- 用户可以搜索、安装、发布 Skill
- 本地缓存 registry 索引，离线也可搜索
"""

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import yaml
from rich.console import Console

from soloflow.core.skill_loader import load_skill
from soloflow.models.skill import SkillFile

console = Console()

# 默认的中央 Registry 仓库
DEFAULT_REGISTRY_REPO = "https://github.com/halexzd686-cloud/skills-registry.git"
DEFAULT_REGISTRY_BRANCH = "main"

# 本地路径
REGISTRY_CACHE = Path.home() / ".soloflow" / "registry"
REGISTRY_INDEX = REGISTRY_CACHE / "registry.yaml"
REGISTRY_SKILLS = REGISTRY_CACHE / "skills"

# 内置的离线 registry 索引（打包在模块中，无需网络即可使用）
BUNDLED_REGISTRY = Path(__file__).parent / "registry.yaml"


class RegistryEntry:
    """Registry 中的一条 Skill 条目。"""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "0.1.0")
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "unknown")
        self.tags: list[str] = data.get("tags", [])
        self.source: str = data.get("source", "")  # GitHub URL or local path
        self.downloads: int = data.get("downloads", 0)
        self.stars: int = data.get("stars", 0)

    def match(self, keyword: str) -> bool:
        """检查是否匹配搜索关键词。"""
        kw = keyword.lower()
        return (
            kw in self.name.lower()
            or kw in self.description.lower()
            or any(kw in tag.lower() for tag in self.tags)
            or kw in self.author.lower()
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "source": self.source,
            "downloads": self.downloads,
            "stars": self.stars,
        }


def _ensure_registry_cache() -> bool:
    """确保本地有 registry 缓存。不存在则尝试 clone。"""
    if REGISTRY_INDEX.exists():
        return True
    return update_registry()


def update_registry(registry_url: str = DEFAULT_REGISTRY_REPO) -> bool:
    """更新本地 registry 缓存（git pull 或 git clone）。

    Args:
        registry_url: Registry Git 仓库 URL。

    Returns:
        是否更新成功。
    """
    REGISTRY_CACHE.parent.mkdir(parents=True, exist_ok=True)

    if (REGISTRY_CACHE / ".git").exists() and REGISTRY_INDEX.exists():
        # 已有缓存，执行 pull
        console.print("[dim]Updating registry...[/dim]")
        try:
            # BUG-REG-003 修复: 检查 return code，失败必须明确报告
            pull_result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=REGISTRY_CACHE,
                capture_output=True,
                timeout=30,
                check=True,
            )
            stdout = pull_result.stdout.decode() if pull_result.stdout else ""
            console.print("[green][OK] Registry updated[/green]")
            if "Already up to date" in stdout:
                console.print("[dim]Already up to date.[/dim]")
            return True
        except Exception as e:
            stderr = ""
            if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                stderr = e.stderr.decode()
            console.print(f"[yellow]Warning: Failed to update registry: {stderr or e}[/yellow]")
            console.print("[dim]Continuing with existing cache.[/dim]")
            # 继续使用现有缓存
            return REGISTRY_INDEX.exists()
    else:
        # 首次使用或缓存不完整时，clone 到同盘 staging 后原子替换。
        # Windows 跨盘逐文件移动 .git pack 时可能被拒绝访问；把临时目录
        # 放在缓存父目录可确保最终替换使用同一文件系统内的 rename。
        console.print(f"[dim]Cloning registry from {registry_url}...[/dim]")
        backup: Path | None = None
        try:
            with tempfile.TemporaryDirectory(
                prefix=".registry-clone-", dir=REGISTRY_CACHE.parent
            ) as tmp:
                staging = Path(tmp)
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        "--branch",
                        DEFAULT_REGISTRY_BRANCH,
                        registry_url,
                        str(staging),
                    ],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                if not (staging / "registry.yaml").is_file():
                    raise RuntimeError("cloned registry is missing registry.yaml")

                if REGISTRY_CACHE.exists():
                    backup = REGISTRY_CACHE.parent / f".registry-backup-{uuid.uuid4().hex[:8]}"
                    REGISTRY_CACHE.rename(backup)

                try:
                    staging.rename(REGISTRY_CACHE)
                except OSError:
                    if backup is not None and backup.exists() and not REGISTRY_CACHE.exists():
                        backup.rename(REGISTRY_CACHE)
                    raise

                if backup is not None and backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
            console.print("[green][OK] Registry cloned[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Failed to clone registry: {e}[/red]")
            console.print(
                "[dim]You can still use local skills. Run 'sf registry update' to retry.[/dim]"
            )
            return False


def load_registry_index() -> list[RegistryEntry]:
    """加载 registry 索引。

    加载顺序：
    1. 本地缓存的远程 registry（通过 sf registry update 获取）
    2. 内置的离线 registry（打包在模块中，无需网络）

    Returns:
        RegistryEntry 列表。
    """
    # 优先使用缓存的远程索引
    if _ensure_registry_cache() and REGISTRY_INDEX.exists():
        try:
            data = yaml.safe_load(REGISTRY_INDEX.read_text(encoding="utf-8"))
            if data and "skills" in data:
                return [RegistryEntry(s) for s in data["skills"]]
        except Exception:
            pass

    # 回退到内置索引
    if BUNDLED_REGISTRY.exists():
        console.print("[dim]Using bundled registry index (offline mode)[/dim]")
        try:
            data = yaml.safe_load(BUNDLED_REGISTRY.read_text(encoding="utf-8"))
            if data and "skills" in data:
                return [RegistryEntry(s) for s in data["skills"]]
        except Exception:
            pass

    return []


def search_registry(keyword: str) -> list[RegistryEntry]:
    """搜索 registry 中的 Skill。

    Args:
        keyword: 搜索关键词。

    Returns:
        匹配的 RegistryEntry 列表。
    """
    entries = load_registry_index()
    return [e for e in entries if e.match(keyword)]


# GAP-REG-004: 供应链安全 —— 从第三方仓库安装的文件大小上限（5MB）
MAX_SKILL_DIR_BYTES = 5 * 1024 * 1024


def _verify_installed_version(
    dest_dir: Path,
    requested_version: str | None,
    fallback_latest: bool,
) -> Path | None:
    """安装后验证实际版本（BUG-REG-002 验收标准）。

    指定版本时:
    - 精确匹配 → 返回 SKILL.md 路径
    - 不匹配 → fallback_latest=True 时警告并接受，否则失败
    """
    skill_md = dest_dir / "SKILL.md"
    if not skill_md.exists():
        return None

    if requested_version is None:
        return skill_md  # 未指定版本，安装最新即可

    try:
        installed = load_skill(skill_md)
        actual = installed.meta.version
    except Exception:
        actual = "unknown"

    if actual == requested_version:
        return skill_md

    if fallback_latest:
        console.print(
            f"[yellow]请求版本 {requested_version}，实际安装 {actual} "
            f"（--fallback-latest 已接受）[/yellow]"
        )
        return skill_md

    console.print(
        f"[red]版本锁定失败: 请求 {requested_version}，实际 {actual}。"
        f"版本不存在时不静默回退最新版（BUG-REG-002）。"
        f"如确需最新版，请显式传 --fallback-latest。[/red]"
    )
    return None


def _check_skill_dir_size(source_dir: Path) -> bool:
    """GAP-REG-004: 检查 Skill 目录总大小是否超限。"""
    total = sum(f.stat().st_size for f in source_dir.rglob("*") if f.is_file())
    if total > MAX_SKILL_DIR_BYTES:
        console.print(
            f"[red]供应链安全检查失败: {source_dir} 大小 {total} 字节 "
            f"超过上限 {MAX_SKILL_DIR_BYTES} 字节[/red]"
        )
        return False
    return True


def _install_atomic(
    source_dir: Path,
    dest_dir: Path,
    version: str | None,
    fallback_latest: bool,
) -> Path | None:
    """staging + 原子替换安装（P1-004 修复）。

    保护用户已有安装：
    1. 复制源到临时 staging 目录（目标父目录下，点前缀隐藏）。
    2. 在 staging 内完成全部验证（大小/格式/版本）。
    3. 验证失败：只删除 staging，目标目录从未被触碰。
    4. 验证成功：目标目录 rename 到 backup → staging rename 为正式目录
       → 成功后删除 backup；替换失败则回滚 backup。

    Args:
        source_dir: 安装源目录（缓存/内置/Git clone 的 Skill 目录）。
        dest_dir: 最终安装目录。
        version: 请求版本（None=最新）。
        fallback_latest: 版本不存在时是否允许回退。

    Returns:
        安装后的 SKILL.md 路径，失败返回 None。
    """
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    staging = dest_dir.parent / f".{dest_dir.name}.staging-{suffix}"

    try:
        shutil.copytree(source_dir, staging, dirs_exist_ok=False)

        # ── staging 内完成全部验证 ──
        if not _check_skill_dir_size(staging):
            return None
        verified = _verify_installed_version(staging, version, fallback_latest)
        if verified is None:
            return None

        # ── 原子替换 ──
        backup: Path | None = None
        if dest_dir.exists():
            backup = dest_dir.parent / f".{dest_dir.name}.backup-{suffix}"
            dest_dir.rename(backup)

        try:
            staging.rename(dest_dir)
        except OSError as e:
            # 替换失败 → 回滚 backup，绝不留下半状态；按失败契约返回 None
            console.print(f"[red]安装替换失败，已回滚旧版本: {e}[/red]")
            if backup is not None and backup.exists() and not dest_dir.exists():
                try:
                    backup.rename(dest_dir)
                except OSError:
                    console.print(f"[red]回滚失败! 旧版本位于: {backup}，请手动恢复[/red]")
            return None

        # 成功 → 清理 backup
        if backup is not None and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

        return dest_dir / "SKILL.md"
    finally:
        # 任何失败路径都只清理 staging，目标目录不受影响
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def install_skill(
    name: str,
    target: str = "local",
    version: str = None,
    fallback_latest: bool = False,
    project_dir: Path | None = None,
) -> Path | None:
    """从 registry 安装一个 Skill。

    安装来源优先级：
    1. 本地缓存的 registry（registry.yaml 中的条目）
    2. 内置 registry（打包在模块中）
    3. Git clone（条目中的 source URL）

    BUG-REG-002 修复: 指定版本时必须精确安装该版本；
    版本不存在必须失败，除非显式传 fallback_latest=True。

    Args:
        name: Skill 名称。
        target: 安装目标 —— "project" (./skills/) 或 "local" (~/.soloflow/skills/)。
        version: 指定版本号。None 表示安装最新版。
        fallback_latest: 版本不存在时是否允许回退最新版（默认 False=严格）。
        project_dir: 项目根目录（默认当前工作目录）。用于内置 Skill 源查找。

    Returns:
        安装后的 Skill 路径，失败返回 None。
    """
    # 先在 registry 索引中查找
    entries = load_registry_index()
    entry = None
    for e in entries:
        if e.name == name:
            entry = e
            break

    if entry is None:
        console.print(f"[red]Skill '{name}' not found in registry.[/red]")
        console.print("[dim]Try 'sf registry search <keyword>' to find skills.[/dim]")
        return None

    # 版本提示
    if version:
        console.print(f"[dim]Pinning version: {version}[/dim]")
    else:
        console.print(f"[dim]Installing latest version: {entry.version}[/dim]")

    # 确定目标目录
    if target == "project":
        dest_dir = Path(os.getcwd()) / "skills" / name
    else:
        dest_dir = Path.home() / ".soloflow" / "skills" / name

    # 如果 registry 缓存中已有该 skill，直接复制
    cached_skill = REGISTRY_SKILLS / name
    if cached_skill.is_dir() and (cached_skill / "SKILL.md").exists():
        verified = _install_atomic(cached_skill, dest_dir, version, fallback_latest)
        if verified:
            console.print(f"[green][OK] Installed '{name}' to {dest_dir}[/green]")
        return verified

    # 对于内置 Skill（source 为空），从项目 skills 目录复制
    if not entry.source:
        from soloflow.core.skill_loader import find_skill as find_sk

        try:
            source_path = find_sk(name, project_dir=project_dir)
            source_dir = source_path.parent
            verified = _install_atomic(source_dir, dest_dir, version, fallback_latest)
            if verified:
                console.print(f"[green][OK] Installed '{name}' to {dest_dir}[/green]")
            return verified
        except FileNotFoundError:
            console.print(f"[red]Source for '{name}' is not available.[/red]")
            return None

    # 否则，尝试从 source URL 下载
    if entry.source:
        console.print(f"[dim]Downloading from {entry.source}...[/dim]")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                # 构建 clone 命令，支持版本锁定
                clone_args = ["git", "clone", "--depth", "1"]
                if version:
                    # 尝试 checkout 到指定版本的 tag 或 branch
                    clone_args += ["--branch", f"v{version}", entry.source, tmp]
                else:
                    clone_args += [entry.source, tmp]

                clone_result = subprocess.run(
                    clone_args,
                    capture_output=True,
                    timeout=60,
                )

                # BUG-REG-002: 指定版本失败时，默认失败而非静默回退
                if clone_result.returncode != 0:
                    if version and fallback_latest:
                        console.print(
                            f"[yellow]Tag v{version} not found，"
                            f"--fallback-latest 回退到默认分支[/yellow]"
                        )
                        subprocess.run(
                            ["git", "clone", "--depth", "1", entry.source, tmp],
                            capture_output=True,
                            timeout=60,
                            check=True,
                        )
                    elif version:
                        console.print(
                            f"[red]版本锁定失败: tag v{version} 不存在于 {entry.source}。"
                            f"如需最新版请显式传 --fallback-latest。[/red]"
                        )
                        return None
                    else:
                        clone_result.check_returncode()

                # 查找 SKILL.md
                tmp_path = Path(tmp)
                skill_md = None
                for f in tmp_path.rglob("SKILL.md"):
                    skill_md = f
                    break

                if skill_md is None:
                    console.print(f"[red]No SKILL.md found in {entry.source}[/red]")
                    return None

                # 找到 skill 目录（包含 SKILL.md 的目录）
                skill_dir = skill_md.parent
                verified = _install_atomic(skill_dir, dest_dir, version, fallback_latest)
                if verified:
                    console.print(f"[green][OK] Installed '{name}' from {entry.source}[/green]")
                return verified
        except Exception as e:
            console.print(f"[red]Failed to download: {e}[/red]")
            return None

    console.print(f"[red]No source available for '{name}'[/red]")
    return None


def publish_skill(
    name: str, submit: bool = False, message: str = "", fork_name: str = ""
) -> Path | None:
    """导出一个 Skill 为可分享的格式，可选自动提交到社区 Registry。

    生成一个包含 SKILL.md 和所有相关文件的目录，
    放在 .soloflow/publish/ 下。

    当 submit=True 时，自动：
    1. 打包 Skill
    2. 生成 Registry 条目
    3. Fork/Clone 社区 Registry 仓库
    4. 添加 Skill 文件 + 更新 registry.yaml
    5. 通过 gh CLI 创建 PR

    Args:
        name: Skill 名称。
        submit: 是否自动提交 PR 到社区 Registry。
        message: PR 描述（可选）。
        fork_name: GitHub fork 目标 (user/repo)，默认使用 soloflow-community/skills-registry。

    Returns:
        发布目录路径，失败返回 None。
    """
    from soloflow.core.skill_loader import find_skill, load_skill

    # 查找 Skill
    try:
        skill_path = find_skill(name)
        skill = load_skill(skill_path)
    except FileNotFoundError:
        console.print(f"[red]Skill '{name}' not found.[/red]")
        return None

    # ── Step 1: 本地打包 ──
    publish_dir = Path(os.getcwd()) / ".soloflow" / "publish" / name
    publish_dir.mkdir(parents=True, exist_ok=True)

    # 复制 skill 目录
    source_dir = skill_path.parent
    for item in source_dir.iterdir():
        dest = publish_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    # 生成 README（如果没有的话）
    readme = publish_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {skill.meta.name}\n\n"
            f"**Version**: {skill.meta.version}\n"
            f"**Author**: {skill.meta.author}\n"
            f"**Tags**: {', '.join(skill.meta.tags)}\n\n"
            f"## Description\n\n{skill.meta.description}\n\n"
            f"## Usage\n\n```bash\n"
            f"sf registry install {skill.meta.name}\n"
            f"sf skill run {skill.meta.name} <your-task>\n"
            f"```\n",
            encoding="utf-8",
        )

    console.print(f"[green][OK] Skill packaged: {publish_dir}[/green]")

    # ── Step 2: 生成 Registry 条目 ──
    entry = _generate_registry_entry(skill, name)
    entry_yaml = yaml.dump([entry], allow_unicode=True, default_flow_style=False, sort_keys=False)

    console.print("[bold]Registry Entry:[/bold]")
    console.print(f"  name: {entry['name']}")
    console.print(f"  version: {entry['version']}")
    console.print(f"  tags: {', '.join(entry['tags'])}")

    if not submit:
        console.print("\n[dim]To share this skill:[/dim]")
        console.print(f"  1. Push {publish_dir} to GitHub")
        console.print("  2. Add the entry below to registry.yaml via PR:")
        console.print(f"     {entry_yaml.strip()}")
        console.print("\n[dim]Or run with --submit to automate all steps.[/dim]")
        return publish_dir

    # ── Step 3: 自动提交 PR ──
    return _submit_to_registry(
        name=name,
        publish_dir=publish_dir,
        registry_entry=entry,
        message=message,
        fork_name=fork_name,
    )


def _generate_registry_entry(skill: SkillFile, name: str) -> dict:
    """从 SKILL.md 元数据生成 Registry 条目。

    Args:
        skill: 已加载的 SkillFile。
        name: Skill 名称。

    Returns:
        YAML-ready 字典。
    """
    return {
        "name": skill.meta.name,
        "version": skill.meta.version,
        "description": skill.meta.description,
        "author": skill.meta.author,
        "tags": skill.meta.tags,
        "source": "",  # 用户可以在 PR 中填写
    }


def _submit_to_registry(
    name: str,
    publish_dir: Path,
    registry_entry: dict,
    message: str = "",
    fork_name: str = "",
) -> Path | None:
    """自动提交 Skill 到社区 Registry。

    工作流程：
    1. 检查 gh CLI 是否可用
    2. Fork/Clone 社区 Registry 仓库
    3. 添加 Skill 文件到 skills/<name>/
    4. 更新 registry.yaml 添加新条目
    5. Commit + Push 到 fork
    6. 通过 gh pr create 创建 PR

    Args:
        name: Skill 名称。
        publish_dir: 打包好的 Skill 目录。
        registry_entry: Registry YAML 条目字典。
        message: PR 描述。
        fork_name: Fork 目标。

    Returns:
        publish_dir，失败返回 None。
    """
    registry_repo = fork_name or DEFAULT_REGISTRY_REPO

    # 检查 gh CLI
    gh_available = _check_gh_cli()
    git_available = _check_git()

    if not git_available:
        console.print("[red]Git is not available. Cannot submit to registry.[/red]")
        console.print("[dim]Please manually push to GitHub and create a PR.[/dim]")
        return publish_dir

    # 认证状态
    if gh_available:
        try:
            auth_check = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10)
            if auth_check.returncode != 0:
                console.print(
                    "[yellow]gh CLI not authenticated. Run 'gh auth login' first.[/yellow]"
                )
                console.print("[dim]Falling back to manual mode...[/dim]")
                gh_available = False
        except Exception:
            gh_available = False

    # ── 在临时目录中操作 ──
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        registry_dir = tmp_path / "registry"

        console.print(f"\n[bold]Step 1/5:[/bold] Cloning registry {registry_repo}...")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", registry_repo, str(registry_dir)],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            console.print(
                f"[red]Failed to clone registry: {e.stderr.decode() if e.stderr else e}[/red]"
            )
            console.print("[dim]The community registry may not exist yet.")
            console.print(f"[dim]Consider creating it at: {registry_repo}[/dim]")
            console.print(f"[dim]Then re-run: sf registry publish {name} --submit[/dim]")
            return publish_dir

        # ── 添加 Skill 文件 ──
        console.print("[bold]Step 2/5:[/bold] Adding skill files to registry...")
        skills_dir = registry_dir / "skills" / name
        skills_dir.mkdir(parents=True, exist_ok=True)

        for item in publish_dir.iterdir():
            dest = skills_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        # ── 更新 registry.yaml ──
        console.print("[bold]Step 3/5:[/bold] Updating registry index...")
        registry_yaml_path = registry_dir / "registry.yaml"
        if registry_yaml_path.exists():
            existing_data = yaml.safe_load(registry_yaml_path.read_text(encoding="utf-8")) or {}
        else:
            existing_data = {"version": 1, "skills": []}

        existing_skills = existing_data.get("skills", [])

        # 检查是否已存在同名 Skill
        existing_names = {s["name"] for s in existing_skills if isinstance(s, dict)}
        if name in existing_names:
            console.print(
                f"[yellow]Skill '{name}' already exists in registry. Updating entry...[/yellow]"
            )
            existing_skills = [s for s in existing_skills if s.get("name") != name]

        existing_skills.append(registry_entry)
        existing_data["skills"] = existing_skills
        existing_data["updated"] = time.strftime("%Y-%m-%d")

        registry_yaml_path.write_text(
            yaml.dump(existing_data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        # ── Commit ──
        console.print("[bold]Step 4/5:[/bold] Committing changes...")
        try:
            subprocess.run(
                ["git", "-C", str(registry_dir), "add", "-A"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            commit_msg = message or f"Add skill: {name} v{registry_entry.get('version', '0.1.0')}"
            subprocess.run(
                ["git", "-C", str(registry_dir), "commit", "-m", commit_msg],
                capture_output=True,
                timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            console.print(
                f"[yellow]Commit warning: {e.stderr.decode() if e.stderr else e}[/yellow]"
            )

        # ── Push + Create PR ──
        console.print("[bold]Step 5/5:[/bold] Pushing and creating PR...")

        branch_name = f"add-{name}-{uuid.uuid4().hex[:8]}"

        try:
            # 创建新分支
            subprocess.run(
                ["git", "-C", str(registry_dir), "checkout", "-b", branch_name],
                capture_output=True,
                timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError:
            console.print("[red]Failed to create branch.[/red]")
            return publish_dir

        if gh_available:
            # 使用 gh CLI 创建 PR
            try:
                pr_body = (
                    message
                    or f"## Description\n\nAdd **{name}** ({registry_entry.get('version', '0.1.0')}) to the community skill registry.\n\n"  # noqa: E501
                )
                pr_body += "### Skill Info\n"
                pr_body += f"- **Name**: {name}\n"
                pr_body += f"- **Description**: {registry_entry.get('description', 'N/A')}\n"
                pr_body += f"- **Author**: {registry_entry.get('author', 'unknown')}\n"
                pr_body += f"- **Tags**: {', '.join(registry_entry.get('tags', []))}\n"
                pr_body += "\n### Files\n"
                for f in sorted(publish_dir.rglob("*")):
                    if f.is_file():
                        pr_body += f"- {f.relative_to(publish_dir)}\n"

                # Push to fork
                push_result = subprocess.run(
                    ["git", "-C", str(registry_dir), "push", "origin", branch_name],
                    capture_output=True,
                    timeout=60,
                )
                if push_result.returncode != 0:
                    stderr = push_result.stderr.decode() if push_result.stderr else ""
                    console.print(
                        f"[yellow]Push to origin failed (may need fork): {stderr[:200]}[/yellow]"
                    )
                    console.print("[dim]Attempting to create PR from local branch...[/dim]")

                # Create PR
                pr_result = subprocess.run(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--repo",
                        registry_repo,
                        "--head",
                        branch_name,
                        "--title",
                        f"Add skill: {name} v{registry_entry.get('version', '0.1.0')}",
                        "--body",
                        pr_body,
                    ],
                    capture_output=True,
                    timeout=30,
                    cwd=str(registry_dir),
                )

                if pr_result.returncode == 0:
                    pr_url = pr_result.stdout.decode().strip()
                    console.print(f"[green][OK] PR created: {pr_url}[/green]")
                else:
                    stderr = pr_result.stderr.decode() if pr_result.stderr else ""
                    console.print(f"[red]Failed to create PR: {stderr}[/red]")
                    _print_manual_pr_instructions(registry_dir, branch_name, registry_repo)

            except Exception as e:
                console.print(f"[red]Error during PR creation: {e}[/red]")
                _print_manual_pr_instructions(registry_dir, branch_name, registry_repo)
        else:
            # 无 gh CLI，给出手动指引
            _print_manual_pr_instructions(registry_dir, branch_name, registry_repo)

    return publish_dir


def _print_manual_pr_instructions(registry_dir: Path, branch_name: str, repo_url: str) -> None:
    """打印手动创建 PR 的指引。"""
    console.print("\n[yellow]Manual PR required:[/yellow]")
    console.print(f"  1. cd {registry_dir}")
    console.print(f"  2. git push origin {branch_name}")
    console.print(f"  3. Visit: {repo_url}/compare/main...{branch_name}")
    console.print("  4. Create a Pull Request\n")


def _check_gh_cli() -> bool:
    """检查 gh CLI 是否可用。"""
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_git() -> bool:
    """检查 git 是否可用。"""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def validate_registry_entry(entry: dict) -> list[str]:
    """校验 Registry 条目的完整性和格式。

    Args:
        entry: Registry 条目字典。

    Returns:
        问题列表，空列表表示通过。
    """
    issues = []

    # 必填字段
    required_fields = ["name", "version", "description", "author", "tags"]
    for field in required_fields:
        if not entry.get(field):
            issues.append(f"缺少必填字段: '{field}'")

    # name 格式：kebab-case
    name = entry.get("name", "")
    if name and not all(c.isalnum() or c == "-" for c in name):
        issues.append(f"name '{name}' 必须为 kebab-case（仅小写字母、数字、连字符）")

    # version 格式：语义化版本
    version = entry.get("version", "")
    if version:
        parts = version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            issues.append(f"version '{version}' 必须是语义化版本 (如 1.0.0)")

    # tags 至少一个
    tags = entry.get("tags", [])
    if isinstance(tags, list) and len(tags) == 0:
        issues.append("tags 不能为空")

    # source 格式（如果有）：URL
    source = entry.get("source", "")
    if source and not (source.startswith("https://") or source.startswith("git@")):
        issues.append(f"source '{source}' 必须是 HTTPS 或 git URL")

    return issues


def list_registry_skills() -> list[RegistryEntry]:
    """列出 registry 中所有可用的 Skill。"""
    return load_registry_index()
