"""Wabi-Sabi 侘寂风主题 —— 暖灰底 + 细线框 + 克制配色。

Textual CSS 中通过 Python 变量注入颜色值，避免 CSS 自定义属性兼容问题。
"""

# ── 基础色板 ──
C = {
    "bg": "#F7F4EF",
    "surface": "#EFECE7",
    "surface_hover": "#E8E4DE",
    "border": "#C4B5A5",
    "border_focus": "#A0886E",
    "text": "#4A4A4A",
    "text_dim": "#8C8C8C",
    "text_muted": "#B0A89E",
    "accent": "#8B4513",
    "success": "#9CAF88",
    "warning": "#D4A853",
    "error": "#C45A3C",
    "divider": "#E0DBD3",
    "highlight": "#F0EBE3",
}


def build_css() -> str:
    """构建侘寂风主题 CSS 字符串。"""
    return f"""
    Screen {{
        background: {C["bg"]};
        color: {C["text"]};
    }}

    .wabi-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 2;
    }}

    .wabi-label {{
        color: {C["text_dim"]};
        text-style: italic;
        padding: 0 1;
    }}

    .wabi-card {{
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
        margin: 0 1;
    }}

    .wabi-divider-h {{
        background: {C["divider"]};
        height: 1;
    }}

    .wabi-status-done {{
        color: {C["success"]};
    }}

    .wabi-status-running {{
        color: {C["warning"]};
        text-style: bold;
    }}

    .wabi-status-pending {{
        color: {C["text_muted"]};
    }}

    .wabi-status-failed {{
        color: {C["error"]};
    }}

    .wabi-nav-key {{
        color: {C["accent"]};
        text-style: bold;
    }}

    .wabi-badge-new {{
        color: {C["accent"]};
        text-style: italic;
    }}

    .wabi-metric {{
        color: {C["accent"]};
        text-style: bold;
    }}

    .wabi-metric-label {{
        color: {C["text_dim"]};
    }}
    """
