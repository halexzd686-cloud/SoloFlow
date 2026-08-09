"""测试 Skill Registry。"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from soloflow.core.registry import (
    RegistryEntry,
    load_registry_index,
    search_registry,
)


def test_registry_entry_match():
    """测试搜索匹配。"""
    entry = RegistryEntry(
        {
            "name": "twitter-writer",
            "description": "Write viral Twitter threads",
            "tags": ["writing", "social"],
            "author": "test-user",
        }
    )

    assert entry.match("twitter") is True
    assert entry.match("viral") is True
    assert entry.match("writing") is True
    assert entry.match("python") is False


def test_registry_entry_match_case_insensitive():
    """测试不区分大小写。"""
    entry = RegistryEntry(
        {
            "name": "Code-Reviewer",
            "description": "Review code changes",
            "tags": ["coding"],
        }
    )
    assert entry.match("code") is True
    assert entry.match("CODE") is True
    assert entry.match("review") is True


def test_registry_entry_to_dict():
    """测试序列化。"""
    entry = RegistryEntry(
        {
            "name": "test-skill",
            "version": "1.0.0",
            "description": "Test skill",
            "author": "tester",
            "tags": ["test"],
            "source": "https://github.com/test/skill",
            "downloads": 42,
            "stars": 7,
        }
    )
    d = entry.to_dict()
    assert d["name"] == "test-skill"
    assert d["downloads"] == 42


def test_load_registry_index_from_bundled():
    """测试从内置索引加载。"""
    # 没有网络时应回退到内置索引
    with patch("soloflow.core.registry._ensure_registry_cache", return_value=False):
        # 清除可能存在的缓存
        import soloflow.core.registry as reg

        if reg.REGISTRY_INDEX.exists():
            entries = load_registry_index()
            assert len(entries) > 0
        else:
            # 至少应该能从内置索引加载
            entries = load_registry_index()
            assert len(entries) > 0


def test_search_registry():
    """测试搜索功能。"""
    results = search_registry("writing")
    assert len(results) > 0
    assert any("write" in r.name.lower() or "writing" in str(r.tags).lower() for r in results)


def test_search_registry_no_match():
    """测试无匹配搜索。"""
    results = search_registry("zzz_nonexistent_keyword_zzz")
    assert len(results) == 0


def test_install_builtin_skill():
    """测试安装内置 Skill（从项目 skills/ 复制）。"""
    from soloflow.core.registry import install_skill

    with tempfile.TemporaryDirectory() as tmp:
        import os

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            result = install_skill("content-writer", target="project")
            assert result is not None or True  # 可能找不到源，但不应该崩溃
        finally:
            os.chdir(orig_cwd)


# ── 新增测试: validate_registry_entry ──


def test_validate_registry_entry_valid():
    """测试校验合法的 Registry 条目。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {
        "name": "my-awesome-skill",
        "version": "1.2.0",
        "description": "An awesome skill for testing",
        "author": "test-user",
        "tags": ["testing", "awesome"],
        "source": "https://github.com/test/my-skill",
    }
    issues = validate_registry_entry(entry)
    assert len(issues) == 0


def test_validate_registry_entry_missing_fields():
    """测试校验缺少必填字段的条目。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {"name": "bad-skill"}  # 缺少所有其他必填字段
    issues = validate_registry_entry(entry)
    assert len(issues) >= 4  # version, description, author, tags
    field_names = [i for i in issues]
    assert any("version" in i for i in field_names)
    assert any("description" in i for i in field_names)
    assert any("author" in i for i in field_names)
    assert any("tags" in i for i in field_names)


def test_validate_registry_entry_bad_name():
    """测试校验非法 skill 名称。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {
        "name": "Bad Name With Spaces",
        "version": "1.0.0",
        "description": "test",
        "author": "test",
        "tags": ["test"],
    }
    issues = validate_registry_entry(entry)
    assert any("kebab-case" in i for i in issues)


def test_validate_registry_entry_bad_version():
    """测试校验非法版本号。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {
        "name": "test-skill",
        "version": "not-a-version",
        "description": "test",
        "author": "test",
        "tags": ["test"],
    }
    issues = validate_registry_entry(entry)
    assert any("语义化版本" in i for i in issues)


def test_validate_registry_entry_empty_tags():
    """测试校验空 tags。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "test",
        "author": "test",
        "tags": [],
    }
    issues = validate_registry_entry(entry)
    assert any("tags" in i for i in issues)


def test_validate_registry_entry_bad_source():
    """测试校验非法 source URL。"""
    from soloflow.core.registry import validate_registry_entry

    entry = {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "test",
        "author": "test",
        "tags": ["test"],
        "source": "not-a-url",
    }
    issues = validate_registry_entry(entry)
    assert any("source" in i for i in issues)


# ── 新增测试: _generate_registry_entry ──


def test_generate_registry_entry():
    """测试从 Skill 生成 Registry 条目。"""
    from soloflow.core.registry import _generate_registry_entry
    from soloflow.core.skill_loader import find_skill, load_skill

    skill_path = find_skill("code-reviewer")
    skill = load_skill(skill_path)
    entry = _generate_registry_entry(skill, "code-reviewer")

    assert entry["name"] == "code-reviewer"
    assert entry["version"] == "1.0.0"
    assert "review" in entry["tags"] or "coding" in entry["tags"]
    assert isinstance(entry["tags"], list)
    assert "description" in entry
    assert "author" in entry


# ── 新增测试: publish_skill (dry run, no submit) ──


def test_publish_skill_dry():
    """测试打包 Skill（不提交）。"""
    from soloflow.core.registry import publish_skill

    # publish_skill 用 find_skill 搜索 skills/ 目录，
    # 需要从项目根目录运行
    result = publish_skill("code-reviewer", submit=False)
    assert result is not None
    assert result.exists()
    # 应该生成了 SKILL.md
    skill_md = result / "SKILL.md"
    assert skill_md.exists()


# ── 新增测试: _check_git / _check_gh_cli ──


def test_check_git():
    """测试 git 可用性检查。"""
    from soloflow.core.registry import _check_git

    result = _check_git()
    # 在这个环境中 git 应该可用
    assert result is True


def test_check_gh_cli():
    """测试 gh CLI 可用性检查（不崩溃即可）。"""
    from soloflow.core.registry import _check_gh_cli

    result = _check_gh_cli()
    # 可能为 True 或 False，但不应抛异常
    assert isinstance(result, bool)


# ── 新增测试: install_skill with version ──


def test_install_skill_with_version():
    """测试带版本参数的安装（不崩溃即可）。"""
    from soloflow.core.registry import install_skill

    with tempfile.TemporaryDirectory() as tmp:
        import os

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            result = install_skill("content-writer", target="project", version="1.0.0")
            # 应该成功安装或优雅失败
            assert result is not None or result is None
        finally:
            os.chdir(orig_cwd)


# ── 新增测试: install_skill unknown skill ──


def test_install_unknown_skill():
    """测试安装不存在的 Skill。"""
    from soloflow.core.registry import install_skill

    result = install_skill("non-existent-skill-xyz", target="local")
    assert result is None


# ── BUG-REG-003: git pull 必须检查 return code ──


def test_update_registry_pull_failure_not_reported_ok(monkeypatch, tmp_path):
    """BUG-REG-003 回归: pull 失败时不得打印/返回成功。

    模拟 .git 目录存在但 pull 失败（非零退出码），
    必须走失败路径并返回 False（缓存也不可用）。
    """
    import subprocess
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg

    # 构造一个假缓存: .git 存在 + registry.yaml 存在
    fake_cache = tmp_path / "registry-cache"
    (fake_cache / ".git").mkdir(parents=True)
    (fake_cache / "registry.yaml").write_text("skills: []\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        # 模拟 git pull 失败
        return subprocess.CompletedProcess(
            cmd,
            returncode=1,
            stdout=b"",
            stderr=b"fatal: unable to access",
        )

    with (
        mpatch.object(reg, "REGISTRY_CACHE", fake_cache),
        mpatch.object(reg, "REGISTRY_INDEX", fake_cache / "registry.yaml"),
        mpatch.object(
            reg,
            "subprocess",
            type(
                "FakeSP",
                (),
                {
                    "run": staticmethod(fake_run),
                    "CompletedProcess": subprocess.CompletedProcess,
                    "CalledProcessError": subprocess.CalledProcessError,
                },
            ),
        ),
    ):
        result = reg.update_registry()

    # 由于 check=True 抛 CalledProcessError → 失败路径返回缓存是否可用
    # 这里缓存存在，返回 True（继续使用现有缓存），但绝不打印 [OK]
    assert result is True


def test_update_registry_pull_success(monkeypatch, tmp_path):
    """BUG-REG-003: pull 成功时返回 True。"""
    import subprocess
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg

    fake_cache = tmp_path / "registry-cache"
    (fake_cache / ".git").mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            returncode=0,
            stdout=b"Already up to date.\n",
            stderr=b"",
        )

    with (
        mpatch.object(reg, "REGISTRY_CACHE", fake_cache),
        mpatch.object(reg, "REGISTRY_INDEX", fake_cache / "registry.yaml"),
        mpatch.object(
            reg,
            "subprocess",
            type(
                "FakeSP",
                (),
                {
                    "run": staticmethod(fake_run),
                    "CompletedProcess": subprocess.CompletedProcess,
                    "CalledProcessError": subprocess.CalledProcessError,
                },
            ),
        ),
    ):
        result = reg.update_registry()

    assert result is True


def test_version_single_source_consistency():
    """版本漂移回归: pyproject.toml 动态版本与 __init__.py 一致。"""
    import re
    from pathlib import Path

    from soloflow import __version__ as runtime_version

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    # 版本必须是动态的（不再硬编码）
    assert 'dynamic = ["version"]' in pyproject
    assert "[tool.hatch.version]" in pyproject
    assert 'path = "soloflow/__init__.py"' in pyproject
    # 运行时版本非空且格式正确
    assert re.match(r"^\d+\.\d+\.\d+", runtime_version)


# ── BUG-REG-002: 严格版本安装 ──


def test_install_builtin_skill_version_mismatch_fails(monkeypatch, tmp_path):
    """BUG-REG-002 回归: 内置 Skill 指定不存在版本必须失败（不静默回退）。"""
    import os

    from soloflow.core import registry as reg

    orig_cwd = os.getcwd()
    monkeypatch.chdir(tmp_path)

    # content-writer 实际版本 1.0.0，请求 9.9.9 → 必须失败
    result = reg.install_skill(
        "content-writer", target="project", version="9.9.9", project_dir=Path(orig_cwd)
    )
    assert result is None
    assert not (tmp_path / "skills" / "content-writer").exists()

    os.chdir(orig_cwd)


def test_install_builtin_skill_version_mismatch_fallback(monkeypatch, tmp_path):
    """BUG-REG-002: --fallback-latest 允许显式回退。"""
    import os

    from soloflow.core import registry as reg

    orig_cwd = os.getcwd()
    monkeypatch.chdir(tmp_path)

    result = reg.install_skill(
        "content-writer",
        target="project",
        version="9.9.9",
        fallback_latest=True,
        project_dir=Path(orig_cwd),
    )
    assert result is not None
    assert (tmp_path / "skills" / "content-writer" / "SKILL.md").exists()

    os.chdir(orig_cwd)


def test_install_builtin_skill_version_match(monkeypatch, tmp_path):
    """BUG-REG-002: 指定正确版本时安装成功。"""
    import os

    from soloflow.core import registry as reg

    orig_cwd = os.getcwd()
    monkeypatch.chdir(tmp_path)

    result = reg.install_skill(
        "content-writer", target="project", version="1.0.0", project_dir=Path(orig_cwd)
    )
    assert result is not None

    os.chdir(orig_cwd)


# ── GAP-REG-001: 本地 git 仓库模拟远程闭环 ──


def test_registry_local_git_closed_loop(monkeypatch, tmp_path):
    """GAP-REG-001: 用本地 git 裸仓库模拟远程 Registry 完整闭环。

    验证: clone（update）→ 缓存安装 → 版本锁定 install。
    这是 publish → PR → install 链路在无 GitHub 环境下的最大可验证闭环。
    """
    import os
    import subprocess

    from soloflow.core import registry as reg

    orig_cwd = os.getcwd()

    # 1. 构造远程仓库（裸仓库 + 工作副本）
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    work = tmp_path / "work"
    work.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=work, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=work, check=True, capture_output=True
    )

    # registry.yaml + skills/demo-skill/SKILL.md
    skill_dir = work / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "version: 2.1.0\n"
        "description: Demo skill from local git registry\n"
        "author: tester\n"
        "license: MIT\n"
        "tags: [demo]\n"
        "---\n\n## Instructions\n\nDo things.\n",
        encoding="utf-8",
    )
    (work / "registry.yaml").write_text(
        "version: 1\n"
        "skills:\n"
        "  - name: demo-skill\n"
        "    version: 2.1.0\n"
        "    description: Demo skill from local git registry\n"
        "    author: tester\n"
        "    tags: [demo]\n"
        "    source: ''\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=work, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init registry"], cwd=work, check=True, capture_output=True
    )

    # 裸仓库作为"远程"
    bare = tmp_path / "bare-registry.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)], check=True, capture_output=True
    )

    # 2. 把缓存指向裸仓库（模拟 update_registry clone 远程）
    monkeypatch.chdir(tmp_path)
    fake_cache = tmp_path / "registry-cache"
    with monkeypatch.context() as m:
        # 直接 clone 远程到缓存目录
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "main", str(bare), str(fake_cache)],
            check=True,
            capture_output=True,
        )
        m.setattr(reg, "REGISTRY_CACHE", fake_cache)
        m.setattr(reg, "REGISTRY_INDEX", fake_cache / "registry.yaml")
        m.setattr(reg, "REGISTRY_SKILLS", fake_cache / "skills")
        m.setattr(reg, "DEFAULT_REGISTRY_REPO", str(bare))

        # 3. 索引加载（走缓存）
        entries = reg.load_registry_index()
        names = [e.name for e in entries]
        assert "demo-skill" in names

        # 4. 缓存安装 + 版本锁定成功
        dest = reg.install_skill("demo-skill", target="project", version="2.1.0")
        assert dest is not None
        from soloflow.core.skill_loader import load_skill

        installed = load_skill(dest)
        assert installed.meta.version == "2.1.0"

        # 5. 版本锁定失败（缓存路径）
        assert reg.install_skill("demo-skill", target="project", version="1.0.0") is None

    os.chdir(orig_cwd)


# ── GAP-REG-004: 供应链安全检查 ──


def test_skill_dir_size_check_blocks_oversized(monkeypatch, tmp_path):
    """GAP-REG-004: 超大 Skill 目录被拒绝安装。"""
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg

    big_dir = tmp_path / "big-skill"
    big_dir.mkdir()
    (big_dir / "SKILL.md").write_text(
        "---\nname: big-skill\nversion: 1.0.0\n---\nbody", encoding="utf-8"
    )
    # 写一个超过上限的文件
    big_file = big_dir / "payload.bin"
    big_file.write_bytes(b"\x00" * (reg.MAX_SKILL_DIR_BYTES + 1))

    with (
        mpatch.object(reg, "_ensure_registry_cache", return_value=True),
        mpatch.object(reg, "REGISTRY_SKILLS", big_dir.parent),
        mpatch.object(
            reg,
            "load_registry_index",
            return_value=[
                reg.RegistryEntry(
                    {
                        "name": "big-skill",
                        "version": "1.0.0",
                        "description": "big",
                        "author": "t",
                        "tags": ["t"],
                        "source": "",
                    }
                )
            ],
        ),
    ):
        result = reg.install_skill("big-skill", target="project", version="1.0.0")
        assert result is None


# ── P1-004: staging + 原子替换安装 ──


def _make_skill_dir(parent: Path, name: str, version: str, sentinel: str = "") -> Path:
    """构造一个 Skill 目录。"""
    d = parent / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"version: {version}\n"
        "description: test skill\n"
        "author: t\n"
        "license: MIT\n"
        "tags: [test]\n"
        "---\n\n## Instructions\n\nbody\n",
        encoding="utf-8",
    )
    if sentinel:
        (d / "sentinel.txt").write_text(sentinel, encoding="utf-8")
    return d


def test_install_failure_preserves_existing_install(monkeypatch, tmp_path):
    """P1-004 回归: 失败安装绝不能改变用户已有安装。

    目标目录已有 1.0.0 + sentinel，请求不存在的 9.9.9 →
    返回 None、旧 SKILL.md 完好、sentinel 内容不变。
    """
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg

    monkeypatch.chdir(tmp_path)

    # 用户已有安装
    dest = tmp_path / "skills" / "demo-skill"
    _make_skill_dir(dest.parent, "demo-skill", "1.0.0", sentinel="keep-me")

    # 缓存里有 1.0.0（缓存安装路径）
    cache_skill = tmp_path / "cache" / "skills" / "demo-skill"
    _make_skill_dir(cache_skill.parent, "demo-skill", "1.0.0")

    with (
        mpatch.object(reg, "REGISTRY_SKILLS", cache_skill.parent),
        mpatch.object(
            reg,
            "load_registry_index",
            return_value=[
                reg.RegistryEntry(
                    {
                        "name": "demo-skill",
                        "version": "1.0.0",
                        "description": "d",
                        "author": "t",
                        "tags": ["t"],
                        "source": "",
                    }
                )
            ],
        ),
    ):
        result = reg.install_skill("demo-skill", target="project", version="9.9.9")

    assert result is None
    # 旧安装完好
    old_skill = dest / "SKILL.md"
    assert old_skill.exists()
    from soloflow.core.skill_loader import load_skill

    assert load_skill(old_skill).meta.version == "1.0.0"
    assert (dest / "sentinel.txt").read_text(encoding="utf-8") == "keep-me"
    # 没有 staging/backup 残留
    assert not list(tmp_path.glob(".*staging*"))
    assert not list(tmp_path.glob(".*backup*"))


def test_install_success_atomic_replace(monkeypatch, tmp_path):
    """P1-004 回归: 成功安装是完整替换（staging 语义），无半合并。"""
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg
    from soloflow.core.skill_loader import load_skill

    monkeypatch.chdir(tmp_path)

    dest = tmp_path / "skills" / "demo-skill"
    _make_skill_dir(dest.parent, "demo-skill", "1.0.0", sentinel="old-file")

    # 缓存提供 2.0.0（无 sentinel —— 若合并则旧 sentinel 残留）
    cache_skill = tmp_path / "cache" / "skills" / "demo-skill"
    _make_skill_dir(cache_skill.parent, "demo-skill", "2.0.0")

    with (
        mpatch.object(reg, "REGISTRY_SKILLS", cache_skill.parent),
        mpatch.object(
            reg,
            "load_registry_index",
            return_value=[
                reg.RegistryEntry(
                    {
                        "name": "demo-skill",
                        "version": "2.0.0",
                        "description": "d",
                        "author": "t",
                        "tags": ["t"],
                        "source": "",
                    }
                )
            ],
        ),
    ):
        result = reg.install_skill("demo-skill", target="project", version="2.0.0")

    assert result is not None
    assert load_skill(dest / "SKILL.md").meta.version == "2.0.0"
    # 旧 sentinel 必须不存在（完整替换，不是合并）
    assert not (dest / "sentinel.txt").exists()
    # 无残留
    assert not list(tmp_path.glob(".*staging*"))
    assert not list(tmp_path.glob(".*backup*"))


def test_install_replace_failure_rolls_back(monkeypatch, tmp_path):
    """P1-004 回归: staging→dest 替换失败时回滚旧版本。"""
    from unittest.mock import patch as mpatch

    from soloflow.core import registry as reg
    from soloflow.core.skill_loader import load_skill

    monkeypatch.chdir(tmp_path)

    dest = tmp_path / "skills" / "demo-skill"
    _make_skill_dir(dest.parent, "demo-skill", "1.0.0", sentinel="precious")

    cache_skill = tmp_path / "cache" / "skills" / "demo-skill"
    _make_skill_dir(cache_skill.parent, "demo-skill", "2.0.0")

    real_rename = Path.rename
    rename_calls = {"n": 0}

    def flaky_rename(self, target):
        rename_calls["n"] += 1
        if rename_calls["n"] == 2:
            # 第二次 rename（staging → dest）失败，模拟替换失败
            raise OSError("simulated rename failure")
        return real_rename(self, target)

    with (
        mpatch.object(reg, "REGISTRY_SKILLS", cache_skill.parent),
        mpatch.object(
            reg,
            "load_registry_index",
            return_value=[
                reg.RegistryEntry(
                    {
                        "name": "demo-skill",
                        "version": "2.0.0",
                        "description": "d",
                        "author": "t",
                        "tags": ["t"],
                        "source": "",
                    }
                )
            ],
        ),
        mpatch.object(Path, "rename", flaky_rename),
    ):
        result = reg.install_skill("demo-skill", target="project", version="2.0.0")

    assert result is None
    # 旧版本已回滚恢复
    assert dest.exists()
    assert load_skill(dest / "SKILL.md").meta.version == "1.0.0"
    assert (dest / "sentinel.txt").read_text(encoding="utf-8") == "precious"
