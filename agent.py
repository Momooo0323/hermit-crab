#!/usr/bin/env python3
"""
Local Agent — 你的本地 AI 助手，带持久记忆系统。
运行在 llama.cpp server 或 Ollama 后端上。

用法:
  1. 先启动模型:  llama-server -m model.gguf -ngl 999 -c 8192
  2. 运行本 agent: python agent.py

记忆命令:
  /remember <名字> <描述>   — 保存一条关于你的信息
  /forget <名字>            — 删除一条记忆
  /list                     — 查看所有记忆
  /help                     — 显示帮助
  /exit                     — 退出

记忆会持久保存在 memory/ 目录中，下次启动自动加载。
"""

import json
import os
import sys
import time
import re
from datetime import datetime
from pathlib import Path

import requests

from app.memory import MEMORY_DIR, MEMORY_INDEX, load_memories, save_memory, delete_memory, ensure_dirs

# ============================================================
#  配置
# ============================================================

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "api_base": "http://localhost:8080/v1",
    "model": "gpt-3.5-turbo",
    "temperature": 0.7,
    "max_tokens": 4096,
    "system_prompt": (
        "你是 Agent，一个 helpful AI 助手。你有持久的记忆系统，"
        "能记住关于用户的信息。回答保持简洁、有帮助。"
    ),
}


def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            user_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config.update(user_config)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        # 首次启动：从 example 自动复制
        example = CONFIG_FILE.with_name("config.example.json")
        if example.exists():
            import shutil
            shutil.copy2(example, CONFIG_FILE)
            print(f"[config] 已从 config.example.json 创建 {CONFIG_FILE.name}")
            config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return config


def save_config(config):
    CONFIG_FILE.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_memory_context(memories):
    if not memories:
        return ""
    parts = ["\n## 关于用户的信息："]
    for name, mem in memories.items():
        parts.append(f"- {mem['description']}")
        if mem["content"]:
            truncated = mem["content"][:200]
            if len(mem["content"]) > 200:
                truncated += "..."
            parts.append(f"  -> {truncated}")
    return "\n".join(parts)


# ============================================================
#  LLM 客户端（OpenAI 兼容 API）
# ============================================================

def _api_url(base):
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def chat_completion(messages, config, stream=True):
    url = _api_url(config["api_base"])

    payload = {
        "model": config.get("model", "gpt-3.5-turbo"),
        "messages": messages,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 2048),
        "stream": stream,
    }

    headers = {"Content-Type": "application/json"}
    timeout = config.get("timeout", 120)

    try:
        response = requests.post(
            url, json=payload, headers=headers, stream=stream, timeout=timeout
        )
        response.raise_for_status()

        if stream:
            return _handle_stream(response)
        else:
            data = response.json()
            return data["choices"][0]["message"]["content"]

    except requests.exceptions.ConnectionError:
        print(f"\n[!] 无法连接到 {config['api_base']}")
        print("    请确保模型后端已启动！例如：")
        print("    llama-server -m model.gguf -ngl 999 -c 8192")
        return None
    except requests.exceptions.Timeout:
        print("\n[!] 请求超时，模型可能仍在加载或响应过慢。")
        return None
    except Exception as e:
        print(f"\n[!] 错误: {type(e).__name__}: {e}")
        return None


def _handle_stream(response):
    collected = ""
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue

        data_str = line[6:]
        if data_str == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                collected += content
                print(content, end="", flush=True)
        except json.JSONDecodeError:
            continue

    print()
    return collected


# ============================================================
#  CLI 主循环
# ============================================================

def show_help():
    print("""
  /remember <名字> <描述>    保存一条记忆（然后输入详细内容，空行结束）
  /forget <名字>             删除一条记忆
  /list                      列出所有记忆
  /config                    查看当前配置
  /model <名字>              切换到指定模型
  /help                      显示此帮助
  /exit                      退出
""")


def show_welcome(config, memories):
    print()
    print("=" * 60)
    print("  Local Agent -- 带记忆的本地 AI 助手")
    print("=" * 60)
    print(f"  API:     {config['api_base']}")
    print(f"  模型:    {config['model']}")
    print(f"  记忆数:  {len(memories)}")
    print("  /help 查看命令  /exit 退出")
    print("=" * 60)

    if memories:
        for name, mem in memories.items():
            print(f"  [{name}] {mem['description']}")
    print()


def main():
    config = load_config()
    ensure_dirs()
    memories = load_memories()

    show_welcome(config, memories)

    history = []

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # ----- Commands -----
        if user_input.startswith("/"):
            parts = user_input[1:].split(None, 1)
            cmd = parts[0].lower() if parts else ""
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "exit":
                print("再见！")
                break

            elif cmd == "help":
                show_help()
                continue

            elif cmd == "list":
                memories = load_memories()
                if not memories:
                    print("  还没有记忆。用 /remember 添加一条。")
                else:
                    print(f"  {len(memories)} 条记忆：")
                    for name, mem in memories.items():
                        print(f"    [{name}] {mem['description']}")
                        print(f"      {mem['content'][:120]}")
                continue

            elif cmd == "forget":
                if not arg:
                    print("  用法: /forget <名字>")
                    continue
                delete_memory(arg.strip())
                memories = load_memories()
                print(f"  已删除记忆: {arg}")
                continue

            elif cmd == "remember":
                sub = arg.split(None, 1)
                if not sub:
                    print("  用法: /remember <名字> <描述>")
                    print("         然后输入详细内容，空行结束输入")
                    continue
                name = sub[0]
                desc = sub[1] if len(sub) > 1 else name

                print(f"  输入 '{name}' 的详细内容（空行结束）：")
                content_lines = []
                while True:
                    try:
                        line = input()
                        if line == "":
                            break
                        content_lines.append(line)
                    except EOFError:
                        break
                content = "\n".join(content_lines).strip() or desc

                save_memory(name, desc, content)
                memories = load_memories()
                print(f"  已保存记忆: {name}")
                continue

            elif cmd == "config":
                print(f"\n  当前配置:")
                for k, v in config.items():
                    print(f"    {k}: {v}")
                print()
                continue

            elif cmd == "model":
                if not arg:
                    print(f"  当前模型: {config.get('model', '?')}")
                else:
                    config["model"] = arg.strip()
                    save_config(config)
                    print(f"  已切换模型: {config['model']}")
                continue

            else:
                print(f"  未知命令: /{cmd}。输入 /help 查看可用命令。")
                continue

        # ----- Normal conversation -----

        memory_text = _build_memory_context(memories)
        system_prompt = config.get("system_prompt", DEFAULT_CONFIG["system_prompt"])
        if memory_text:
            system_prompt += memory_text

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        print("\nAgent ", end="", flush=True)
        response = chat_completion(messages, config, stream=True)

        if response:
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})

            if len(history) > 30:
                history = history[-30:]

        print()


if __name__ == "__main__":
    main()
