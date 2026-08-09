"""SoloFlow 本地配置加载。"""

from pathlib import Path

from dotenv import load_dotenv


def load_project_env(project_dir: Path | None = None) -> bool:
    """加载当前项目根目录的 ``.env``，且不覆盖已有环境变量。

    仅检查明确指定的目录（默认当前工作目录），不向父目录递归搜索，
    避免无意加载其他项目的凭据。
    """
    env_path = (project_dir or Path.cwd()) / ".env"
    return load_dotenv(dotenv_path=env_path, override=False)
