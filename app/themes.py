"""
Hermit Crab Theme System
5 dark themes with full color palette for the terminal-style UI.
"""

THEMES = {
    "default": {
        "label": "经典暗色",
        "bg": "#0d0d0d", "fg": "#c0c0c0",
        "green": "#4ade80", "yellow": "#e8c84a",
        "prompt": "#8888ff", "user": "#66ccff",
        "agent": "#c0c0c0", "error": "#ff6666",
        "dim": "#555555", "label": "#888888",
        "input_bg": "#111111", "input_fg": "#e0e0e0",
        "border": "#222222", "status_ok": "#4ade80", "status_err": "#ff6666",
        "code_fg": "#c8d8e8", "code_sign": "#444476",
        "user_bubble": "#1a1a2e", "search_bg": "#1e1e2e",
        "search_highlight": "#888840",
        "thinking_label": "#8888ff", "thinking_content": "#666688",
        "thinking_sep": "#444466", "timestamp": "#333344",
        "status_bar_bg": "#0a0a0a", "status_bar_line": "#1a1a1a",
    },
    "ocean": {
        "label": "深海蓝",
        "bg": "#0a0e1a", "fg": "#b0c4de",
        "green": "#5cede8", "yellow": "#e8c84a",
        "prompt": "#7eb8ff", "user": "#5bb8ff",
        "agent": "#b0c4de", "error": "#ff6b6b",
        "dim": "#4a5a7a", "label": "#6a8aaa",
        "input_bg": "#0e1525", "input_fg": "#c8d8e8",
        "border": "#1a2a40", "status_ok": "#5cede8", "status_err": "#ff6b6b",
        "code_fg": "#88b8d8", "code_sign": "#3a5a7a",
        "user_bubble": "#0e1a2e", "search_bg": "#121a2e",
        "search_highlight": "#3a6a8a",
        "thinking_label": "#7eb8ff", "thinking_content": "#5a7a9a",
        "thinking_sep": "#3a4a6a", "timestamp": "#2a3a5a",
        "status_bar_bg": "#080c18", "status_bar_line": "#121a2e",
    },
    "twilight": {
        "label": "暮光紫",
        "bg": "#120d1a", "fg": "#c8b8d8",
        "green": "#b8a0e8", "yellow": "#e8c84a",
        "prompt": "#b088ff", "user": "#a080e0",
        "agent": "#c8b8d8", "error": "#ff6b9a",
        "dim": "#5a4a6a", "label": "#7a6a8a",
        "input_bg": "#18102a", "input_fg": "#d0c0e8",
        "border": "#2a1a40", "status_ok": "#b8a0e8", "status_err": "#ff6b9a",
        "code_fg": "#a890c8", "code_sign": "#4a3a5a",
        "user_bubble": "#1a122e", "search_bg": "#1a122e",
        "search_highlight": "#5a4a7a",
        "thinking_label": "#b088ff", "thinking_content": "#6a5a8a",
        "thinking_sep": "#4a3a5a", "timestamp": "#3a2a4a",
        "status_bar_bg": "#0e0818", "status_bar_line": "#1a122e",
    },
    "forest": {
        "label": "森林绿",
        "bg": "#0d1a10", "fg": "#b0c8a8",
        "green": "#6ae85a", "yellow": "#c8c84a",
        "prompt": "#88cc88", "user": "#66cc88",
        "agent": "#b0c8a8", "error": "#ff8866",
        "dim": "#4a6a4a", "label": "#6a8a6a",
        "input_bg": "#0f1e12", "input_fg": "#c0d8b8",
        "border": "#1a2e1a", "status_ok": "#6ae85a", "status_err": "#ff8866",
        "code_fg": "#a0c898", "code_sign": "#3a5a3a",
        "user_bubble": "#0e1e12", "search_bg": "#0e1e12",
        "search_highlight": "#4a6a3a",
        "thinking_label": "#88cc88", "thinking_content": "#5a7a52",
        "thinking_sep": "#3a4a32", "timestamp": "#2a3a2a",
        "status_bar_bg": "#0a140c", "status_bar_line": "#122016",
    },
    "warm": {
        "label": "暖阳橙",
        "bg": "#1a140d", "fg": "#d0c0a8",
        "green": "#e8b84a", "yellow": "#e8d04a",
        "prompt": "#d4a060", "user": "#e0b060",
        "agent": "#d0c0a8", "error": "#ff6644",
        "dim": "#6a5a4a", "label": "#8a7a5a",
        "input_bg": "#221a10", "input_fg": "#e0d0b8",
        "border": "#3a2a1a", "status_ok": "#e8b84a", "status_err": "#ff6644",
        "code_fg": "#c8b090", "code_sign": "#5a4a3a",
        "user_bubble": "#221810", "search_bg": "#1e1810",
        "search_highlight": "#7a6a3a",
        "thinking_label": "#d4a060", "thinking_content": "#7a6a52",
        "thinking_sep": "#4a3a2a", "timestamp": "#3a2a1a",
        "status_bar_bg": "#141008", "status_bar_line": "#221810",
    },
}

# Color constants
COLOR_BG = "#0d0d0d"
COLOR_FG = "#c0c0c0"
COLOR_GREEN = "#4ade80"
COLOR_YELLOW = "#e8c84a"
COLOR_PROMPT = "#8888ff"
COLOR_USER = "#66ccff"
COLOR_AGENT = "#c0c0c0"
COLOR_ERROR = "#ff6666"
COLOR_DIM = "#555555"
COLOR_LABEL = "#888888"
COLOR_INPUT_BG = "#111111"
COLOR_INPUT_FG = "#e0e0e0"
COLOR_BORDER = "#222222"
COLOR_STATUS_OK = "#4ade80"
COLOR_STATUS_ERR = "#ff6666"
COLOR_CODE_BG_FG = "#c8d8e8"
COLOR_CODE_SIGN = "#444476"
COLOR_USER_BUBBLE = "#1a1a2e"
COLOR_SEARCH_BG = "#1e1e2e"
COLOR_SEARCH_HIGHLIGHT = "#888840"

# Font constants
FONT = ("Consolas", 12)
FONT_BOLD = ("Consolas", 12, "bold")
FONT_SMALL = ("Consolas", 10)
FONT_LOGO = ("Consolas", 10)
