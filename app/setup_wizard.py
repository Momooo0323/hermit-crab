"""
Hermit Crab First-Run Setup Wizard
多步配置向导，引导新用户完成初始设置。
Bilingual: 中文 / English.
"""

import tkinter as tk
from pathlib import Path
from app.themes import *
from app import providers


WIZARD_WIDTH = 600
WIZARD_HEIGHT = 540

# ── Translations ──────────────────────────────────────────────

TR = {
    "zh": {
        "title": "Hermit Crab 初始设置",
        "subtitle": "本地 AI 助手 — 设置向导",
        "welcome_msg": (
            "欢迎使用 Hermit Crab，一个运行在本地的 AI 桌面助手。\n\n"
            "本向导将帮助您完成初始设置：\n"
            "  ① 选择 AI 提供商\n"
            "  ② 配置 API 密钥或选择本地模型\n"
            "  ③ 确认设置并开始使用\n\n"
            "您随时可以通过 /provider 命令或右键菜单更改这些设置。"
        ),
        "step_title": "选择 AI 提供商",
        "local": "本地模型 (Local)",
        "openai": "OpenAI 兼容 API",
        "anthropic": "Anthropic Claude",
        "models_found": "在 models/ 目录中找到 {n} 个模型：",
        "no_models": "⚠ models/ 目录下没有找到 .gguf 模型文件。",
        "no_models_hint": "您可以稍后将模型放入 models/ 目录，然后通过 /model 命令切换。",
        "local_hint": "选择一个模型，或留空稍后设置。",
        "api_key": "API Key:",
        "base_url": "Base URL:",
        "model_opt": "模型 (可选):",
        "fetch_models": "获取模型列表",
        "toggle_show": "显示/隐藏",
        "no_models_api": "(无可用模型)",
        "fetch_fail_oa": "(获取失败，请检查 API Key 和 URL)",
        "fetch_fail_an": "(获取失败，请检查 API Key)",
        "summary_title": "设置摘要",
        "provider_label": "提供商",
        "model_label": "模型",
        "not_set": "(将稍后设置)",
        "not_set_key": "(未设置)",
        "back": "← 上一步",
        "next": "下一步 →",
        "start": "开始设置",
        "finish": "✔ 完成",
        "cancel": "取消",
    },
    "en": {
        "title": "Hermit Crab Setup",
        "subtitle": "Local AI Assistant — Setup Wizard",
        "welcome_msg": (
            "Welcome to Hermit Crab, a local AI desktop assistant.\n\n"
            "This wizard will help you get started:\n"
            "  ① Choose an AI provider\n"
            "  ② Configure API keys or select a local model\n"
            "  ③ Confirm and start using\n\n"
            "You can change these settings anytime via the /provider command or right-click menu."
        ),
        "step_title": "Choose AI Provider",
        "local": "Local Model",
        "openai": "OpenAI Compatible API",
        "anthropic": "Anthropic Claude",
        "models_found": "Found {n} model(s) in models/:",
        "no_models": "⚠ No .gguf model files found in models/.",
        "no_models_hint": "You can add models to models/ later and switch via the /model command.",
        "local_hint": "Select a model, or leave empty to set later.",
        "api_key": "API Key:",
        "base_url": "Base URL:",
        "model_opt": "Model (Optional):",
        "fetch_models": "Fetch Models",
        "toggle_show": "Show/Hide",
        "no_models_api": "(No models available)",
        "fetch_fail_oa": "(Failed — check API Key and URL)",
        "fetch_fail_an": "(Failed — check API Key)",
        "summary_title": "Setup Summary",
        "provider_label": "Provider",
        "model_label": "Model",
        "not_set": "(Will set later)",
        "not_set_key": "(Not set)",
        "back": "← Previous",
        "next": "Next →",
        "start": "Get Started",
        "finish": "✔ Finish",
        "cancel": "Cancel",
    },
}


def show_setup_wizard(parent, config_data):
    """显示首次运行设置向导（模态对话框）。"""
    dlg = tk.Toplevel(parent)
    dlg.geometry(f"{WIZARD_WIDTH}x{WIZARD_HEIGHT}")
    dlg.configure(bg=COLOR_BG)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    # Center on parent
    dlg.update_idletasks()
    px = parent.winfo_x()
    py = parent.winfo_y()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    x = px + (pw - WIZARD_WIDTH) // 2
    y = py + (ph - WIZARD_HEIGHT) // 2
    dlg.geometry(f"+{x}+{y}")

    # ── State ──
    lang = [config_data.get("language", "zh")]
    state = {
        "provider": tk.StringVar(value=config_data.get("provider", "local")),
        "model": tk.StringVar(value=config_data.get("model", "")),
        "openai_api_key": tk.StringVar(value=config_data.get("openai_api_key", "")),
        "openai_base_url": tk.StringVar(value=config_data.get("openai_base_url", "https://api.openai.com/v1")),
        "anthropic_api_key": tk.StringVar(value=config_data.get("anthropic_api_key", "")),
        "theme": tk.StringVar(value=config_data.get("theme", "default")),
    }
    # Widget references that survive rebuild
    w2 = {"local_listbox": None, "oa_listbox": None, "an_listbox": None}

    def T(key, **fmt):
        s = TR[lang[0]].get(key, key)
        if fmt:
            s = s.format(**fmt)
        return s

    result = {"cancelled": True}
    current_step = [0]
    total_steps = 3

    # Models scan (shared, survives rebuild)
    models_dir = Path(__file__).parent.parent / "models"
    model_files = sorted(models_dir.glob("*.gguf"))

    # ── Top bar: title + lang toggle ──
    top_bar = tk.Frame(dlg, bg=COLOR_BG)
    top_bar.pack(fill="x")
    title_lbl = tk.Label(top_bar, text="", bg=COLOR_BG, fg=COLOR_LABEL,
                          font=("Consolas", 9))
    title_lbl.pack(side="left", padx=16, pady=(8, 0))
    lang_btn = tk.Label(top_bar, text="", bg=COLOR_BG, fg="#8888ff",
                         font=("Consolas", 9, "bold"), cursor="hand2", padx=8)
    lang_btn.pack(side="right", padx=(0, 16), pady=(8, 0))

    def update_title():
        title_lbl.configure(text=f"🐚  {T('title')}")
        lang_btn.configure(text="EN/中" if lang[0] == "zh" else "中/EN")

    # ── Content area with step frames ──
    content = tk.Frame(dlg, bg=COLOR_BG)
    content.pack(fill="both", expand=True)
    steps = [tk.Frame(content, bg=COLOR_BG) for _ in range(total_steps)]

    # ── Helpers ──
    def _clear(fr):
        for w in fr.winfo_children():
            w.destroy()

    # ───── Step 1: Welcome ─────
    def build_step1():
        _clear(steps[0])
        f = steps[0]
        tk.Label(f, text="🐚 Hermit Crab", bg=COLOR_BG, fg=COLOR_LABEL,
                 font=("Consolas", 18, "bold")).pack(pady=(30, 4))
        tk.Label(f, text=T("subtitle"), bg=COLOR_BG, fg=COLOR_DIM,
                 font=("Consolas", 11)).pack(pady=(0, 20))
        tk.Label(f, text=T("welcome_msg"), bg=COLOR_BG, fg=COLOR_FG,
                 font=FONT, wraplength=480, justify="left").pack(pady=10)

    # ───── Step 2: Provider + config ─────
    def build_step2():
        _clear(steps[1])
        f = steps[1]

        tk.Label(f, text=T("step_title"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_BOLD).pack(anchor="w", padx=16, pady=(16, 8))

        prov_frame = tk.Frame(f, bg=COLOR_BG)
        prov_frame.pack(fill="x", padx=16, pady=4)

        def switch_prov():
            for ff in (local_f, oa_f, an_f):
                ff.pack_forget()
            p = state["provider"].get()
            {"local": local_f, "openai": oa_f, "anthropic": an_f}.get(p, local_f).pack(
                fill="both", expand=True)

        for p, _ in [("local", ""), ("openai", ""), ("anthropic", "")]:
            tk.Radiobutton(prov_frame, text=T(p), variable=state["provider"],
                           value=p, bg=COLOR_BG, fg=COLOR_LABEL,
                           selectcolor="#1a1a1a", font=FONT_SMALL,
                           command=switch_prov).pack(anchor="w", pady=2)

        tk.Frame(f, bg=COLOR_BORDER, height=1).pack(fill="x", padx=16, pady=6)

        prov_content = tk.Frame(f, bg=COLOR_BG)
        prov_content.pack(fill="both", expand=True, padx=16, pady=4)

        # -- Local --
        local_f = tk.Frame(prov_content, bg=COLOR_BG)
        if model_files:
            tk.Label(local_f, text=T("models_found", n=len(model_files)),
                     bg=COLOR_BG, fg=COLOR_LABEL, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))
            lf = tk.Frame(local_f, bg="#1a1a1a")
            lf.pack(fill="both", expand=True)
            w2["local_listbox"] = tk.Listbox(lf, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                                              selectbackground="#333366", relief="flat",
                                              borderwidth=0, highlightthickness=0)
            sc = tk.Scrollbar(lf, command=w2["local_listbox"].yview,
                              bg="#1a1a1a", troughcolor="#0d0d0d")
            w2["local_listbox"].configure(yscrollcommand=sc.set)
            sc.pack(side="right", fill="y")
            w2["local_listbox"].pack(side="left", fill="both", expand=True)
            current_name = state["model"].get()
            preselect = 0
            for i, mf in enumerate(model_files):
                size = mf.stat().st_size / (1024 ** 3)
                w2["local_listbox"].insert("end", f"  {mf.name:45s} {size:5.1f}GB")
                if mf.name == current_name:
                    preselect = i
            if model_files:
                w2["local_listbox"].selection_set(preselect)
                w2["local_listbox"].see(preselect)
        else:
            w2["local_listbox"] = None
            tk.Label(local_f, text=T("no_models"),
                     bg=COLOR_BG, fg=COLOR_YELLOW, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))
            tk.Label(local_f, text=T("no_models_hint"),
                     bg=COLOR_BG, fg=COLOR_DIM, font=FONT_SMALL).pack(anchor="w")
        tk.Label(local_f, text=T("local_hint"),
                 bg=COLOR_BG, fg=COLOR_DIM, font=("Consolas", 9)).pack(anchor="w", pady=(6, 2))

        # -- OpenAI --
        oa_f = tk.Frame(prov_content, bg=COLOR_BG)
        tk.Label(oa_f, text=T("api_key"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(4, 2))
        oa_key = tk.Entry(oa_f, bg="#1a1a1a", fg=COLOR_FG,
                          textvariable=state["openai_api_key"],
                          font=("Consolas", 10), relief="flat", borderwidth=6, show="*")
        oa_key.pack(fill="x", pady=(0, 4))

        def mk_toggle(e):
            return lambda: e.configure(show="" if e.cget("show") == "*" else "*")
        tk.Button(oa_f, text=T("toggle_show"), bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=mk_toggle(oa_key)).pack(anchor="e")

        tk.Label(oa_f, text=T("base_url"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(6, 2))
        tk.Entry(oa_f, bg="#1a1a1a", fg=COLOR_FG,
                 textvariable=state["openai_base_url"],
                 font=("Consolas", 10), relief="flat", borderwidth=6).pack(fill="x", pady=(0, 4))

        tk.Label(oa_f, text=T("model_opt"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(6, 2))
        oa_lf = tk.Frame(oa_f, bg="#1a1a1a")
        oa_lf.pack(fill="both", expand=True)
        w2["oa_listbox"] = tk.Listbox(oa_lf, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                                       selectbackground="#333366", relief="flat",
                                       borderwidth=0, highlightthickness=0, height=5)
        oa_sc = tk.Scrollbar(oa_lf, command=w2["oa_listbox"].yview,
                             bg="#1a1a1a", troughcolor="#0d0d0d")
        w2["oa_listbox"].configure(yscrollcommand=oa_sc.set)
        oa_sc.pack(side="right", fill="y")
        w2["oa_listbox"].pack(side="left", fill="both", expand=True)

        def fetch_oa():
            w2["oa_listbox"].delete(0, "end")
            try:
                ids = providers.list_openai_models({
                    "openai_api_key": state["openai_api_key"].get(),
                    "openai_base_url": state["openai_base_url"].get(),
                    "api_base": "",
                })
                if not ids:
                    w2["oa_listbox"].insert("end", T("no_models_api"))
                for mid in ids:
                    w2["oa_listbox"].insert("end", mid)
            except Exception:
                w2["oa_listbox"].insert("end", T("fetch_fail_oa"))
        tk.Button(oa_f, text=T("fetch_models"), bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=fetch_oa).pack(anchor="e", pady=(2, 0))

        # -- Anthropic --
        an_f = tk.Frame(prov_content, bg=COLOR_BG)
        tk.Label(an_f, text=T("api_key"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(4, 2))
        an_key = tk.Entry(an_f, bg="#1a1a1a", fg=COLOR_FG,
                          textvariable=state["anthropic_api_key"],
                          font=("Consolas", 10), relief="flat", borderwidth=6, show="*")
        an_key.pack(fill="x", pady=(0, 4))
        tk.Button(an_f, text=T("toggle_show"), bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=mk_toggle(an_key)).pack(anchor="e")

        tk.Label(an_f, text=T("model_opt"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_SMALL).pack(anchor="w", pady=(6, 2))
        an_lf = tk.Frame(an_f, bg="#1a1a1a")
        an_lf.pack(fill="both", expand=True)
        w2["an_listbox"] = tk.Listbox(an_lf, bg="#1a1a1a", fg=COLOR_FG, font=FONT,
                                       selectbackground="#333366", relief="flat",
                                       borderwidth=0, highlightthickness=0, height=5)
        an_sc = tk.Scrollbar(an_lf, command=w2["an_listbox"].yview,
                             bg="#1a1a1a", troughcolor="#0d0d0d")
        w2["an_listbox"].configure(yscrollcommand=an_sc.set)
        an_sc.pack(side="right", fill="y")
        w2["an_listbox"].pack(side="left", fill="both", expand=True)

        def fetch_an():
            w2["an_listbox"].delete(0, "end")
            try:
                ids = providers.list_anthropic_models({
                    "anthropic_api_key": state["anthropic_api_key"].get(),
                })
                if not ids:
                    w2["an_listbox"].insert("end", T("no_models_api"))
                for mid in ids:
                    w2["an_listbox"].insert("end", mid)
            except Exception:
                w2["an_listbox"].insert("end", T("fetch_fail_an"))
        tk.Button(an_f, text=T("fetch_models"), bg="#222", fg=COLOR_LABEL,
                  font=FONT_SMALL, relief="flat", command=fetch_an).pack(anchor="e", pady=(2, 0))

        # Show current provider
        switch_prov()

    # ───── Step 3: Summary ─────
    def build_step3():
        _clear(steps[2])
        f = steps[2]

        tk.Label(f, text=T("summary_title"), bg=COLOR_BG, fg=COLOR_LABEL,
                 font=FONT_BOLD).pack(anchor="w", padx=16, pady=(16, 8))

        sf = tk.Frame(f, bg="#1a1a1a", relief="flat", borderwidth=0)
        sf.pack(fill="both", expand=True, padx=16, pady=8)

        prov = state["provider"].get()
        prov_names = {"local": T("local"), "openai": T("openai"), "anthropic": T("anthropic")}
        tk.Label(sf, text=f"  {T('provider_label')}: {prov_names.get(prov, prov)}",
                 bg="#1a1a1a", fg=COLOR_LABEL, font=FONT,
                 anchor="w", justify="left").pack(fill="x", padx=16, pady=8)
        tk.Label(sf, text=f"  {T('model_label')}: {state['model'].get() or T('not_set')}",
                 bg="#1a1a1a", fg=COLOR_LABEL, font=FONT,
                 anchor="w", justify="left").pack(fill="x", padx=16, pady=4)

        if prov in ("openai", "anthropic"):
            key = state[f"{prov}_api_key"].get()
            masked = f"{key[:8]}..." if len(key) > 8 else T("not_set_key")
            tk.Label(sf, text=f"  API Key: {masked}",
                     bg="#1a1a1a", fg=COLOR_DIM, font=FONT_SMALL,
                     anchor="w", justify="left").pack(fill="x", padx=16, pady=4)

    # ───── Collect step2 values into state ─────
    def collect_step2():
        prov = state["provider"].get()
        if prov == "local":
            lb = w2["local_listbox"]
            if lb is not None:
                sel = lb.curselection()
                state["model"].set(model_files[sel[0]].name if sel else "")
        elif prov == "openai":
            lb = w2["oa_listbox"]
            if lb is not None:
                sel = lb.curselection()
                state["model"].set(lb.get(sel[0]) if sel else "")
        elif prov == "anthropic":
            lb = w2["an_listbox"]
            if lb is not None:
                sel = lb.curselection()
                state["model"].set(lb.get(sel[0]) if sel else "")

    # ───── Navigation ─────
    nav = tk.Frame(dlg, bg=COLOR_BG)
    nav.pack(fill="x", padx=16, pady=(8, 16))

    nav_back = tk.Button(nav, bg="#222", fg=COLOR_LABEL,
                          font=FONT_SMALL, relief="flat", padx=20)
    nav_next = tk.Button(nav, bg="#2a4a2a", fg=COLOR_GREEN,
                          font=FONT_SMALL, relief="flat", padx=20)
    nav_finish = tk.Button(nav, bg="#2a4a2a", fg=COLOR_GREEN,
                            font=("Consolas", 10, "bold"), relief="raised", bd=2, padx=28)
    nav_cancel = tk.Button(nav, bg="#4a1a1a", fg=COLOR_ERROR,
                            font=FONT_SMALL, relief="flat", padx=16)

    def show_step(idx):
        for i, fr in enumerate(steps):
            fr.pack_forget()
        steps[idx].pack(fill="both", expand=True)

        nav_back.pack_forget()
        nav_next.pack_forget()
        nav_finish.pack_forget()

        if idx > 0:
            nav_back.configure(text=T("back"))
            nav_back.pack(side="left", padx=(0, 8))
        nav_cancel.configure(text=T("cancel"))
        nav_cancel.pack(side="left")

        if idx == total_steps - 1:
            nav_finish.configure(text=T("finish"))
            nav_finish.pack(side="right", padx=(0, 8))
        else:
            nav_next.configure(text=T("start") if idx == 0 else T("next"))
            nav_next.pack(side="right", padx=(0, 8))

    def do_back():
        current_step[0] -= 1
        build_current_step()
        show_step(current_step[0])

    def do_next():
        if current_step[0] == 1:
            collect_step2()
        current_step[0] += 1
        build_current_step()
        show_step(current_step[0])

    def do_finish():
        collect_step2()
        prov = state["provider"].get()
        result["cancelled"] = False
        result["provider"] = prov
        result["model"] = state["model"].get()
        result["openai_api_key"] = state["openai_api_key"].get()
        result["openai_base_url"] = state["openai_base_url"].get()
        result["anthropic_api_key"] = state["anthropic_api_key"].get()
        result["theme"] = state["theme"].get()
        result["language"] = lang[0]
        result["setup_version"] = 1
        dlg.destroy()
        result["language"] = lang[0]
        dlg.destroy()

    def do_cancel():
        result["cancelled"] = True
        dlg.destroy()

    nav_back.configure(command=do_back)
    nav_next.configure(command=do_next)
    nav_finish.configure(command=do_finish)
    nav_cancel.configure(command=do_cancel)

    def toggle_lang():
        lang[0] = "en" if lang[0] == "zh" else "zh"
        update_title()
        collect_step2()  # preserve any unsaved entries
        build_current_step()
        show_step(current_step[0])

    def build_current_step():
        idx = current_step[0]
        [build_step1, build_step2, build_step3][idx]()

    lang_btn.bind("<Button-1>", lambda e: toggle_lang())
    update_title()
    build_step1()
    show_step(0)
    dlg.protocol("WM_DELETE_WINDOW", do_cancel)
    dlg.bind("<Escape>", lambda e: do_cancel())

    parent.wait_window(dlg)
    if result["cancelled"]:
        return None
    return {k: result[k] for k in (
        "provider", "model", "openai_api_key", "openai_base_url",
        "anthropic_api_key", "theme", "language", "setup_version",
    )}
