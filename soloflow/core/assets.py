"""Bundled and project asset discovery helpers.

The repository keeps one authoritative copy of the example assets in the
top-level ``skills/``, ``agents/`` and ``flows/`` directories. Hatch maps
those directories into ``soloflow/_bundled`` when building a wheel.
"""

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_BUNDLED_ROOT = _PACKAGE_ROOT / "_bundled"
_ASSET_KINDS = frozenset({"skills", "agents", "flows"})


def bundled_asset_dir(kind: str) -> Path:
    """Return the installed package directory for a bundled asset kind."""
    if kind not in _ASSET_KINDS:
        raise ValueError(f"Unknown asset kind: {kind}")
    return _BUNDLED_ROOT / kind


def find_flow_path(name_or_path: str | Path, project_dir: str | Path | None = None) -> Path:
    """Resolve a Flow path from an explicit path, project assets, or bundled assets."""
    direct = Path(name_or_path)
    if direct.is_file():
        return direct

    name = direct.name
    if not name.endswith((".flow.yml", ".flow.yaml")):
        name = f"{name}.flow.yml"

    project_root = Path(project_dir) if project_dir is not None else Path.cwd()
    for directory in (project_root / "flows", bundled_asset_dir("flows")):
        candidate = directory / name
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(f"Flow not found: {name_or_path}")


def list_flow_paths(project_dir: str | Path | None = None) -> list[Path]:
    """List project and bundled Flows, preferring project overrides by name."""
    project_root = Path(project_dir) if project_dir is not None else Path.cwd()
    directories = (project_root / "flows", bundled_asset_dir("flows"))
    results: list[Path] = []
    seen: set[str] = set()

    for directory in directories:
        if not directory.is_dir():
            continue
        files = sorted(directory.glob("*.flow.yml")) + sorted(directory.glob("*.flow.yaml"))
        for path in files:
            name = path.name.removesuffix(".flow.yml").removesuffix(".flow.yaml")
            if name in seen:
                continue
            seen.add(name)
            results.append(path)

    return results
