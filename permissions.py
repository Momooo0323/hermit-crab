"""
Hermit Crab — 权限控制模块。

管理 Agent 的各项操作权限，每个权限是一个 bool 开关。
权限状态持久化到 config.json。
"""

import tkinter as tk

# 所有可用权限定义
# (key, 显示名称, 说明, 默认值)
PERMISSION_DEFS = [
    ("file_read",     "文件读取",     "允许读取本地文件",        True),
    ("file_create",   "文件创建",     "允许创建和写入文件",      True),
    ("file_delete",   "文件删除",     "允许删除文件",            True),
    ("shell_exec",    "命令执行",     "允许执行 shell 命令",    False),
    ("memory_add",    "记忆添加",     "允许保存新记忆",          True),
    ("memory_delete", "记忆删除",     "允许删除已有记忆",        True),
    ("web_search",    "网络搜索",     "允许搜索网络信息",        True),
    ("kb_index",      "知识库索引",   "允许索引文件到知识库",    True),
    ("kb_search",     "知识库搜索",   "允许搜索知识库",          True),
    ("plan_execute",  "计划执行",     "允许执行多步计划",        True),
]


def default_permissions():
    """返回默认权限字典（全部开启）。"""
    return {key: default for key, _, _, default in PERMISSION_DEFS}


def merge_permissions(cfg_perms: dict | None) -> dict:
    """用配置中的权限覆盖默认值，保证新增字段不缺省。"""
    base = default_permissions()
    if cfg_perms:
        base.update(cfg_perms)
    return base


def check(perms: dict, key: str) -> bool:
    """检查某项权限是否开启，未知 key 默认允许。"""
    return perms.get(key, True)


def _toggle_color(bg_on="#1a4a1a", bg_off="#4a1a1a",
                  fg_on="#88ff88", fg_off="#ff8888"):
    """根据开关状态返回配色。"""
    return (bg_on, fg_on), (bg_off, fg_off)


def show_permission_dialog(parent, perms: dict, on_save) -> None:
    """弹出权限设置对话框，修改后调用 on_save(new_perms)。"""
    dlg = tk.Toplevel(parent)
    dlg.title("权限设置")
    dlg.geometry("520x500")
    dlg.configure(bg="#1a1a2e")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    work_perms = dict(perms)  # 本地副本

    # ── 标题 ──
    tk.Label(dlg,
             text="  🔐  权限控制  ",
             bg="#1a1a2e", fg="#8888ff",
             font=("Consolas", 13, "bold")
             ).pack(pady=(16, 4))
    tk.Label(dlg,
             text="关闭某项权限后，Agent 将无法执行对应操作",
             bg="#1a1a2e", fg="#666688",
             font=("Consolas", 9)
             ).pack(pady=(0, 12))

    # ── 开关列表 ──
    frame = tk.Frame(dlg, bg="#1a1a2e")
    frame.pack(fill="both", expand=True, padx=24, pady=(0, 8))

    widgets = {}  # key -> tk.Button

    def toggle(key):
        work_perms[key] = not work_perms[key]
        bg, fg = (_toggle_color()[0] if work_perms[key] else _toggle_color()[1])
        widgets[key].configure(bg=bg[0] if work_perms[key] else bg_off[0],
                                fg=fg[0] if work_perms[key] else fg_off[0],
                                text=" ✓ 开启" if work_perms[key] else " ✕ 关闭")

    bg_on, fg_on = _toggle_color()[0]
    bg_off, fg_off = _toggle_color()[1]

    for key, label, desc, _ in PERMISSION_DEFS:
        row = tk.Frame(frame, bg="#1a1a2e")
        row.pack(fill="x", pady=3)

        is_on = work_perms.get(key, True)
        btn = tk.Button(row,
                        text=" ✓ 开启" if is_on else " ✕ 关闭",
                        bg=bg_on if is_on else bg_off,
                        fg=fg_on if is_on else fg_off,
                        font=("Consolas", 9, "bold"),
                        relief="flat", bd=0, padx=10, pady=4,
                        cursor="hand2",
                        command=lambda k=key: toggle(k))
        btn.pack(side="left", padx=(0, 10))
        widgets[key] = btn

        info_frame = tk.Frame(row, bg="#1a1a2e")
        info_frame.pack(side="left", fill="x", expand=True)
        tk.Label(info_frame, text=label,
                 bg="#1a1a2e", fg="#c0c0d0",
                 font=("Consolas", 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(info_frame, text=desc,
                 bg="#1a1a2e", fg="#555566",
                 font=("Consolas", 8),
                 anchor="w").pack(fill="x")

    # ── 底部按钮 ──
    btn_frame = tk.Frame(dlg, bg="#1a1a2e")
    btn_frame.pack(fill="x", padx=24, pady=(4, 16))

    def save():
        on_save(work_perms)
        dlg.destroy()

    def reset():
        for key, _, _, default in PERMISSION_DEFS:
            work_perms[key] = default
            bg, fg = (_toggle_color()[0] if default else _toggle_color()[1])
            widgets[key].configure(bg=bg[0], fg=fg[0],
                                    text=" ✓ 开启" if default else " ✕ 关闭")

    tk.Button(btn_frame, text="重置默认", bg="#1a1a2e", fg="#666688",
              font=("Consolas", 9), relief="flat", padx=16, pady=6,
              cursor="hand2", command=reset
              ).pack(side="left")
    tk.Button(btn_frame, text="取消", bg="#222244", fg="#888888",
              font=("Consolas", 9), relief="flat", padx=16, pady=6,
              cursor="hand2", command=dlg.destroy
              ).pack(side="right", padx=(4, 0))
    tk.Button(btn_frame, text="保存", bg="#1a4a1a", fg="#88ff88",
              font=("Consolas", 9, "bold"), relief="raised", bd=2,
              padx=24, pady=6, cursor="hand2",
              activebackground="#2a6a2a", activeforeground="#ccffcc",
              highlightbackground="#44aa44", highlightthickness=1,
              command=save
              ).pack(side="right", padx=(0, 4))

    dlg.wait_window()
