"""CLI 输出编码兼容处理。"""

import os
import sys


def configure_output_encoding() -> None:
    """Use UTF-8 for Windows CLI streams when the runtime supports reconfigure."""
    if os.name != "nt":
        return

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # Some redirected or embedded streams reject runtime reconfiguration.
            continue
