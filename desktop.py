#!/usr/bin/env python3
"""
Hermit Crab - 本地 AI 助手 (寄居蟹)
终端风格的桌面聊天程序。
"""

import tkinter as tk
from tkinter import font as tkfont
import json, os, threading, requests, re, time, subprocess, ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime
from app import providers
from app.tools import register, execute_tool, init_tools, get_openai_tools, match_tool_from_text
from app.memory import (
    MEMORY_DIR, MEMORY_INDEX, ensure_dirs, load_memories,
    save_memory, delete_memory, build_memory_text,
)
from app.themes import *
from app.win32_drop import WM_DROPFILES, WNDPROC
import permissions as _perm

# ============================================================
#  配置
# ============================================================

LLAMA_PORT = 8080
CONFIG_FILE = Path(__file__).parent / "config.json"

# ── 可选系统密钥环 ──
_has_keyring = False
try:
    import keyring
    _has_keyring = True
except ImportError:
    pass

SHRIMP_BANNER = r"""
   ╔══════════════════╗
   ║                  ║
   ║    ╭──╮ ╭──╮    ║
   ║   ╱ ◉ ╲╱ ◉ ╲   ║
   ║  │  ╭──╮  │     ║
   ║  │  ╰──╯  │     ║
   ║  ╰──╮  ╭──╯     ║
   ║     ╰──╯        ║
   ║                  ║
   ║   Hermit Crab   ║
   ║  Local Memory AI ║
   ║                  ║
   ╚══════════════════╝
"""

# ============================================================
#  终端风格桌面应用
# ============================================================


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Hermit Crab")
        self._set_window_icon()
        self.configure(bg=COLOR_BG)

        # State
        self.messages = []
        self.is_streaming = False
        self._stop_requested = False
        self.stream_text = ""
        self.memories = {}
        self.started = False
        self.llama_proc = None

        # Provider config
        self.provider = "local"
        self.openai_api_key = ""
        self.openai_base_url = ""
        self.anthropic_api_key = ""
        self.current_model = self._get_current_model_name()
        self._last_provider_validation = 0
        self.token_speed_var = tk.StringVar(value="0 t/s")
        self.context_var = tk.StringVar(value="ctx: 0/8192")
        self.stream_start_time = 0
        self.completion_tokens = 0
        self.prompt_tokens = 0
        self._last_stats_update = 0
        self.thinking_visible = True
        self.in_code_block = False
        self.search_visible = False
        self.conversation_id = self._new_conv_id()
        self.conversation_title = "新对话"
        self.last_exchange_start = None
        self.can_retry = False
        self.context_summary = ""
        self.total_tokens = 0
        self.compression_threshold = 6000
        self.system_prompt = (
            "你是 Agent，一个 helpful AI 助手。你有持久的记忆系统，"
            "能记住关于用户的信息。回答保持简洁、有帮助。"
            "使用和用户一样的语言回复。"
            "请用中文进行思考和推理，思考过程也用中文。"
            "注意：如果发现自己反复绕圈子、自我怀疑，立即停止纠结，直接输出当前的最佳答案。"
        )
        self.plan_prompt = (
            "\n\n对于需要多步操作的任务（搜索信息、分析、读取文件、总结等），"
            "请先输出一个计划。\n"
            "计划格式：\n"
            "[计划]\n"
            "1. 第一步：描述\n"
            "2. 第二步：描述\n"
            "[/计划]\n"
            "- 如果某步需要搜索实时信息，写 \"搜索：关键词\"。\n"
            "- 如果需要读取文件，写 \"读取文件：路径\"。\n"
            "用户确认后会逐步执行。"
        )

        # Knowledge base
        self.kb = None
        try:
            from app.knowledge import KnowledgeBase
            self.kb = KnowledgeBase()
        except Exception:
            pass

        # Plan & search state
        self.active_plan = None
        self.plan_frame = None
        self.search_enabled = False
        try:
            from duckduckgo_search import DDGS
            self.search_enabled = True
        except ImportError:
            pass

        # Restore window geometry & theme & provider
        self.theme_name = "default"
        cfg = {}
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            self.theme_name = cfg.get("theme", "default")
            self.provider = cfg.get("provider", "local")
            self._load_credentials(cfg)
        except:
            pass

        # First-run setup wizard (deferred: wait for main window to finish init)
        self._setup_pending = None
        if cfg.get("setup_version", 0) < 1:
            self._setup_pending = cfg
            self.after(200, self._run_setup_wizard)

        # 权限系统
        self.permissions = _perm.merge_permissions(cfg.get("permissions"))
        self.system_prompt = cfg.get("system_prompt") or self.system_prompt

        self._restore_geometry()

        self._build_ui()
        init_tools(self)
        self._load_memories()
        self._check_status()
        self._update_perm_indicator()
        # 自动启动后端
        self.after(500, self._auto_start)

        # Save geometry on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _save_config(self, updates):
        """原子地更新 config.json 中的字段（不保存凭证，走 _save_credentials）。"""
        # 过滤掉凭证字段
        safe_updates = {k: v for k, v in updates.items()
                        if k not in ("openai_api_key", "openai_base_url", "anthropic_api_key")}
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except:
            cfg = {}
        cfg.update(safe_updates)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    # ======== 权限系统 ========

    def _perm_check(self, key, label="该项操作"):
        """检查权限，被拒时显示提示并返回 False。"""
        if not _perm.check(self.permissions, key):
            self._show_lines([f"  [!] 权限被拒: {label} 未开启。请在权限设置中启用。"], "error")
            return False
        return True

    def _show_permissions_dialog(self):
        """弹出权限设置对话框。"""
        def on_save(new_perms):
            self.permissions = new_perms
            self._save_config({"permissions": new_perms})
            self._update_perm_indicator()
            self._show_lines(["  ✓ 权限设置已保存"], "dim")
        _perm.show_permission_dialog(self, self.permissions, on_save)

    def _update_perm_indicator(self):
        """更新权限按钮颜色：全开灰色，有关闭项亮色。"""
        if not hasattr(self, "perm_btn"):
            return
        all_open = all(_perm.check(self.permissions, key) for key, _, _, _ in _perm.PERMISSION_DEFS)
        self.perm_btn.configure(fg="#4a4a4a" if all_open else "#ff8844")

    # ── 密钥管理（优先系统密钥环，fallback 加密文件）──

    def _load_credentials(self, config):
        """从密钥环或凭证文件加载 API 密钥。"""
        if _has_keyring:
            try:
                self.openai_api_key = keyring.get_password("hermit-crab", "openai_api_key") or config.get("openai_api_key", "")
                self.openai_base_url = config.get("openai_base_url", "")
                self.anthropic_api_key = keyring.get_password("hermit-crab", "anthropic_api_key") or config.get("anthropic_api_key", "")
                return
            except Exception:
                pass
        # Fallback: 从专门的凭证文件读取（权限受限）
        self.openai_api_key = config.get("openai_api_key", "")
        self.openai_base_url = config.get("openai_base_url", "")
        self.anthropic_api_key = config.get("anthropic_api_key", "")

    def _save_credentials(self, updates):
        """保存密钥到系统密钥环（优先）或凭证文件。"""
        key_updates = {}
        for k in ("openai_api_key", "openai_base_url", "anthropic_api_key"):
            if k in updates:
                key_updates[k] = updates[k]
        if not key_updates:
            return
        if _has_keyring:
            try:
                for k, v in key_updates.items():
                    keyring.set_password("hermit-crab", k, v)
                return
            except Exception:
                pass
        # Fallback: 保存到 config.json（加密层）
        self._save_config(key_updates)

    # ======== Window Geometry ========

    def _save_geometry(self):
        self._save_config({"window_geometry": self.geometry()})

    def _restore_geometry(self):
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            geom = cfg.get("window_geometry")
            if geom:
                self.geometry(geom)
                return
        except:
            pass
        self.geometry("880x640")
        self.minsize(600, 400)

    def _new_conversation(self):
        """开始新对话：保存当前对话，清空消息，重置界面。"""
        if self.is_streaming:
            return
        self._save_conversation()
        self.messages = []
        self.conversation_id = self._new_conv_id()
        self.conversation_title = "新对话"
        self.started = False
        self.stream_text = ""
        self.context_summary = ""
        self.token_speed_var.set("0 t/s")
        self.context_var.set("ctx: 0/8192")
        self.completion_tokens = 0
        self.prompt_tokens = 0
        self._show_welcome()
        self.input.delete("1.0", "end")
        self.input.focus()
        self.retry_btn.configure(fg="#333333")
        self.edit_btn.configure(fg="#333333")
        self.can_retry = False

    def _retry_last(self):
        """重试：重新生成上一条 AI 回复。"""
        if self.is_streaming or len(self.messages) < 2:
            return
        if self.last_exchange_start:
            self.text.configure(state="normal")
            self.text.delete(self.last_exchange_start, "end")
            self.text.configure(state="disabled")
        self.messages.pop()
        last_user = self.messages.pop()
        self.retry_btn.configure(fg="#333333")
        self.edit_btn.configure(fg="#333333")
        self.can_retry = False
        self._send_raw(last_user["content"])

    def _edit_last(self):
        """编辑：把上一条用户消息放回输入框修改。"""
        if self.is_streaming or len(self.messages) < 2:
            return
        if self.last_exchange_start:
            self.text.configure(state="normal")
            self.text.delete(self.last_exchange_start, "end")
            self.text.configure(state="disabled")
        self.messages.pop()
        last_user = self.messages.pop()
        self.input.delete("1.0", "end")
        self.input.insert("1.0", last_user["content"])
        self.input.focus()
        self.retry_btn.configure(fg="#333333")
        self.edit_btn.configure(fg="#333333")
        self.can_retry = False

    def _rename_conversation(self, title):
        """重命名当前对话。"""
        if title:
            self.conversation_title = title
            self._save_conversation()
            self._show_lines([f"  已重命名为: {title}"], "dim")

    def _cmd_export(self):
        """导出对话为 Markdown 文件。"""
        if not self.messages:
            self._show_lines(["  没有可导出的内容"], "dim")
            return
        fp = MEMORY_DIR.parent / f"对话_{self.conversation_id}.md"
        lines = [
            f"# {self.conversation_title}",
            f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"消息数: {len(self.messages)//2}",
            "",
        ]
        for msg in self.messages:
            role = "你" if msg["role"] == "user" else "AI"
            lines.append(f"**{role}:**\n{msg['content']}\n")
        fp.write_text("\n".join(lines), encoding="utf-8")
        self._show_lines([f"  已导出: {fp.name}"], "dim")

    def _compress_context(self):
        """自动压缩早期对话历史以节省 context 空间。"""
        if len(self.messages) < 6:
            return
        compress_n = max(2, len(self.messages) // 3)
        if compress_n % 2 != 0:
            compress_n += 1
        old = self.messages[:compress_n]
        rest = self.messages[compress_n:]
        lines = [f"以下为 {compress_n//2} 轮压缩的早期对话："]
        for msg in old:
            role = "用户" if msg["role"] == "user" else "AI"
            content = msg["content"][:300]
            lines.append(f"{role}: {content}")
        summary = "\n".join(lines)
        self.context_summary = summary
        compressed = {"role": "system", "content": f"[上下文压缩 - {compress_n//2} 轮摘要]\n{summary[:1500]}"}
        self.messages = [compressed] + rest
        self._show_lines([f"  [已压缩 {compress_n//2} 轮历史对话，释放 context 空间]"], "dim")

    def _on_close(self):
        self._save_geometry()
        self._save_conversation()
        self.destroy()

    # ======== System Prompt Builder ========

    def _build_system_prompt(self, user_text):
        memories = load_memories()
        ctx = build_memory_text(memories)
        sp = self.system_prompt + self.plan_prompt
        if self.context_summary:
            sp += "\n\n[早期对话摘要]\n" + self.context_summary[:800]
        if self.kb:
            try:
                kb_ctx = self.kb.get_context(user_text)
                if kb_ctx:
                    sp += "\n\n" + kb_ctx
            except Exception:
                pass
        if ctx:
            sp += "\n\n" + ctx
        return sp

    # ======== UI ========

    def _build_ui(self):
        self._container = tk.Frame(self, bg=COLOR_BG)
        self._container.pack(fill="both", expand=True)

        title_bar = tk.Frame(self._container, bg=COLOR_BG, height=28)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        self.title_bar = title_bar

        self.status_dot = tk.Canvas(title_bar, width=10, height=10,
                                     bg=COLOR_BG, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(12, 4), pady=9)
        self.dot = self.status_dot.create_oval(2, 2, 10, 10,
                                                 fill=COLOR_STATUS_ERR, outline="")

        tk.Label(title_bar, text=" Hermit Crab  v1.6",
                 bg=COLOR_BG, fg=COLOR_DIM, font=FONT_SMALL).pack(side="left")

        prov_style = {"bg": COLOR_BG, "font": ("Consolas", 9), "cursor": "hand2", "padx": 4}
        self._prov_tabs = {}
        for p, label, color in [
            ("local", " LOCAL ", COLOR_GREEN),
            ("openai", " OPENAI ", "#4a9eff"),
            ("anthropic", " ANTHROPIC ", "#d4a574"),
        ]:
            lbl = tk.Label(title_bar, text=label, fg="#444444", **prov_style)
            lbl.pack(side="left", padx=(0, 0))
            lbl.bind("<Button-1>", lambda e, prov=p, c=color: self._ui_switch_provider(prov))
            self._prov_tabs[p] = lbl
        self._update_prov_tabs()

        self.status_text = tk.Label(title_bar, text="● 离线",
                                     bg=COLOR_BG, fg=COLOR_STATUS_ERR,
                                     font=FONT_SMALL)
        self.status_text.pack(side="right", padx=12)

        tk.Label(title_bar, text="记忆", bg=COLOR_BG, fg=COLOR_DIM,
                 font=FONT_SMALL).pack(side="right", padx=(4, 0))
        self.mem_label = tk.Label(title_bar, text="0", bg=COLOR_BG,
                                   fg=COLOR_LABEL, font=FONT_SMALL)
        self.mem_label.pack(side="right")

        sep = tk.Frame(self._container, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x")
        self.sep = sep

        chat_frame = tk.Frame(self._container, bg=COLOR_BG)
        chat_frame.pack(fill="both", expand=True)

        self.text = tk.Text(chat_frame, bg=COLOR_BG, fg=COLOR_FG,
                             font=FONT, insertbackground=COLOR_FG,
                             relief="flat", borderwidth=0,
                             padx=16, pady=8, wrap="word",
                             state="disabled", cursor="arrow")
        self.text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(chat_frame, command=self.text.yview,
                                  bg=COLOR_BG, troughcolor=COLOR_BG,
                                  activebackground=COLOR_DIM)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)

        self.text.tag_config("logo", foreground=COLOR_DIM, font=FONT_LOGO,
                              spacing1=0, spacing2=0)
        self.text.tag_config("logo_title", foreground=COLOR_LABEL,
                              font=("Consolas", 11, "bold"))
        self.text.tag_config("banner", foreground=COLOR_DIM, font=FONT_SMALL)
        self.text.tag_config("user_label", foreground=COLOR_PROMPT,
                              font=FONT_BOLD)
        self.text.tag_config("user_msg", foreground=COLOR_USER, font=FONT,
                              spacing1=4, spacing3=4, justify="right",
                              lmargin1=120, rmargin=8)
        self.text.tag_config("agent_label", foreground=COLOR_GREEN,
                              font=FONT_BOLD)
        self.text.tag_config("agent_msg", foreground=COLOR_AGENT, font=FONT,
                              spacing1=4, spacing3=4, rmargin=120)
        self.text.tag_config("error", foreground=COLOR_ERROR, font=FONT)
        self.text.tag_config("dim", foreground=COLOR_DIM, font=FONT_SMALL)
        self.text.tag_config("separator", foreground=COLOR_BORDER,
                              font=("Consolas", 3), spacing1=2, spacing2=2)
        self.text.tag_config("thinking_label", foreground="#8888ff", font=("Consolas", 10, "bold"))
        self.text.tag_config("thinking_content", foreground="#666688", font=("Consolas", 10))
        self.text.tag_config("thinking_sep", foreground="#444466", font=("Consolas", 7))
        self.text.tag_config("thinking_toggle", elide=False)
        self.text.tag_config("code_block", foreground=COLOR_CODE_BG_FG,
                              font=("Consolas", 11), spacing1=2, spacing3=2,
                              lmargin1=12, rmargin=12)
        self.text.tag_config("code_fence", foreground=COLOR_CODE_SIGN,
                              font=("Consolas", 10))
        self.text.tag_config("search_highlight", background=COLOR_SEARCH_HIGHLIGHT,
                              foreground="#ffffff")
        self.text.tag_config("timestamp", foreground="#333344", font=("Consolas", 9))

        self.search_frame = tk.Frame(self._container, bg=COLOR_SEARCH_BG, height=30)
        self.search_label = tk.Label(self.search_frame, text="查找:",
                                      bg=COLOR_SEARCH_BG, fg=COLOR_LABEL,
                                      font=FONT_SMALL)
        self.search_label.pack(side="left", padx=(12, 4))
        self.search_entry = tk.Entry(self.search_frame, bg="#2a2a3a", fg=COLOR_FG,
                                      font=FONT_SMALL, relief="flat", borderwidth=0,
                                      insertbackground=COLOR_GREEN)
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=2, padx=4)
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        self.search_entry.bind("<Escape>", lambda e: self._toggle_search())
        self.search_count = tk.Label(self.search_frame, text="", bg=COLOR_SEARCH_BG,
                                      fg=COLOR_DIM, font=FONT_SMALL)
        self.search_count.pack(side="left", padx=8)
        btn_close = tk.Label(self.search_frame, text=" ✕ ", bg=COLOR_SEARCH_BG,
                              fg=COLOR_DIM, font=FONT_SMALL, cursor="hand2")
        btn_close.pack(side="right", padx=(0, 8))
        btn_close.bind("<Button-1>", lambda e: self._toggle_search())

        bottom = tk.Frame(self._container, bg=COLOR_BG)
        bottom.pack(fill="x")
        self.bottom_frame = bottom

        sep2 = tk.Frame(bottom, bg=COLOR_BORDER, height=1)
        sep2.pack(fill="x")

        input_row = tk.Frame(bottom, bg=COLOR_BG)
        input_row.pack(fill="x", padx=12, pady=(8, 10))

        tk.Label(input_row, text="> ", bg=COLOR_BG, fg=COLOR_PROMPT,
                 font=FONT_BOLD).pack(side="left", anchor="s")

        self.input = tk.Text(input_row, bg=COLOR_INPUT_BG, fg=COLOR_INPUT_FG,
                              font=FONT, relief="flat", borderwidth=0,
                              insertbackground=COLOR_GREEN,
                              height=3, wrap="word")
        self.input.pack(side="left", fill="x", expand=True, ipady=4,
                         padx=(0, 8))
        self.input.bind("<Return>", lambda e: self._send())
        self.input.bind("<Shift-Return>", lambda e: self._insert_newline())
        self.input.focus()

        self.send_btn = tk.Button(input_row, text="发送", bg=COLOR_BORDER,
                                   fg=COLOR_LABEL, font=FONT_SMALL,
                                   relief="flat", padx=12, activebackground="#333",
                                   activeforeground="#fff", cursor="hand2",
                                   command=self._send)
        self.send_btn.pack(side="right", anchor="s")

        memo_bar = tk.Frame(bottom, bg=COLOR_BG, height=20)
        memo_bar.pack(fill="x")
        self.memo_hint = tk.Label(memo_bar, bg=COLOR_BG, fg=COLOR_DIM,
                                   font=("Consolas", 9),
                                   text="/help 查看命令 | 记忆会在对话时自动注入")
        self.memo_hint.pack(padx=16, pady=(2, 6))

        status_bar = tk.Frame(bottom, bg="#0a0a0a", height=22)
        status_bar.pack(fill="x")
        tk.Frame(status_bar, bg="#1a1a1a", height=1).pack(fill="x")

        inner_bar = tk.Frame(status_bar, bg="#0a0a0a")
        inner_bar.pack(fill="x", padx=12, pady=(2, 2))

        self.speed_label = tk.Label(inner_bar,
            textvariable=self.token_speed_var,
            bg="#0a0a0a", fg="#666688", font=("Consolas", 9))
        self.speed_label.pack(side="left", padx=(0, 12))
        self.context_label = tk.Label(inner_bar,
            textvariable=self.context_var,
            bg="#0a0a0a", fg="#666688", font=("Consolas", 9))
        self.context_label.pack(side="left")

        self.new_conv_btn = tk.Label(inner_bar,
            text="✚ 新对话", bg="#0a0a0a", fg="#4ade80",
            font=("Consolas", 9, "bold"), cursor="hand2")
        self.new_conv_btn.pack(side="left", padx=(8, 0))
        self.new_conv_btn.bind("<Button-1>", lambda e: self._new_conversation())

        self.history_btn = tk.Label(inner_bar,
            text="历史 ▸", bg="#0a0a0a", fg="#666688",
            font=("Consolas", 9), cursor="hand2")
        self.history_btn.pack(side="left", padx=(8, 0))
        self.history_btn.bind("<Button-1>", lambda e: self._show_history_dialog())

        self.retry_btn = tk.Label(inner_bar,
            text="↻ 重试", bg="#0a0a0a", fg="#333333",
            font=("Consolas", 9), cursor="hand2")
        self.retry_btn.pack(side="left", padx=(6, 0))
        self.retry_btn.bind("<Button-1>", lambda e: self._retry_last())

        self.edit_btn = tk.Label(inner_bar,
            text="✎ 编辑", bg="#0a0a0a", fg="#333333",
            font=("Consolas", 9), cursor="hand2")
        self.edit_btn.pack(side="left", padx=(2, 0))
        self.edit_btn.bind("<Button-1>", lambda e: self._edit_last())

        self.model_btn = tk.Label(inner_bar,
            text=self._model_btn_text(),
            bg="#0a0a0a", fg="#8888aa", font=("Consolas", 9), cursor="hand2")
        self.model_btn.pack(side="right", padx=(0, 2))
        self.model_btn.bind("<Button-1>", lambda e: self._switch_provider_dialog())

        self.config_btn = tk.Label(inner_bar,
            text="⚙", bg="#0a0a0a", fg="#555555",
            font=("Consolas", 9), cursor="hand2")
        self.config_btn.pack(side="right")
        self.config_btn.bind("<Button-1>", lambda e: self._switch_provider_dialog())

        self.perm_btn = tk.Label(inner_bar,
            text="🔐", bg="#0a0a0a", fg="#4a4a4a",
            font=("Consolas", 9), cursor="hand2")
        self.perm_btn.pack(side="right", padx=(0, 2))
        self.perm_btn.bind("<Button-1>", lambda e: self._show_permissions_dialog())

        self.thinking_btn = tk.Label(inner_bar,
            text="思考 ▼", bg="#0a0a0a", fg="#666688",
            font=("Consolas", 9), cursor="hand2")
        self.thinking_btn.pack(side="right", padx=(0, 8))
        self.thinking_btn.bind("<Button-1>", lambda e: self._toggle_thinking())

        self.stop_btn = tk.Label(inner_bar,
            text="⏹ 停止", bg="#0a0a0a", fg="#ff4444",
            font=("Consolas", 9, "bold"), cursor="hand2")
        self.stop_btn.bind("<Button-1>", lambda e: self._stop_stream())

        self.plan_status = tk.Label(inner_bar, text="", bg="#0a0a0a",
            fg="#8888ff", font=("Consolas", 9))
        self.plan_status.pack(side="right", padx=(0, 4))

        self.inner_bar = inner_bar
        self.status_bar_frame = status_bar

        self._show_welcome()
        self._apply_theme(self.theme_name)
        self._update_prov_tabs()
        self._setup_drag_drop()

    # ======== Conversation History ========

    def _new_conv_id(self):
        return datetime.now().strftime("conv_%Y%m%d_%H%M%S")

    def _conv_dir(self):
        p = MEMORY_DIR / "conversations"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _save_conversation(self):
        if not self.messages:
            return
        data = {
            "id": self.conversation_id,
            "title": self.conversation_title,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "messages": self.messages,
        }
        fp = self._conv_dir() / f"{self.conversation_id}.json"
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _list_conversations(self):
        conv_dir = self._conv_dir()
        convs = []
        for f in sorted(conv_dir.glob("conv_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                convs.append({
                    "id": data.get("id", f.stem),
                    "title": data.get("title", "无标题"),
                    "updated_at": data.get("updated_at", ""),
                    "count": len(data.get("messages", [])),
                    "file": f,
                })
            except Exception:
                convs.append({"id": f.stem, "title": "读取失败", "updated_at": "", "count": 0, "file": f})
        return convs

    def _restore_conversation(self, cid, filepath):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            self.messages = data.get("messages", [])
            self.conversation_id = cid
            self.conversation_title = data.get("title", "历史对话")
            self._show_welcome()
            self.text.configure(state="normal")
            for msg in self.messages:
                if msg["role"] == "user":
                    self.text.insert("end", "\n", "separator")
                    self.text.insert("end", " > ", "user_label")
                    self.text.insert("end", msg["content"] + "\n", "user_msg")
                elif msg["role"] == "assistant":
                    self.text.insert("end", "  ", "agent_label")
                    self.text.insert("end", msg["content"] + "\n", "agent_msg")
            self.text.insert("end", "\n", "separator")
            self.text.configure(state="disabled")
            self.text.see("end")
            self.started = True
            return True
        except Exception as e:
            self._show_lines([f"  加载失败: {e}"], "error")
            return False

    def _show_history_dialog(self):
        convs = self._list_conversations()
        dlg = tk.Toplevel(self)
        dlg.title("历史对话")
        dlg.geometry("600x420")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="已保存的对话:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(padx=16, pady=(12, 4), anchor="w")

        if not convs:
            tk.Label(dlg, text="  暂无历史对话", bg=COLOR_BG, fg=COLOR_DIM,
                     font=FONT).pack(padx=16, pady=20, anchor="w")
            tk.Button(dlg, text="关闭", bg="#222", fg=COLOR_LABEL,
                      font=FONT_SMALL, relief="flat", padx=16,
                      command=dlg.destroy).pack(pady=12)
            return

        frame = tk.Frame(dlg, bg="#1a1a1a")
        frame.pack(fill="both", expand=True, padx=16, pady=4)

        listbox = tk.Listbox(frame, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                              selectbackground="#333366", relief="flat",
                              borderwidth=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(frame, command=listbox.yview,
                                  bg="#1a1a1a", troughcolor="#0d0d0d",
                                  activebackground=COLOR_DIM)
        listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        listbox.pack(side="left", fill="both", expand=True)

        for c in convs:
            title = c["title"][:50]
            date = c["updated_at"]
            count = c["count"]
            is_current = " ◄" if c["id"] == self.conversation_id else ""
            listbox.insert("end", f"  [{date}] {title:50s}  {count}条{is_current}")

        def do_load():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            c = convs[idx]
            dlg.destroy()
            self._save_conversation()
            self._restore_conversation(c["id"], c["file"])

        def do_delete():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            c = convs[idx]
            if c["id"] == self.conversation_id:
                self._show_lines(["  不能删除当前对话"], "error")
                return
            c["file"].unlink(missing_ok=True)
            dlg.destroy()
            self._show_history_dialog()

        def do_rename():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            c = convs[idx]
            from tkinter import simpledialog
            new_title = simpledialog.askstring("重命名", "新名称:",
                initialvalue=c["title"], parent=dlg)
            if new_title:
                try:
                    data = json.loads(c["file"].read_text(encoding="utf-8"))
                    data["title"] = new_title
                    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    c["file"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                dlg.destroy()
                self._show_history_dialog()

        btn_frame = tk.Frame(dlg, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=(8, 12))
        tk.Button(btn_frame, text="加载", bg="#2a4a2a", fg=COLOR_GREEN,
                  font=FONT_SMALL, relief="flat", padx=20,
                  command=do_load).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="重命名", bg="#5a5a2a", fg=COLOR_YELLOW,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=do_rename).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="删除", bg="#5a2a2a", fg=COLOR_ERROR,
                  font=FONT_SMALL, relief="flat", padx=20,
                  command=do_delete).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="取消", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right")
        listbox.bind("<Double-Button-1>", lambda e: do_load())

    # ======== Search Overlay ========

    def _toggle_search(self):
        if self.search_visible:
            self.search_frame.pack_forget()
            self.search_visible = False
            self._search_clear()
            self.input.focus()
        else:
            self.search_frame.pack(fill="x", before=self.bottom_frame)
            self.search_visible = True
            self.search_entry.delete(0, "end")
            self.search_entry.focus()
            self.search_count.configure(text="")

    def _do_search(self):
        query = self.search_entry.get()
        self._search_clear()
        if not query:
            self.search_count.configure(text="")
            return
        count = 0
        idx = "1.0"
        while True:
            idx = self.text.search(query, idx, nocase=True, stopindex="end")
            if not idx:
                break
            end = f"{idx}+{len(query)}c"
            self.text.tag_add("search_highlight", idx, end)
            count += 1
            idx = end
        self.search_count.configure(text=f"{count} 个匹配")

    def _search_clear(self):
        self.text.tag_remove("search_highlight", "1.0", "end")

    # ======== Input Helpers ========

    def _insert_newline(self):
        self.input.insert("insert", "\n")
        return "break"

    def _show_welcome(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n  /help      - 查看命令\n", "dim")
        self.text.insert("end", "  /models    - 列出/切换模型\n", "dim")
        self.text.insert("end", "  /read      - 读取文件\n", "dim")
        self.text.insert("end", "  /search    - 搜索网络\n", "dim")
        self.text.insert("end", "  /plan      - 多步规划\n", "dim")
        self.text.insert("end", "  /kb        - 知识库\n", "dim")
        self.text.insert("end", "  /mem       - 管理记忆\n", "dim")
        self.text.insert("end", "  /new       - 新对话\n", "dim")
        self.text.insert("end", "  /history   - 历史对话\n", "dim")
        self.text.insert("end", "  /export    - 导出对话\n", "dim")
        self.text.insert("end", "  /theme     - 切换主题\n", "dim")
        self.text.insert("end", "  /prompt    - 编辑提示词\n", "dim")
        self.text.insert("end", "\n  输入消息开始对话\n", "dim")
        self.text.configure(state="disabled")

    # ======== Memory ========

    def _load_memories(self):
        self.memories = load_memories()
        self.mem_label.configure(text=str(len(self.memories)))

    # ======== Window Icon ========

    def _set_window_icon(self):
        icon_path = Path(__file__).parent / "icon_small.png"
        if icon_path.exists():
            try:
                icon = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, icon)
                self._icon_img = icon
            except Exception as e:
                print(f"Icon load failed: {e}")

    # ======== Drag & Drop (Windows Shell API) ========

    def _setup_drag_drop(self):
        try:
            hwnd = self.winfo_id()
            ctypes.windll.shell32.DragAcceptFiles(hwnd, True)
            GWLP_WNDPROC = -4
            self._drop_old_proc = ctypes.windll.user32.GetWindowLongPtrW(
                hwnd, GWLP_WNDPROC
            )
            @WNDPROC
            def _drop_wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_DROPFILES:
                    self._handle_file_drop(wparam)
                    return 0
                return ctypes.windll.user32.CallWindowProcW(
                    self._drop_old_proc, hwnd, msg, wparam, lparam
                )
            self._drop_wnd_proc = _drop_wnd_proc
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, _drop_wnd_proc)
        except Exception as e:
            print(f"Drag-drop init failed: {e}")

    def _handle_file_drop(self, hDrop):
        files = []
        try:
            file_count = ctypes.windll.shell32.DragQueryFileW(hDrop, 0xFFFFFFFF, None, 0)
            for i in range(file_count):
                buf_size = ctypes.windll.shell32.DragQueryFileW(hDrop, i, None, 0) + 1
                buf = ctypes.create_unicode_buffer(buf_size)
                ctypes.windll.shell32.DragQueryFileW(hDrop, i, buf, buf_size)
                files.append(buf.value)
        finally:
            ctypes.windll.shell32.DragFinish(hDrop)
        if files:
            self.after(0, self._process_dropped_files, files)

    def _process_dropped_files(self, files):
        if self.is_streaming:
            self._show_lines(["  [!] 正在生成回复，请稍后再拖入文件"], "error")
            return
        for fp in files:
            path = Path(fp)
            if path.exists() and path.is_file():
                ext = path.suffix.lower()
                if ext in (".exe", ".dll", ".bin", ".pyc", ".o", ".obj", ".pdb"):
                    self._show_lines([f"  跳过二进制文件: {path.name}"], "dim")
                    continue
                self._show_lines([f"  读取文件: {path.name}"], "dim")
                content = self._read_file(str(path))
                self._show_lines([content], "dim")
                self._send_raw(
                    f"用户拖入了文件 {path.name}，以下是文件内容，请分析或回答。\n\n{content}"
                )
            else:
                self._show_lines([f"  文件不存在: {fp[:80]}"], "error")

    # ======== Status & Backend ========

    def _get_current_model_name(self):
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            provider = cfg.get("provider", "local")
            name = cfg.get("model", "?")
            if provider == "local":
                if name == "gpt-3.5-turbo" or not name.endswith(".gguf"):
                    models_dir = Path(__file__).parent / "models"
                    models = sorted(models_dir.glob("*.gguf"))
                    return models[0].name if models else "custom"
                return name
            else:
                return name if name else "?"
        except:
            return "?"

    def _run_setup_wizard(self):
        """延迟执行首次运行向导（等主窗口初始化完毕）。"""
        from app.setup_wizard import show_setup_wizard
        cfg = self._setup_pending or {}
        try:
            result = show_setup_wizard(self, cfg)
        finally:
            self._setup_pending = None
        if result is not None:
            self._save_config(result)
            self._save_credentials(result)
            self.provider = result.get("provider", self.provider)
            self.openai_api_key = result.get("openai_api_key", self.openai_api_key)
            self.openai_base_url = result.get("openai_base_url", self.openai_base_url)
            self.anthropic_api_key = result.get("anthropic_api_key", self.anthropic_api_key)
            model = result.get("model", "")
            if model:
                self.current_model = model
            self.theme_name = result.get("theme", self.theme_name)
            self._apply_theme(self.theme_name)
            self._refresh_model_btn()
            self._update_prov_tabs()
            self._check_status()
        # 向导完成或取消后，继续正常启动流程
        self.after(500, self._auto_start)

    def _auto_start(self):
        if self._setup_pending is not None:
            return  # 向导还在进行中，跳过自动启动
        if self.provider == "local":
            if self.status_dot.itemcget(self.dot, "fill") != COLOR_STATUS_OK:
                self._show_lines(["  [!] 后端离线，正在自动启动..."], "dim")
                self._start_backend()
                # 启动等待动画
                self._show_loading_animation()
        else:
            self.after(100, self._check_status)

    def _show_loading_animation(self):
        """显示后端启动的等待动画。"""
        dots = [".  ", ".. ", "...", " ..", "  .", "   "]
        self._loading_idx = 0
        self._loading_timer_id = None
        self.status_text.configure(text="● 启动中", fg=COLOR_YELLOW)

        def _animate():
            if self._loading_idx >= len(dots):
                self._loading_idx = 0
            dot = dots[self._loading_idx]
            self.status_text.configure(text=f"● 启动中{dot}")
            self._loading_idx += 1
            # 检查是否已在运行或超过15秒
            if self.status_dot.itemcget(self.dot, "fill") == COLOR_STATUS_OK:
                self.status_text.configure(text="● 在线", fg=COLOR_STATUS_OK)
                return
            self._loading_timer_id = self.after(500, _animate)

        self.after(500, _animate)

    def _list_models(self):
        if self.provider == "local":
            models_dir = Path(__file__).parent / "models"
            models = []
            for f in sorted(models_dir.glob("*.gguf")):
                size = f.stat().st_size / (1024**3)
                models.append({"name": f.name, "path": str(f), "size": size})
            return models
        elif self.provider == "openai":
            config = self._provider_config()
            ids = providers.list_openai_models(config)
            return [{"name": m, "path": "", "size": 0} for m in ids]
        elif self.provider == "anthropic":
            config = self._provider_config()
            ids = providers.list_anthropic_models(config)
            return [{"name": m, "path": "", "size": 0} for m in ids]
        return []

    def _provider_config(self):
        return {
            "provider": self.provider,
            "model": self.current_model,
            "openai_api_key": self.openai_api_key,
            "openai_base_url": self.openai_base_url,
            "anthropic_api_key": self.anthropic_api_key,
            "api_base": f"http://127.0.0.1:{LLAMA_PORT}" if self.provider == "local" else "",
            "temperature": 0.7,
            "max_tokens": 4096,
            "timeout": 120,
        }

    def _stop_backend(self):
        if self.llama_proc:
            try:
                self.llama_proc.kill()
                self.llama_proc.wait(timeout=3)
            except:
                pass
            self.llama_proc = None
        try:
            subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                           capture_output=True, timeout=3)
        except:
            pass
        time.sleep(1)

    def _check_status(self):
        ok = False
        if self.provider == "local":
            try:
                r = requests.get(f"http://127.0.0.1:{LLAMA_PORT}/v1/models",
                                 timeout=2)
                ok = r.status_code == 200
            except:
                ok = False
        else:
            now = time.time()
            if now - self._last_provider_validation > 60:
                config = self._provider_config()
                if self.provider == "openai":
                    ok = providers.validate_openai(config)
                elif self.provider == "anthropic":
                    ok = providers.validate_anthropic(config)
                self._last_provider_validation = now if ok else 0
            else:
                ok = True

        if ok:
            self.status_dot.itemconfig(self.dot, fill=COLOR_STATUS_OK)
            self.input.configure(state="normal")
            self.send_btn.configure(state="normal")
            model_short = self.current_model[:40] if self.current_model else "?"
            self.status_text.configure(text=f"● {model_short}", fg=COLOR_STATUS_OK)
            self._update_prov_tabs()
        else:
            self.status_dot.itemconfig(self.dot, fill=COLOR_STATUS_ERR)
            self.status_text.configure(text="● 离线", fg=COLOR_STATUS_ERR)
            if self.provider == "local":
                self.input.configure(state="disabled")
                self.send_btn.configure(state="disabled")

        interval = 10000 if self.provider == "local" else 60000
        self.after(interval, self._check_status)

    # ======== Commands ========

    def _cmd_help(self):
        lines = [
            "",
            "可用命令:",
            "  /help              显示此帮助",
            "  /models            列出可用的模型",
            "  /model <模型名>     切换到指定模型 (本地/API)",
            "  /provider          显示当前 provider",
            "  /provider <类型>    切换 provider (local/openai/anthropic)",
            "  /key <类型> <密钥>  设置 API 密钥 (/key openai sk-...)",
            "  /read <文件路径>    读取文件内容",
            "  /write <文件路径>   创建或写入文件",
            "  /delete <文件路径>  删除文件",
            "  /search <关键词>    搜索网络",
            "  /plan <任务>        多步规划执行",
            "  /kb index <路径>    索引文档到知识库",
            "  /kb search <词>     搜索知识库",
            "  /kb status         知识库状态",
            "  /mem list          列出所有记忆",
            "  /mem add <名> <描述> 添加记忆",
            "  /mem del <名>      删除记忆",
            "  /status            检查后端状态",
            "  /clear             清屏",
            "  /history          历史对话浏览",
            "  /new              新对话",
            "  /rename <标题>    重命名当前对话",
            "  /export           导出对话为 Markdown",
            "  /theme [名称]     列出/切换主题 (ocean/twilight/forest/warm)",
            "  /prompt           编辑系统提示词",
            "  /exit              退出",
            "",
        ]
        self._show_lines(lines, "dim")

    def _cmd_mem_list(self):
        if not self.memories:
            self._show_lines(["  还没有记忆。用 /mem add 添加一条。"], "dim")
            return
        lines = [f"  记忆 ({len(self.memories)}):"]
        for name, mem in self.memories.items():
            lines.append(f"    [{name}] {mem['description']}")
        self._show_lines(lines, "dim")

    def _cmd_mem_add(self, arg):
        if not self._perm_check("memory_add", "记忆添加"):
            return
        parts = arg.split(None, 1)
        if not parts:
            self._show_lines(["  用法: /mem add <名字> <描述>"], "dim")
            return
        name = parts[0]
        desc = parts[1] if len(parts) > 1 else name
        self._show_lines([f"  输入内容 (空行结束):"], "dim")
        dlg = tk.Toplevel(self)
        dlg.title("添加记忆")
        dlg.geometry("400x250")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"名字: {name}  描述: {desc}",
                 bg=COLOR_BG, fg=COLOR_LABEL, font=FONT_SMALL).pack(padx=16, pady=(12,4))
        tk.Label(dlg, text="详细内容:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(padx=16, pady=(4,2))

        txt = tk.Text(dlg, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                       relief="flat", borderwidth=0, height=6)
        txt.pack(fill="both", expand=True, padx=16, pady=4)
        txt.focus()

        def do_save():
            content = txt.get("1.0", "end-1c").strip()
            save_memory(name, desc, content)
            self._load_memories()
            self._show_lines([f"  已保存记忆: {name}"], "dim")
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))
        tk.Button(btn_frame, text="取消", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right", padx=(4,0))
        tk.Button(btn_frame, text="保存", bg="#2a4a2a", fg=COLOR_GREEN,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=do_save).pack(side="right")
        txt.bind("<Control-Return>", lambda e: do_save())

    def _cmd_mem_del(self, arg):
        if not self._perm_check("memory_delete", "记忆删除"):
            return
        if not arg:
            self._show_lines(["  用法: /mem del <名字>"], "dim")
            return
        delete_memory(arg.strip())
        self._load_memories()
        self._show_lines([f"  已删除记忆: {arg}"], "dim")

    def _cmd_models(self, switch_name=None):
        models = self._list_models()
        if not models:
            if self.provider == "local":
                self._show_lines(["  [!] models/ 目录没有 .gguf 文件"], "error")
            else:
                self._show_lines(["  [!] 无法获取模型列表，请先设置 API 密钥"], "error")
            return

        if switch_name:
            match = None
            for m in models:
                if switch_name in m["name"]:
                    match = m
                    break
            if not match:
                self._show_lines([f"  未找到包含「{switch_name}」的模型"], "error")
                return
            self._show_lines([f"  切换到: {match['name']}"], "dim")
            if self.provider == "local":
                self._start_backend(match["name"])
            else:
                self.current_model = match["name"]
                self._save_config({"model": match["name"]})
                self._refresh_model_btn()
            return

        lines = [f"  可用模型 ({len(models)}) [{self.provider.upper()}]", ""]
        for m in models:
            tag = "  ► " if m["name"] == self.current_model else "    "
            if self.provider == "local":
                lines.append(f"{tag}{m['name']:45s} {m['size']:5.1f}GB")
            else:
                lines.append(f"{tag}{m['name']}")
        lines.append("")
        lines.append("  切换: /model <关键词或模型ID>")
        lines.append("")
        self._show_lines(lines, "dim")

    def _cmd_model(self, arg):
        if not arg:
            self._show_lines([f"  当前: {self.current_model}"], "dim")
        elif self.provider == "local":
            self._cmd_models(arg)
        else:
            self.current_model = arg
            self._save_config({"model": arg})
            self._refresh_model_btn()
            self._show_lines([f"  已切换模型: {arg}"], "dim")

    def _cmd_provider(self, arg):
        if not arg:
            self._show_lines([f"  当前 provider: {self.provider}", f"  当前模型: {self.current_model}"], "dim")
            return
        arg = arg.strip().lower()
        if arg not in ("local", "openai", "anthropic"):
            self._show_lines([f"  无效 provider: {arg}，可选: local, openai, anthropic"], "dim")
            return
        if arg == self.provider:
            self._show_lines([f"  已经是 {arg}"], "dim")
            return
        if self.provider == "local":
            self._stop_backend()
        self.provider = arg
        if arg in ("openai", "anthropic") and self.current_model.endswith(".gguf"):
            self.current_model = "gpt-4o" if arg == "openai" else "claude-sonnet-4-7"
        self._save_config({"provider": arg, "model": self.current_model})
        self._refresh_model_btn()
        self._check_status()
        self._show_lines([f"  已切换到 provider: {arg}"], "dim")

    def _cmd_key(self, arg):
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            self._show_lines(["  用法: /key <openai|anthropic> <你的密钥>", "  例: /key openai sk-xxxx"], "dim")
            return
        prov, key = parts[0].lower(), parts[1].strip()
        if prov == "openai":
            self.openai_api_key = key
            self._save_credentials({"openai_api_key": key})
        elif prov == "anthropic":
            self.anthropic_api_key = key
            self._save_credentials({"anthropic_api_key": key})
        else:
            self._show_lines([f"  无效 provider: {prov}，可选: openai, anthropic"], "dim")
            return
        self._show_lines([f"  已保存 {prov} API 密钥"], "dim")
        self._check_status()

    def _cmd_status(self):
        self._show_lines(["  检查后端状态..."], "dim")
        self._check_status()
        self.after(500, lambda: self._show_lines(["  状态已刷新"], "dim"))

    def _cmd_clear(self):
        self.messages = []
        self.context_summary = ""
        self.started = False
        self._show_welcome()

    # ======== Theme System ========

    def _apply_theme(self, theme_name=None):
        if theme_name:
            self.theme_name = theme_name
        theme = THEMES.get(self.theme_name, THEMES["default"])
        c = theme

        self.configure(bg=c["bg"])
        self._container.configure(bg=c["bg"])
        self.title_bar.configure(bg=c["bg"])
        self.sep.configure(bg=c["border"])

        for child in self.title_bar.winfo_children():
            if isinstance(child, (tk.Label, tk.Canvas)):
                try: child.configure(bg=c["bg"])
                except: pass
        self.status_text.configure(fg=c["status_err"])
        self.mem_label.configure(fg=c["label"])
        for child in self.title_bar.winfo_children():
            if isinstance(child, tk.Label):
                fg = child.cget("fg")
                if fg in ("#555555", "#888888"):
                    try: child.configure(fg=c["dim"])
                    except: pass

        self.text.configure(bg=c["bg"], fg=c["fg"])
        self.text.tag_config("logo", foreground=c["dim"])
        self.text.tag_config("logo_title", foreground=c["label"])
        self.text.tag_config("banner", foreground=c["dim"])
        self.text.tag_config("user_label", foreground=c["prompt"])
        self.text.tag_config("user_msg", foreground=c["user"])
        self.text.tag_config("agent_label", foreground=c["green"])
        self.text.tag_config("agent_msg", foreground=c["agent"])
        self.text.tag_config("error", foreground=c["error"])
        self.text.tag_config("dim", foreground=c["dim"])
        self.text.tag_config("separator", foreground=c["border"])
        self.text.tag_config("thinking_label", foreground=c["thinking_label"])
        self.text.tag_config("thinking_content", foreground=c["thinking_content"])
        self.text.tag_config("thinking_sep", foreground=c["thinking_sep"])
        self.text.tag_config("code_block", foreground=c["code_fg"])
        self.text.tag_config("code_fence", foreground=c["code_sign"])
        self.text.tag_config("search_highlight", background=c["search_highlight"])
        self.text.tag_config("timestamp", foreground=c["timestamp"])

        self.search_frame.configure(bg=c["search_bg"])
        self.search_label.configure(bg=c["search_bg"], fg=c["label"])
        self.search_entry.configure(bg=c["input_bg"], fg=c["fg"])
        self.search_count.configure(bg=c["search_bg"], fg=c["dim"])
        for child in self.search_frame.winfo_children():
            if isinstance(child, tk.Label) and child.cget("text").strip() == "✕":
                try: child.configure(bg=c["search_bg"], fg=c["dim"])
                except: pass

        self.bottom_frame.configure(bg=c["bg"])
        for child in self.bottom_frame.winfo_children():
            if isinstance(child, tk.Frame):
                try:
                    child.configure(bg=c["bg"])
                except: pass

        self.input.configure(bg=c["input_bg"], fg=c["input_fg"])
        self.send_btn.configure(bg=c["border"], fg=c["label"])
        self.memo_hint.configure(bg=c["bg"], fg=c["dim"])

        self.status_bar_frame.configure(bg=c["status_bar_bg"])
        self.inner_bar.configure(bg=c["status_bar_bg"])
        for child in self.inner_bar.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=c["status_bar_bg"])

        self._save_config({"theme": self.theme_name})

    def _cmd_theme(self, arg=None):
        if not arg:
            names = list(THEMES.keys())
            lines = [f"  可用主题 ({len(names)}):"]
            for n in names:
                tag = "  ► " if n == self.theme_name else "    "
                lines.append(f"{tag}{n:15s} {THEMES[n]['label']}")
            lines.append("")
            lines.append("  切换: /theme <名称>")
            lines.append("  例: /theme ocean")
            lines.append("")
        else:
            if arg in THEMES:
                self._apply_theme(arg)
                self._show_lines([f"  已切换主题: {THEMES[arg]['label']}"], "dim")
            else:
                self._show_lines([f"  未找到主题: {arg}，用 /theme 查看列表"], "error")

    def _load_config(self):
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return {}

    def _show_lines(self, lines, tag="dim"):
        self.text.configure(state="normal")
        for line in lines:
            self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    # ======== Thinking Display ========

    def _thinking_start(self):
        self.text.configure(state="normal")
        self.text.insert("end", "\n  思考过程\n  ", ("thinking_label", "thinking_toggle"))
        self.text.configure(state="disabled")
        self.text.see("end")

    def _thinking_append(self, text):
        self.text.configure(state="normal")
        self.text.insert("end", text, ("thinking_content", "thinking_toggle"))
        self.text.configure(state="disabled")
        self.text.see("end")

    def _thinking_end(self):
        self.text.configure(state="normal")
        self.text.insert("end", "\n  ---\n  ", ("thinking_sep", "thinking_toggle"))
        self.text.configure(state="disabled")
        self.text.see("end")

    def _toggle_thinking(self):
        self.thinking_visible = not self.thinking_visible
        self.text.tag_config("thinking_toggle", elide=not self.thinking_visible)
        self.thinking_btn.configure(text="思考 ▼" if self.thinking_visible else "思考 ▲")

    # ======== Stats ========

    def _update_stats(self):
        now = time.time()
        if now - self._last_stats_update < 0.25:
            return
        self._last_stats_update = now
        if self.stream_start_time == 0:
            return
        elapsed = now - self.stream_start_time
        speed = self.completion_tokens / elapsed if elapsed > 0 and self.completion_tokens > 0 else 0
        self.token_speed_var.set(f"{speed:.1f} t/s")
        if speed > 15:
            self.speed_label.configure(fg=COLOR_GREEN)
        elif speed > 5:
            self.speed_label.configure(fg=COLOR_YELLOW)
        else:
            self.speed_label.configure(fg="#666688")

        total = self.prompt_tokens + self.completion_tokens
        self.context_var.set(f"ctx: {total}/8192")
        if total > 7000:
            self.context_label.configure(fg=COLOR_ERROR)
        elif total > 5500:
            self.context_label.configure(fg=COLOR_YELLOW)
        else:
            self.context_label.configure(fg="#666688")

    def _update_prov_tabs(self):
        active_color = {"local": COLOR_GREEN, "openai": "#4a9eff", "anthropic": "#d4a574"}
        for p, lbl in self._prov_tabs.items():
            if p == self.provider:
                lbl.configure(fg=active_color.get(p, COLOR_LABEL))
            else:
                lbl.configure(fg="#444444")

    def _ui_switch_provider(self, target):
        if target == self.provider:
            return
        if target != "local" and not self._provider_has_key(target):
            self._switch_provider_dialog()
            return
        # Stop local backend when switching away
        if self.provider == "local":
            self._stop_backend()
        self.provider = target
        # Reset model name if coming from local (GGUF names don't work on external APIs)
        if target in ("openai", "anthropic") and self.current_model.endswith(".gguf"):
            self.current_model = "gpt-4o" if target == "openai" else "claude-sonnet-4-7"
        self._save_config({"provider": target, "model": self.current_model})
        self._update_prov_tabs()
        self._refresh_model_btn()
        self._check_status()
        self._show_lines([f"  已切换到 [{(self.provider).upper()}]"], "dim")

    def _provider_has_key(self, prov):
        if prov == "openai":
            return bool(self.openai_api_key)
        if prov == "anthropic":
            return bool(self.anthropic_api_key)
        return True

    def _refresh_model_btn(self):
        self.model_btn.configure(text=self._model_btn_text())

    def _model_btn_text(self):
        provider_tag = {"local": "L", "openai": "O", "anthropic": "A"}.get(self.provider, "?")
        name = self.current_model[:28] if self.current_model else "?"
        return f" {provider_tag} {name} "

    # ======== Model & Provider Switching Dialog ========

    def _switch_provider_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("切换 Provider / 模型")
        dlg.geometry("560x480")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="选择 Provider:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(padx=16, pady=(12, 4), anchor="w")

        prov_frame = tk.Frame(dlg, bg=COLOR_BG)
        prov_frame.pack(fill="x", padx=16, pady=4)

        provider_var = tk.StringVar(value=self.provider)

        def on_provider_change(*args):
            _show_provider_content(provider_var.get())

        prov_local = tk.Radiobutton(prov_frame, text="本地 Local", variable=provider_var,
                                     value="local", bg=COLOR_BG, fg=COLOR_LABEL,
                                     selectcolor="#1a1a1a", font=FONT_SMALL,
                                     command=on_provider_change)
        prov_local.pack(side="left", padx=(0, 8))

        prov_openai = tk.Radiobutton(prov_frame, text="OpenAI", variable=provider_var,
                                      value="openai", bg=COLOR_BG, fg=COLOR_LABEL,
                                      selectcolor="#1a1a1a", font=FONT_SMALL,
                                      command=on_provider_change)
        prov_openai.pack(side="left", padx=(0, 8))

        prov_anthropic = tk.Radiobutton(prov_frame, text="Anthropic", variable=provider_var,
                                         value="anthropic", bg=COLOR_BG, fg=COLOR_LABEL,
                                         selectcolor="#1a1a1a", font=FONT_SMALL,
                                         command=on_provider_change)
        prov_anthropic.pack(side="left")

        sep = tk.Frame(dlg, bg=COLOR_BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=8)

        content_frame = tk.Frame(dlg, bg=COLOR_BG)
        content_frame.pack(fill="both", expand=True, padx=16, pady=4)

        local_frame = tk.Frame(content_frame, bg=COLOR_BG)
        tk.Label(local_frame, text="本地 GGUF 模型:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w")
        lf = tk.Frame(local_frame, bg="#1a1a1a")
        lf.pack(fill="both", expand=True, pady=4)
        local_listbox = tk.Listbox(lf, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                                    selectbackground="#333366", relief="flat",
                                    borderwidth=0, highlightthickness=0)
        local_scroll = tk.Scrollbar(lf, command=local_listbox.yview,
                                     bg="#1a1a1a", troughcolor="#0d0d0d",
                                     activebackground=COLOR_DIM)
        local_listbox.configure(yscrollcommand=local_scroll.set)
        local_scroll.pack(side="right", fill="y")
        local_listbox.pack(side="left", fill="both", expand=True)

        models = self._list_models() if self.provider == "local" else []
        for i, m in enumerate(models):
            tag = " * " if m["name"] == self.current_model else "   "
            local_listbox.insert("end", f"{tag}{m['name']:45s} {m['size']:5.1f}GB")

        openai_frame = tk.Frame(content_frame, bg=COLOR_BG)
        tk.Label(openai_frame, text="API Key:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w")
        openai_key_entry = tk.Entry(openai_frame, bg="#1a1a1a", fg=COLOR_FG,
                                     font=("Consolas", 10), relief="flat", borderwidth=6)
        openai_key_entry.pack(fill="x", pady=(2, 8))
        openai_key_entry.insert(0, self.openai_api_key)
        openai_key_entry.configure(show="*")

        def toggle_openai_key():
            if openai_key_entry.cget("show") == "*":
                openai_key_entry.configure(show="")
            else:
                openai_key_entry.configure(show="*")
        tk.Button(openai_frame, text="显示/隐藏", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=toggle_openai_key).pack(anchor="e")

        tk.Label(openai_frame, text="Base URL:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(4, 0))
        openai_url_entry = tk.Entry(openai_frame, bg="#1a1a1a", fg=COLOR_FG,
                                     font=("Consolas", 10), relief="flat", borderwidth=6)
        openai_url_entry.pack(fill="x", pady=(2, 8))
        openai_url_entry.insert(0, self.openai_base_url or "https://api.openai.com/v1")

        tk.Label(openai_frame, text="模型 (可选, 留空自动获取):", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w")

        openai_model_listbox = tk.Listbox(openai_frame, bg="#1a1a1a", fg=COLOR_FG,
                                           font=FONT, selectbackground="#333366",
                                           relief="flat", borderwidth=0, highlightthickness=0,
                                           height=6)
        openai_model_listbox.pack(fill="both", expand=True, pady=4)

        def fetch_openai_models():
            fetch_btn_openai.configure(state="disabled", text="获取中...")
            openai_model_listbox.delete(0, "end")
            openai_model_listbox.insert("end", " 正在加载...")

            def _fetch():
                cfg = {
                    "openai_api_key": openai_key_entry.get(),
                    "openai_base_url": openai_url_entry.get(),
                    "api_base": "",
                }
                ids = providers.list_openai_models(cfg)
                dlg.after(0, lambda: _populate_openai(ids))

            def _populate_openai(ids):
                openai_model_listbox.delete(0, "end")
                if not ids:
                    openai_model_listbox.insert("end", " 无法获取模型列表，请检查密钥")
                else:
                    for m_id in ids:
                        openai_model_listbox.insert("end", m_id)
                fetch_btn_openai.configure(state="normal", text="获取模型列表")

            threading.Thread(target=_fetch, daemon=True).start()

        fetch_btn_openai = tk.Button(openai_frame, text="获取模型列表", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat",
                  command=fetch_openai_models)
        fetch_btn_openai.pack(anchor="e", pady=(2, 0))

        anthropic_frame = tk.Frame(content_frame, bg=COLOR_BG)
        tk.Label(anthropic_frame, text="API Key:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w")
        anthropic_key_entry = tk.Entry(anthropic_frame, bg="#1a1a1a", fg=COLOR_FG,
                                        font=("Consolas", 10), relief="flat", borderwidth=6)
        anthropic_key_entry.pack(fill="x", pady=(2, 8))
        anthropic_key_entry.insert(0, self.anthropic_api_key)
        anthropic_key_entry.configure(show="*")

        def toggle_anthropic_key():
            if anthropic_key_entry.cget("show") == "*":
                anthropic_key_entry.configure(show="")
            else:
                anthropic_key_entry.configure(show="*")
        tk.Button(anthropic_frame, text="显示/隐藏", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=toggle_anthropic_key).pack(anchor="e")

        tk.Label(anthropic_frame, text="模型:", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(4, 0))

        anthropic_model_listbox = tk.Listbox(anthropic_frame, bg="#1a1a1a", fg=COLOR_FG,
                                              font=FONT, selectbackground="#333366",
                                              relief="flat", borderwidth=0, highlightthickness=0,
                                              height=6)
        anthropic_model_listbox.pack(fill="both", expand=True, pady=4)

        def fetch_anthropic_models():
            fetch_btn_anthropic.configure(state="disabled", text="获取中...")
            anthropic_model_listbox.delete(0, "end")
            anthropic_model_listbox.insert("end", " 正在加载...")

            def _fetch():
                cfg = {"anthropic_api_key": anthropic_key_entry.get()}
                ids = providers.list_anthropic_models(cfg)
                dlg.after(0, lambda: _populate_anthropic(ids))

            def _populate_anthropic(ids):
                anthropic_model_listbox.delete(0, "end")
                if not ids:
                    anthropic_model_listbox.insert("end", " 无法获取模型列表，请检查密钥")
                else:
                    for m_id in ids:
                        anthropic_model_listbox.insert("end", m_id)
                fetch_btn_anthropic.configure(state="normal", text="获取模型列表")

            threading.Thread(target=_fetch, daemon=True).start()

        fetch_btn_anthropic = tk.Button(anthropic_frame, text="获取模型列表", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat",
                  command=fetch_anthropic_models)
        fetch_btn_anthropic.pack(anchor="e", pady=(2, 0))

        def _show_provider_content(prov):
            for f in (local_frame, openai_frame, anthropic_frame):
                f.pack_forget()
            if prov == "local":
                local_frame.pack(fill="both", expand=True)
            elif prov == "openai":
                openai_frame.pack(fill="both", expand=True)
            elif prov == "anthropic":
                anthropic_frame.pack(fill="both", expand=True)

        _show_provider_content(self.provider)

        btn_frame = tk.Frame(dlg, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=16, pady=(8, 12))

        def do_apply():
            new_provider = provider_var.get()
            if new_provider == "local":
                sel = local_listbox.curselection()
                if not sel:
                    return
                idx = sel[0]
                model = models[idx]
                dlg.destroy()
                self._show_lines([f"  切换到: {model['name']}"], "dim")
                self._start_backend(model["name"])
                return
            else:
                if new_provider == "openai":
                    new_key = openai_key_entry.get().strip()
                    new_url = openai_url_entry.get().strip()
                    sel = openai_model_listbox.curselection()
                    if sel:
                        new_model = openai_model_listbox.get(sel[0])
                    else:
                        new_model = self.current_model
                else:
                    new_key = anthropic_key_entry.get().strip()
                    new_url = ""
                    sel = anthropic_model_listbox.curselection()
                    if sel:
                        new_model = anthropic_model_listbox.get(sel[0])
                    else:
                        new_model = self.current_model
                dlg.destroy()
                if self.provider == "local":
                    self._stop_backend()
                old_provider = self.provider
                self.provider = new_provider
                if new_provider == "openai":
                    self.openai_api_key = new_key
                    self.openai_base_url = new_url
                else:
                    self.anthropic_api_key = new_key
                self.current_model = new_model if new_model else self.current_model
                self._save_config({
                    "provider": self.provider,
                    "model": self.current_model,
                })
                self._save_credentials({
                    "openai_api_key": self.openai_api_key,
                    "openai_base_url": self.openai_base_url,
                    "anthropic_api_key": self.anthropic_api_key,
                })
                self._refresh_model_btn()
                self._check_status()
                self._show_lines([f"  已切换到 [{new_provider}] {self.current_model}"], "dim")

        tk.Button(btn_frame, text="取消", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="应用", bg="#2a4a2a", fg=COLOR_GREEN,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=do_apply).pack(side="left")

        local_listbox.bind("<Double-Button-1>", lambda e: do_apply() if provider_var.get() == "local" else None)

    # ======== System Prompt Editor ========

    def _show_prompt_editor(self):
        dlg = tk.Toplevel(self)
        dlg.title("系统提示词编辑器")
        dlg.geometry("680x560")
        dlg.configure(bg=COLOR_BG)
        dlg.transient(self)
        dlg.grab_set()

        notebook = tk.Frame(dlg, bg=COLOR_BG)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        tk.Label(notebook, text="角色设定 (Role Prompt)",
                 bg=COLOR_BG, fg=COLOR_LABEL, font=FONT_SMALL).pack(anchor="w")
        role_text = tk.Text(notebook, bg="#1a1a1a", fg=COLOR_FG,
                            font=("Consolas", 10), relief="flat", borderwidth=0,
                            height=6, wrap="word")
        role_text.pack(fill="x", pady=(4, 12))
        role_text.insert("1.0", self.system_prompt)

        tk.Label(notebook, text="规划指令 (Plan Prompt) — 让模型输出 [计划]...[/计划]",
                 bg=COLOR_BG, fg=COLOR_LABEL, font=FONT_SMALL).pack(anchor="w")
        plan_text = tk.Text(notebook, bg="#1a1a1a", fg=COLOR_FG,
                            font=("Consolas", 10), relief="flat", borderwidth=0,
                            height=6, wrap="word")
        plan_text.pack(fill="x", pady=(4, 12))
        plan_text.insert("1.0", self.plan_prompt)

        tk.Label(notebook, text="组合预览 (Preview) — 保存后生效",
                 bg=COLOR_BG, fg=COLOR_DIM, font=FONT_SMALL).pack(anchor="w")
        preview_text = tk.Text(notebook, bg="#0a0a0a", fg="#666688",
                               font=("Consolas", 9), relief="flat", borderwidth=0,
                               height=10, wrap="word", state="disabled")
        preview_text.pack(fill="both", expand=True, pady=(4, 8))

        def update_preview(*args):
            sp = role_text.get("1.0", "end-1c").strip()
            pp = plan_text.get("1.0", "end-1c").strip()
            combined = sp + "\n" + pp
            preview_text.configure(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", combined[:2000])
            preview_text.configure(state="disabled")

        role_text.bind("<KeyRelease>", update_preview)
        plan_text.bind("<KeyRelease>", update_preview)
        update_preview()

        btn_frame = tk.Frame(dlg, bg=COLOR_BG)
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))

        def do_save():
            sp = role_text.get("1.0", "end-1c").strip()
            pp = plan_text.get("1.0", "end-1c").strip()
            if sp:
                self.system_prompt = sp
            if pp:
                self.plan_prompt = pp
            self._show_lines(["  提示词已更新，下次对话生效"], "dim")
            dlg.destroy()

        tk.Button(btn_frame, text="保存", bg="#2a4a2a", fg=COLOR_GREEN,
                  font=FONT_SMALL, relief="flat", padx=24,
                  command=do_save).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="取消", bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right")

    # ======== Web Search ========

    def _search_web(self, query, max_results=5):
        if self.search_enabled:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
                if results:
                    return self._fmt_search(query, results)
            except Exception:
                pass
        try:
            return self._search_bing(query, max_results)
        except Exception as e:
            return f"[搜索失败] {e}"

    def _search_bing(self, query, count=5):
        import urllib.parse
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={count}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for li in soup.select(".b_algo"):
            a = li.select_one("h2 a")
            p = li.select_one(".b_caption p")
            if a:
                results.append({
                    "title": a.get_text(strip=True),
                    "body": p.get_text(strip=True) if p else "",
                })
                if len(results) >= count:
                    break
        return self._fmt_search(query, results) if results else "无搜索结果。"

    def _fmt_search(self, query, results):
        lines = ["[网络搜索结果]", f"查询: {query}"]
        for i, r in enumerate(results, 1):
            lines.append(f"  {i}. {r.get('title', '')}")
            body = r.get("body", "")[:150]
            if body:
                lines.append(f"     {body}")
        return "\n".join(lines)

    # ======== File Reading ========

    def _read_file(self, filepath):
        fp = Path(filepath)
        if not fp.exists():
            return f"文件不存在: {filepath}"
        try:
            text = fp.read_text(encoding="utf-8")
            lines = text.split('\n')
            size = fp.stat().st_size
            max_lines = 300
            if len(lines) > max_lines:
                text = '\n'.join(lines[:max_lines]) + f"\n\n... (共 {len(lines)} 行, 显示前 {max_lines} 行)"
            elif len(text) > 15000:
                text = text[:15000] + f"\n\n... (共 {size/1024:.1f}KB, 显示前 15KB)"
            return f"[文件: {fp.name}  ({size/1024:.1f}KB, {len(lines)}行)]\n{text}"
        except Exception as e:
            return f"[读取失败] {e}"

    def _cmd_read(self, filepath):
        if not self._perm_check("file_read", "文件读取"):
            return
        if not filepath:
            self._show_lines(["  用法: /read <文件路径>  — 读取文件内容"], "dim")
            return
        content = self._read_file(filepath)
        self._show_lines([content], "dim")
        self._send_raw(f"用户提供了以下文件内容，请根据内容回答用户可能想问的问题。\n\n{content}")

    # ======== File Write / Delete ========

    def _cmd_write(self, arg):
        """/write <文件路径> — 写入/创建文件（弹出内容编辑框）。"""
        if not self._perm_check("file_create", "文件创建"):
            return
        if not arg:
            self._show_lines(["  用法: /write <文件路径>  — 创建或覆盖文件"], "dim")
            return
        fp = Path(arg)
        dlg = tk.Toplevel(self)
        dlg.title(f"写入文件: {fp.name}")
        dlg.geometry("550x350")
        dlg.configure(bg="#1a1a2e")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"路径: {fp}", bg="#1a1a2e", fg="#8888cc",
                 font=("Consolas", 9)).pack(padx=16, pady=(12, 4), anchor="w")

        txt = tk.Text(dlg, bg="#1a1a1a", fg="#c0c0d0", font=("Consolas", 10),
                      relief="flat", borderwidth=0, height=10, wrap="word",
                      insertbackground="#88ff88")
        txt.pack(fill="both", expand=True, padx=16, pady=4)
        txt.focus()

        def do_save():
            content = txt.get("1.0", "end-1c")
            try:
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                self._show_lines([f"  ✓ 已写入: {fp}  ({len(content)} 字符)"], "dim")
            except Exception as e:
                self._show_lines([f"  [!] 写入失败: {e}"], "error")
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))
        tk.Button(btn_frame, text="取消", bg="#222244", fg="#888888",
                  font=("Consolas", 9), relief="flat", padx=16, pady=4,
                  command=dlg.destroy).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="保存", bg="#1a4a1a", fg="#88ff88",
                  font=("Consolas", 9, "bold"), relief="raised", bd=2,
                  padx=24, pady=4, cursor="hand2",
                  command=do_save).pack(side="right")
        txt.bind("<Control-Return>", lambda e: do_save())

    def _cmd_delete(self, arg):
        """/delete <文件路径> — 删除文件（需确认）。"""
        if not self._perm_check("file_delete", "文件删除"):
            return
        if not arg:
            self._show_lines(["  用法: /delete <文件路径>  — 删除文件"], "dim")
            return
        fp = Path(arg)
        if not fp.exists():
            self._show_lines([f"  [!] 文件不存在: {fp}"], "error")
            return
        dlg = tk.Toplevel(self)
        dlg.title("确认删除")
        dlg.geometry("400x150")
        dlg.configure(bg="#1a1a2e")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"确定要删除以下文件？", bg="#1a1a2e", fg="#ff8888",
                 font=("Consolas", 10, "bold")).pack(pady=(16, 4))
        tk.Label(dlg, text=str(fp), bg="#1a1a2e", fg="#c0c0d0",
                 font=("Consolas", 9), wraplength=350).pack(pady=(0, 12))

        def do_delete():
            try:
                fp.unlink()
                self._show_lines([f"  ✓ 已删除: {fp}"], "dim")
            except Exception as e:
                self._show_lines([f"  [!] 删除失败: {e}"], "error")
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))
        tk.Button(btn_frame, text="取消", bg="#222244", fg="#888888",
                  font=("Consolas", 9), relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="确认删除", bg="#4a1a1a", fg="#ff8888",
                  font=("Consolas", 9, "bold"), relief="raised", bd=2,
                  padx=24, cursor="hand2",
                  command=do_delete).pack(side="right")

    def _cmd_mkdir(self, arg):
        """/mkdir <文件夹路径> — 创建文件夹。"""
        if not self._perm_check("file_create", "文件创建"):
            return
        if not arg:
            self._show_lines(["  用法: /mkdir <文件夹路径>  — 创建文件夹"], "dim")
            return
        fp = Path(arg)
        try:
            fp.mkdir(parents=True, exist_ok=True)
            self._show_lines([f"  ✓ 文件夹已创建: {fp}"], "dim")
        except Exception as e:
            self._show_lines([f"  [!] 创建失败: {e}"], "error")

    def _cmd_exec(self, arg):
        """/exec <命令> — 执行 shell 命令。"""
        if not self._perm_check("shell_exec", "命令执行"):
            return
        if not arg:
            self._show_lines(["  用法: /exec <命令>  — 执行 shell 命令"], "dim")
            return
        # 确认对话框
        dlg = tk.Toplevel(self)
        dlg.title("确认执行命令")
        dlg.geometry("520x200")
        dlg.configure(bg="#1a1a2e")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="将要执行以下命令：", bg="#1a1a2e", fg="#ffcc44",
                 font=("Consolas", 10, "bold")).pack(pady=(14, 4))
        tk.Label(dlg, text=arg, bg="#1a1a2e", fg="#c0c0d0",
                 font=("Consolas", 9), wraplength=480).pack(pady=(0, 12))
        tk.Label(dlg, text="确认后命令将立即执行", bg="#1a1a2e", fg="#666688",
                 font=("Consolas", 8)).pack(pady=(0, 4))

        def do_exec():
            dlg.destroy()
            self._show_lines([f"  $ {arg}\n"], "dim")
            try:
                import subprocess
                result = subprocess.run(arg, shell=True, capture_output=True, text=True, timeout=30)
                out = result.stdout.strip()
                err = result.stderr.strip()
                output = ""
                if out:
                    output += out + "\n"
                if err:
                    output += f"[stderr]\n{err}\n"
                output += f"➜ 退出码: {result.returncode}"
                self._show_lines([output], "dim")
            except subprocess.TimeoutExpired:
                self._show_lines(["  [!] 命令执行超时 (30s)"], "error")
            except Exception as e:
                self._show_lines([f"  [!] 执行失败: {e}"], "error")

        btn_frame = tk.Frame(dlg, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=16, pady=(4, 14))
        tk.Button(btn_frame, text="取消", bg="#222244", fg="#888888",
                  font=("Consolas", 9), relief="flat", padx=16,
                  command=dlg.destroy).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="确认执行", bg="#4a1a1a", fg="#ff8888",
                  font=("Consolas", 9, "bold"), relief="raised", bd=2,
                  padx=24, cursor="hand2",
                  command=do_exec).pack(side="right")

    # ======== Intent Detection ========

    def _detect_intent(self, text):
        paths = re.findall(r'[A-Za-z]:\\(?:[^\s\\]+\\)*[^\s\\]+', text)
        read_kw = ("读", "读取", "打开", "查看")
        if paths and any(kw in text for kw in read_kw):
            return ("read", paths)
        search_kw = ("搜索", "搜一下", "搜搜", "查一下", "查查", "查一查", "帮我查")
        if not paths:
            for kw in search_kw:
                idx = text.find(kw)
                if idx != -1:
                    query = text[idx + len(kw):].strip().rstrip("，。？！,?!")
                    if query:
                        return ("search", query)
        return None

    def _handle_intent(self, intent, original_text):
        intent_type, data = intent
        if intent_type == "read":
            paths = data
            contents = []
            for p in paths:
                content = self._read_file(p)
                self._show_lines([content], "dim")
                contents.append(content)
            combined = "\n\n---\n\n".join(contents)
            self._show_lines([f"  共读取 {len(paths)} 个文件, 发送给 AI 分析..."], "dim")
            self._send_raw(f"用户读取了以下文件内容:\n\n{combined}\n\n原始消息: {original_text}\n请基于文件内容回答用户。")
        elif intent_type == "search":
            query = data
            self._show_lines([f"  搜索: {query}"], "dim")
            result = self._search_web(query)
            self._show_lines([result], "dim")
            if "搜索失败" not in result and "不可用" not in result:
                self._send_raw(f"用户想了解: {query}\n\n搜索结果:\n{result}\n\n请基于这些信息回答。")

    # ======== Knowledge Base Commands ========

    def _cmd_kb(self, arg):
        if not self.kb:
            self._show_lines(["  [!] 知识库加载失败"], "error")
            return
        if not arg:
            self._show_lines(["  /kb index <路径>  — 索引文件/目录", "  /kb search <词>   — 搜索知识库", "  /kb status        — 查看状态"], "dim")
            return
        parts = arg.split(None, 1)
        sub = parts[0]
        param = parts[1] if len(parts) > 1 else ""

        if sub == "status":
            self._show_lines([f"  {self.kb.status()}"], "dim")
        elif sub == "index":
            if not self._perm_check("kb_index", "知识库索引"):
                return
            if not param:
                self._show_lines(["  用法: /kb index <文件或目录路径>"], "dim")
                return
            p = Path(param)
            result = self.kb.index_directory(param) if p.is_dir() else self.kb.index_file(param)
            self._show_lines([f"  {result}"], "dim")
        elif sub == "search":
            if not self._perm_check("kb_search", "知识库搜索"):
                return
            if not param:
                self._show_lines(["  用法: /kb search <关键词>"], "dim")
                return
            results = self.kb.search(param)
            if not results:
                self._show_lines(["  知识库无匹配"], "dim")
                return
            lines = [f"  知识库匹配 ({len(results)}):"]
            for score, r in results:
                src = Path(r["source"]).name
                lines.append(f"    [{src}] {r['text'][:120]}")
            self._show_lines(lines, "dim")
        else:
            self._show_lines([f"  未知子命令: {sub}"], "dim")

    # ======== Plan System ========

    def _cmd_plan(self, arg):
        if not arg:
            self._show_lines(["  用法: /plan <任务>  — 多步规划执行"], "dim")
            return
        self._show_lines(["  正在制定计划..."], "dim")
        self._send_raw(f"请为以下任务制定一个详细的执行计划，输出 [计划]...[/计划] 格式。\n\n任务: {arg}")

    def _check_for_plan(self):
        if self.active_plan or not self.stream_text:
            return False
        match = re.search(r'\[计划\](.*?)\[/计划\]', self.stream_text, re.DOTALL)
        if not match:
            return False
        steps = []
        for line in match.group(1).strip().split('\n'):
            line = line.strip()
            cleaned = re.sub(r'^[\d\.\-\*\[\]]+\s*', '', line).strip()
            if cleaned and len(cleaned) > 3:
                steps.append(cleaned)
        if len(steps) < 2:
            return False
        self._show_plan_ui(steps)
        return True

    def _show_plan_ui(self, steps):
        if self.plan_frame:
            self.plan_frame.destroy()
        self.text.configure(state="normal")
        self.text.insert("end", "\n  ── 检测到计划 ──\n", "thinking_label")
        self.text.configure(state="disabled")
        self.text.see("end")

        self.input.configure(state="disabled")
        self.send_btn.configure(state="disabled")
        self.plan_status.configure(text="等待确认...")

        frame = tk.Frame(self._container, bg="#1a1a2e", highlightbackground="#4444aa",
                         highlightthickness=2, highlightcolor="#4444aa",
                         relief="solid", bd=0)
        frame.pack(fill="x", before=self.bottom_frame)
        self.plan_frame = frame

        tk.Label(frame, text="  ═════ 执行计划 ═════", bg="#1a1a2e", fg="#8888ff",
                 font=("Consolas", 11, "bold")).pack(anchor="w", padx=16, pady=(10, 4))
        for i, step in enumerate(steps, 1):
            tk.Label(frame, text=f"    {i}. {step}", bg="#1a1a2e", fg="#c0c0d0",
                     font=("Consolas", 10), wraplength=600, justify="left").pack(anchor="w", padx=16, pady=2)

        btn_frame = tk.Frame(frame, bg="#1a1a2e")
        btn_frame.pack(pady=(10, 12))
        tk.Button(btn_frame, text="▶ 全部执行", bg="#1a4a1a", fg="#88ff88",
                  font=("Consolas", 11, "bold"), relief="raised", bd=2,
                  padx=28, pady=6,
                  cursor="hand2", activebackground="#2a6a2a", activeforeground="#ccffcc",
                  highlightbackground="#44aa44", highlightthickness=1,
                  command=lambda: self._start_plan(steps)).pack(side="left", padx=10)
        tk.Button(btn_frame, text="✕ 取消", bg="#4a1a1a", fg="#ff8888",
                  font=("Consolas", 11, "bold"), relief="raised", bd=2,
                  padx=28, pady=6,
                  cursor="hand2", activebackground="#6a2a2a", activeforeground="#ffcccc",
                  highlightbackground="#aa4444", highlightthickness=1,
                  command=self._cancel_plan).pack(side="left", padx=10)

    def _start_plan(self, steps):
        self.active_plan = {"steps": steps, "step_idx": 0, "results": []}
        if self.plan_frame:
            self.plan_frame.destroy()
            self.plan_frame = None
        self.plan_status.configure(text="计划执行中...")
        self._show_lines([f"  开始执行 {len(steps)} 步计划"], "dim")
        self._execute_next_step()

    def _cancel_plan(self):
        self.active_plan = None
        if self.plan_frame:
            self.plan_frame.destroy()
            self.plan_frame = None
        self.plan_status.configure(text="")
        self.input.configure(state="normal")
        self.send_btn.configure(state="normal", text="发送")
        self._show_lines(["  计划已取消"], "dim")

    def _execute_next_step(self):
        if not self.active_plan:
            return
        step_idx = self.active_plan["step_idx"]
        if step_idx >= len(self.active_plan["steps"]):
            self._finish_plan()
            return
        step = self.active_plan["steps"][step_idx]
        self.active_plan["step_idx"] += 1

        if step.startswith("搜索") and ("：" in step or ":" in step):
            sep = "：" if "：" in step else ":"
            query = step.split(sep, 1)[-1].strip()
            self._show_lines([f"  [搜索] {query}"], "dim")
            result = self._search_web(query)
            self._show_lines([result], "dim")
            self.active_plan["results"].append(f"[搜索] {query}\n{result[:300]}")
            self._execute_next_step()
            return

        read_kw = ("读取文件", "读取", "读文件", "打开文件")
        if any(kw in step for kw in read_kw) and ("：" in step or ":" in step):
            sep = "：" if "：" in step else ":"
            idx = -1
            for kw in read_kw:
                i = step.find(kw)
                if i != -1:
                    idx = i + len(kw)
                    break
            if idx != -1 and (step[idx:].startswith("：") or step[idx:].startswith(":")):
                path = step[idx+1:].strip()
                self._show_lines([f"  [读文件] {path}"], "dim")
                result = self._read_file(path)
                self._show_lines([result], "dim")
                self.active_plan["results"].append(f"[文件] {path}\n({len(result)} 字符)")
                self._execute_next_step()
                return

        step_num = self.active_plan["step_idx"]
        total = len(self.active_plan["steps"])
        prompt = f"[计划] 第 {step_num}/{total} 步\n任务: {step}\n"
        if self.active_plan["results"]:
            prompt += "\n已完成步骤:\n"
            for i, r in enumerate(self.active_plan["results"], 1):
                prompt += f"  步骤{i}: {r[:200]}\n"
        prompt += "\n请执行这一步，输出具体结果。"
        self._show_lines([f"  >> 第 {step_num}/{total} 步: {step}"], "dim")
        self._send_raw(prompt, save_history=False)

    def _finish_plan(self):
        results = self.active_plan["results"] if self.active_plan else []
        self._show_lines([f"  计划完成! 共 {len(results)} 步。"], "dim")
        self.active_plan = None
        self.plan_status.configure(text="")
        self.input.configure(state="normal")
        self.send_btn.configure(state="normal", text="发送")

    def _send_raw(self, text, system_prompt=None, save_history=True):
        if not self.started:
            self.started = True
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")
        self.is_streaming = True
        self.stop_btn.pack(side="right", padx=(0, 2))
        self.input.configure(state="disabled")
        self.send_btn.configure(state="disabled", text="...")
        self.stream_text = ""
        self.in_code_block = False
        self.retry_btn.configure(fg="#333333")
        self.edit_btn.configure(fg="#333333")
        t = threading.Thread(target=self._stream, args=(text, system_prompt, save_history), daemon=True)
        t.start()

    # ======== Chat ========

    def _send(self):
        text = self.input.get("1.0", "end-1c")
        if not text.strip() or self.is_streaming:
            return
        self.input.delete("1.0", "end")

        if text.startswith("/"):
            cmd_line = text[1:].strip()
            if cmd_line == "help":
                self._cmd_help()
            elif cmd_line == "mem list":
                self._cmd_mem_list()
            elif cmd_line == "clear":
                self._cmd_clear()
            elif cmd_line == "status":
                self._cmd_status()
            elif cmd_line == "model":
                self._cmd_model("")
            elif cmd_line == "models":
                self._cmd_models()
            elif cmd_line.startswith("search "):
                if not self._perm_check("web_search", "网络搜索"):
                    return
                query = cmd_line[7:]
                self._show_lines([f"  搜索: {query}"], "dim")
                result = self._search_web(query)
                self._show_lines([result], "dim")
                if "搜索失败" not in result and "不可用" not in result:
                    self._send_raw(f"用户想了解: {query}\n\n搜索到以下信息:\n{result}\n\n请基于这些信息回答。")
            elif cmd_line.startswith("read "):
                self._cmd_read(cmd_line[5:])
            elif cmd_line.startswith("write "):
                self._cmd_write(cmd_line[6:])
            elif cmd_line.startswith("delete "):
                self._cmd_delete(cmd_line[7:])
            elif cmd_line.startswith("mkdir "):
                self._cmd_mkdir(cmd_line[6:])
            elif cmd_line.startswith("exec "):
                self._cmd_exec(cmd_line[5:])
            elif cmd_line.startswith("plan "):
                self._cmd_plan(cmd_line[5:])
            elif cmd_line.startswith("kb "):
                self._cmd_kb(cmd_line[3:])
            elif cmd_line == "exit":
                self.destroy()
            elif cmd_line.startswith("mem add "):
                self._cmd_mem_add(cmd_line[8:])
            elif cmd_line.startswith("mem del "):
                self._cmd_mem_del(cmd_line[8:])
            elif cmd_line == "history":
                self._show_history_dialog()
            elif cmd_line in ("new", "新对话"):
                self._new_conversation()
            elif cmd_line.startswith("rename "):
                self._rename_conversation(cmd_line[7:])
            elif cmd_line == "export":
                self._cmd_export()
            elif cmd_line.startswith("theme"):
                arg = cmd_line[6:].strip() if len(cmd_line) > 6 else None
                self._cmd_theme(arg)
            elif cmd_line in ("prompt", "system"):
                self._show_prompt_editor()
            elif cmd_line.startswith("model "):
                self._cmd_model(cmd_line[6:])
            elif cmd_line == "provider":
                self._cmd_provider("")
            elif cmd_line.startswith("provider "):
                self._cmd_provider(cmd_line[9:])
            elif cmd_line.startswith("key "):
                self._cmd_key(cmd_line[4:])
            else:
                self._show_lines([f"  未知命令: {cmd_line}"], "dim")
            return

        intent = self._detect_intent(text)
        if intent:
            self._handle_intent(intent, text)
            return

        if not self.started:
            self.started = True
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")

        if self.conversation_title == "新对话":
            self.conversation_title = text.strip()[:60]

        self.last_exchange_start = self.text.index("end-1c")
        ts = datetime.now().strftime("%H:%M")
        self.text.configure(state="normal")
        self.text.insert("end", "\n", "separator")
        self.text.insert("end", f"  ══ {ts} ══\n", "timestamp")
        self.text.insert("end", " > ", "user_label")
        self.text.insert("end", text + "\n", "user_msg")
        self.text.configure(state="disabled")
        self.text.see("end")

        self.is_streaming = True
        self.stop_btn.pack(side="right", padx=(0, 2))
        self.input.configure(state="disabled")
        self.send_btn.configure(state="disabled", text="...")
        self.stream_text = ""
        self.in_code_block = False
        self.retry_btn.configure(fg="#333333")
        self.edit_btn.configure(fg="#333333")

        t = threading.Thread(target=self._stream, args=(text,), daemon=True)
        t.start()

    def _stream(self, user_text, system_prompt=None, save_history=True):
        try:
            sp = system_prompt if system_prompt is not None else self._build_system_prompt(user_text)
            full = [{"role": "system", "content": sp}]
            if save_history:
                full.extend(self.messages)
            full.append({"role": "user", "content": user_text})

            self.stream_start_time = 0
            self.completion_tokens = 0
            self.prompt_tokens = 0
            in_thinking = False

            self.after(0, self._agent_start)

            config = self._provider_config()
            tools_list = get_openai_tools() if self.provider in ("local", "openai") else None

            # 工具调用循环：最多 5 轮深度
            max_rounds = 5
            for _round in range(max_rounds):
                if self._stop_requested:
                    break
                if _round > 0:
                    # 从第二轮开始，带上上一轮的工具结果重新请求
                    full.append({"role": "user", "content": "请基于工具返回的结果继续。"})

                if self.provider in ("local", "openai"):
                    stream_gen = providers.stream_openai(full, config, tools=tools_list)
                elif self.provider == "anthropic":
                    stream_gen = providers.stream_anthropic(full, config)
                else:
                    raise ValueError(f"未知 provider: {self.provider}")

                tool_calls = None
                collected_content = ""

                for content, reasoning, usage, tc in stream_gen:
                    if self._stop_requested:
                        break
                    if tc:
                        tool_calls = tc
                        break
                    if reasoning:
                        if not in_thinking:
                            in_thinking = True
                            self.after(0, self._thinking_start)
                        self.after(0, self._thinking_append, reasoning)
                        continue
                    if content:
                        if in_thinking:
                            in_thinking = False
                            self.after(0, self._thinking_end)
                        if self.stream_start_time == 0:
                            self.stream_start_time = time.time()
                        collected_content += content
                        self.stream_text += content
                        self.completion_tokens += 1
                        self.after(0, self._agent_append, content)
                        self.after(0, self._update_stats)
                    if usage:
                        self.completion_tokens = usage.get("completion_tokens", self.completion_tokens)
                        self.prompt_tokens = usage.get("prompt_tokens", self.prompt_tokens)
                        self.total_tokens = usage.get("total_tokens", self.prompt_tokens + self.completion_tokens)
                        self.after(0, self._update_stats)

                if in_thinking:
                    self.after(0, self._thinking_end)
                    in_thinking = False

                if tool_calls:
                    # 执行工具调用
                    self.after(0, self._show_lines,
                               [f"  [工具调用] 模型请求 {len(tool_calls)} 个工具"], "dim")
                    tool_results = []
                    full.append({"role": "assistant", "content": collected_content,
                                 "tool_calls": [{
                                     "id": tc["id"],
                                     "type": "function",
                                     "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}
                                 } for tc in tool_calls]})
                    for tc in tool_calls:
                        self.after(0, self._show_lines,
                                   [f"  → 执行: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)[:100]})"], "dim")
                        result = execute_tool(tc["name"], tc["arguments"], app=self)
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                        self.after(0, self._show_lines,
                                   [f"  ← 结果: {result[:100]}"], "dim")
                    full.extend(tool_results)
                    collected_content = ""
                    continue  # 下一轮，让模型基于工具结果继续回复

                # 没有工具调用，流式输出结束
                break

            if self.completion_tokens == 0 and self.stream_text:
                self.completion_tokens = max(1, len(self.stream_text) // 3)
            self.after(0, self._update_stats)

            if save_history and self.stream_text:
                self.messages.append({"role": "user", "content": user_text})
                self.messages.append({"role": "assistant", "content": self.stream_text})
                if len(self.messages) > 60:
                    self.messages = self.messages[-60:]

            self.after(0, self._stream_done)

        except providers.ProviderError as e:
            self.after(0, self._stream_error, str(e))
        except requests.exceptions.ConnectionError:
            self.after(0, self._stream_error, "无法连接到模型后端")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 401:
                self.after(0, self._stream_error, "API 密钥无效 (401)")
            elif status == 429:
                self.after(0, self._stream_error, "请求过于频繁 (429)")
            else:
                self.after(0, self._stream_error, f"HTTP {status}: {e}")
        except Exception as e:
            self.after(0, self._stream_error, str(e))

    def _agent_start(self):
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M")
        self.text.insert("end", f"  [{ts}] ", "timestamp")
        self.text.insert("end", "  ", "agent_label")
        self.text.configure(state="disabled")
        self.text.see("end")

    def _agent_append(self, delta):
        self.text.configure(state="normal")
        parts = re.split(r'(```)', delta)
        for part in parts:
            if part == '```':
                self.in_code_block = not self.in_code_block
                self.text.insert("end", part, "code_fence")
            elif self.in_code_block:
                self.text.insert("end", part, "code_block")
            else:
                self.text.insert("end", part, "agent_msg")
        self.text.configure(state="disabled")
        self.text.see("end")

    def _stop_stream(self):
        """中断当前流式生成"""
        self._stop_requested = True
        self._stream_cleanup()
        self.after(0, self._show_lines, ["  ⏹ 已停止"], "dim")

    def _stream_cleanup(self):
        """流结束后恢复 UI 状态（共用）。"""
        self.is_streaming = False
        self.stop_btn.pack_forget()

    def _stream_done(self):
        self._stream_cleanup()
        if self.active_plan:
            if self.stream_text:
                self.active_plan["results"].append(self.stream_text)
            self.text.configure(state="normal")
            self.text.insert("end", "\n", "separator")
            self.text.configure(state="disabled")
            self.after(500, self._execute_next_step)
            return

        self.text.configure(state="normal")
        self.text.insert("end", "\n", "separator")
        self.text.configure(state="disabled")

        if len(self.messages) >= 2:
            self.retry_btn.configure(fg="#888888")
            self.edit_btn.configure(fg="#e8c84a")
        self.can_retry = True

        if not self._check_for_plan():
            self.input.configure(state="normal")
            self.send_btn.configure(state="normal", text="发送")
            self.input.focus()

        self._save_conversation()

        if self.total_tokens > self.compression_threshold and len(self.messages) >= 6 and not self.context_summary:
            self._compress_context()

    def _stream_error(self, msg):
        self.text.configure(state="normal")
        self.text.insert("end", f"\n[!] {msg}\n", "error")
        self.text.configure(state="disabled")
        self._stream_cleanup()
        self.input.configure(state="normal")
        self.send_btn.configure(state="normal", text="发送")
        self.input.focus()
        if self.active_plan:
            self.active_plan = None
            self.plan_status.configure(text="")

    def _start_backend(self, model_name=None):
        """启动 llama-server。可指定模型名，默认自动选第一个。"""
        exe = "llama-server"
        models_dir = Path(__file__).parent / "models"

        model_path = None
        if model_name:
            fp = models_dir / model_name
            if fp.exists():
                model_path = fp
        if not model_path:
            all_models = list(models_dir.glob("*.gguf"))
            if not all_models:
                self._show_lines(["  [!] 未找到模型文件"], "error")
                return
            model_path = all_models[0]

        self._stop_backend()
        self.current_model = model_path.name
        self.after(0, self._refresh_model_btn)
        self.after(0, self._update_prov_tabs)
        self._save_config({"model": model_path.name})

        logfile = open(MEMORY_DIR.parent / "llama.log", "w")
        self.llama_proc = subprocess.Popen(
            [exe, "-m", str(model_path), "-ngl", "999", "-c", "8192",
             "--port", str(LLAMA_PORT), "--temp", "0.7"],
            stdout=logfile, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logfile.close()
        self._show_lines([f"  启动: {model_path.name}"], "dim")
        self.after(5000, self._check_status)


if __name__ == "__main__":
    app = App()

    # Keybindings
    app.input.bind("<Control-c>", lambda e: app.destroy())
    app.bind("<Control-f>", lambda e: app._toggle_search())
    app.bind("<Control-F>", lambda e: app._toggle_search())

    # Right-click menu
    menu = tk.Menu(app, bg="#1a1a1a", fg=COLOR_FG, font=FONT_SMALL)
    menu.add_command(label="切换 Provider / 模型", command=lambda: app._switch_provider_dialog())
    menu.add_command(label="列出模型", command=lambda: app._cmd_models())
    menu.add_separator()
    menu.add_command(label="本地模型", command=lambda: app._cmd_provider("local"))
    menu.add_command(label="OpenAI API", command=lambda: app._cmd_provider("openai"))
    menu.add_command(label="Anthropic API", command=lambda: app._cmd_provider("anthropic"))
    menu.add_separator()
    menu.add_command(label="权限设置", command=app._show_permissions_dialog)
    menu.add_command(label="重启后端", command=lambda: app._start_backend())
    menu.add_command(label="检查状态", command=app._check_status)
    menu.add_separator()
    menu.add_command(label="退出", command=app.destroy)

    def show_menu(event):
        menu.post(event.x_root, event.y_root)
    app.bind("<Button-3>", show_menu)

    app.mainloop()
