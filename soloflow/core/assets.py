"""Unified discovery for project, user, and bundled assets."""

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_BUNDLED_ROOT = _PACKAGE_ROOT / "_bundled"
_ASSET_KINDS = frozenset({"skill", "agent", "flow"})
_KIND_ALIASES = {"playbook": "skill", "playbooks": "skill", "skills": "skill"}


def _check_kind(kind: str) -> str:
    normalized = _KIND_ALIASES.get(kind, kind.removesuffix("s"))
    if normalized not in _ASSET_KINDS:
        raise ValueError(f"Unknown asset kind: {kind}")
    return normalized


def bundled_asset_dir(kind: str) -> Path:
    """Return the installed directory for one bundled asset kind."""
    normalized = _check_kind(kind)
    return _BUNDLED_ROOT / f"{normalized}s"


def asset_directories(
    kind: str,
    project_dir: str | Path | None = None,
) -> list[tuple[str, Path]]:
    """Return the shared precedence order: project, user, bundled."""
    normalized = _check_kind(kind)
    project_root = Path(project_dir) if project_dir is not None else Path.cwd()
    roots = [
        ("project", project_root),
        ("user", Path.home() / ".soloflow"),
        ("bundled", _BUNDLED_ROOT),
    ]
    folders = ("playbooks", "skills") if normalized == "skill" else (f"{normalized}s",)
    return [(source, root / folder) for source, root in roots for folder in folders]


def _iter_asset_files(kind: str, directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    if kind == "skill":
        # Prefer the user-facing name when both formats exist in one directory.
        return sorted(directory.rglob("PLAYBOOK.md")) + sorted(directory.rglob("SKILL.md"))
    if kind == "flow":
        return sorted(directory.rglob("*.flow.yml")) + sorted(directory.rglob("*.flow.yaml"))
    return sorted(directory.rglob("*.agent.yml")) + sorted(directory.rglob("*.agent.yaml"))


def asset_name(kind: str, path: Path) -> str:
    """Derive the lookup name from an asset path."""
    normalized = _check_kind(kind)
    if normalized == "skill":
        return path.parent.name
    name = path.name
    return name.removesuffix(f".{normalized}.yml").removesuffix(f".{normalized}.yaml")


def find_asset(
    kind: str,
    name_or_path: str | Path,
    project_dir: str | Path | None = None,
) -> Path:
    """Find an asset by explicit path or the shared precedence order."""
    normalized = _check_kind(kind)
    direct = Path(name_or_path)
    if direct.is_file():
        return direct
    if normalized == "skill" and direct.is_dir():
        for filename in ("PLAYBOOK.md", "SKILL.md"):
            if (direct / filename).is_file():
                return direct / filename

    requested = direct.name if normalized == "skill" else asset_name(normalized, direct)
    for _source, directory in asset_directories(normalized, project_dir):
        for path in _iter_asset_files(normalized, directory):
            if asset_name(normalized, path) == requested:
                return path
    raise FileNotFoundError(f"{normalized.title()} not found: {name_or_path}")


def list_asset_paths(
    kind: str,
    project_dir: str | Path | None = None,
    *,
    include_project: bool = True,
    include_user: bool = True,
    include_bundled: bool = True,
) -> list[tuple[str, Path]]:
    """List assets once by name, preserving the shared precedence order."""
    normalized = _check_kind(kind)
    enabled = {
        "project": include_project,
        "user": include_user,
        "bundled": include_bundled,
    }
    results: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, directory in asset_directories(normalized, project_dir):
        if not enabled[source]:
            continue
        for path in _iter_asset_files(normalized, directory):
            name = asset_name(normalized, path)
            if name in seen:
                continue
            seen.add(name)
            results.append((source, path))
    return results


def find_flow_path(name_or_path: str | Path, project_dir: str | Path | None = None) -> Path:
    """Compatibility wrapper for Flow callers."""
    return find_asset("flow", name_or_path, project_dir)


def list_flow_paths(project_dir: str | Path | None = None) -> list[Path]:
    """Compatibility wrapper for Flow callers."""
    return [path for _source, path in list_asset_paths("flow", project_dir)]
