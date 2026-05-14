"""
Hermit Crab — LLM Provider 模块
封装 OpenAI 兼容 API 和 Anthropic Claude API 的流式调用差异。

每个 stream 函数是一个 generator，每次 yield:
  (content: str, reasoning: str, usage: dict | None)
"""

import json
import requests
import re


class ProviderError(Exception):
    """Provider-specific error that desktop.py can catch and display."""
    pass


def _require_key(config, key_name, label):
    """Raise ProviderError if the given config key is empty."""
    if not config.get(key_name, ""):
        raise ProviderError(f"{label} 密钥未设置。使用 /key 命令或在设置对话框中配置。")


# ── helpers ──

def _base_url(config):
    """OpenAI 兼容的 base URL，含 /v1 前缀。"""
    url = config.get("openai_base_url", "") or config.get("api_base", "https://api.openai.com/v1")
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _headers(config):
    h = {"Content-Type": "application/json"}
    key = config.get("openai_api_key", "")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


# ── OpenAI 兼容（local 也用此格式）──

def stream_openai(messages, config):
    """
    OpenAI 兼容格式的流式调用。
    也用于 local llama-server（同一 wire format）。
    Yields: (content, reasoning, usage)
    """
    provider = config.get("provider", "")
    if provider != "local":
        _require_key(config, "openai_api_key", "OpenAI")

    payload = {
        "messages": messages,
        "stream": True,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 4096),
        "model": config.get("model", ""),
    }

    resp = requests.post(
        f"{_base_url(config)}/chat/completions",
        json=payload, stream=True, timeout=config.get("timeout", 120),
        headers=_headers(config),
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8").strip()
        if not decoded.startswith("data: "):
            continue
        data = decoded[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices", [{}])[0]
        delta = choices.get("delta", {})

        reasoning = delta.get("reasoning_content", "")
        content = delta.get("content", "")
        usage = chunk.get("usage")

        yield (content, reasoning, usage)


def list_openai_models(config):
    """GET /v1/models -> list of model ID strings."""
    try:
        resp = requests.get(
            f"{_base_url(config)}/models",
            headers=_headers(config), timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []


def validate_openai(config):
    """验证 OpenAI 兼容的 API 密钥和端点是否有效。"""
    try:
        resp = requests.get(
            f"{_base_url(config)}/models",
            headers=_headers(config), timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ── Anthropic Claude ──

ANTHROPIC_BASE = "https://api.anthropic.com/v1"

ANTHROPIC_MODEL_ALIAS = {
    "claude-sonnet-4-6": "claude-sonnet-4-20250514",
    "claude-sonnet-4-7": "claude-sonnet-4-20250514",
    "claude-haiku-3-5": "claude-haiku-3-5-20241022",
    "claude-opus-4-7": "claude-opus-4-20250514",
}


def _anthropic_headers(config):
    key = config.get("anthropic_api_key", "")
    return {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }


def _convert_to_anthropic_messages(messages):
    """
    将 OpenAI 格式的消息列表转为 Anthropic 格式。
    - 提取 system 消息作为顶级 system 参数
    - 剩余消息转为 user/assistant 交替（Anthropic 要求 user 开头，严格交替）
    """
    system = ""
    conv = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if role == "system":
            if system:
                system += "\n" + content
            else:
                system = content
        elif role in ("user", "assistant"):
            conv.append({"role": role, "content": content})

    # Anthropic 要求第一条消息必须是 user
    if conv and conv[0]["role"] != "user":
        conv.insert(0, {"role": "user", "content": "."})

    # 合并连续同角色消息
    merged = []
    for msg in conv:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append(msg)

    return system, merged


def stream_anthropic(messages, config):
    """
    Anthropic Claude 流式调用。
    Yields: (content, reasoning, usage)
    """
    _require_key(config, "anthropic_api_key", "Anthropic")
    system, conv_messages = _convert_to_anthropic_messages(messages)

    model = config.get("model", "claude-sonnet-4-20250514")
    model = ANTHROPIC_MODEL_ALIAS.get(model, model)

    payload = {
        "model": model,
        "messages": conv_messages,
        "max_tokens": config.get("max_tokens", 4096),
        "stream": True,
    }
    if system:
        payload["system"] = system

    resp = requests.post(
        f"{ANTHROPIC_BASE}/messages",
        json=payload, stream=True, timeout=config.get("timeout", 120),
        headers=_anthropic_headers(config),
    )
    resp.raise_for_status()

    current_block_type = None
    input_tokens = 0
    output_tokens = 0

    for line in resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8").strip()
        # Anthropic SSE: event: xxx \n data: {...}
        if decoded.startswith("event: "):
            current_event = decoded[7:]
            continue
        if not decoded.startswith("data: "):
            continue
        data = decoded[6:]
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue

        event = chunk.get("type", "")

        if event == "message_start":
            usage = chunk.get("message", {}).get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            continue

        if event == "content_block_start":
            current_block_type = chunk.get("content_block", {}).get("type", "")
            continue

        if event == "content_block_delta":
            delta = chunk.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if current_block_type == "thinking":
                    yield ("", text, None)
                else:
                    yield (text, "", None)

            elif delta_type == "thinking_delta":
                thinking = delta.get("thinking", "")
                yield ("", thinking, None)

            continue

        if event == "content_block_stop":
            current_block_type = None
            continue

        if event == "message_delta":
            usage = chunk.get("usage", {})
            output_tokens = usage.get("output_tokens", 0)
            yield ("", "", {"prompt_tokens": input_tokens, "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens})
            continue

        if event == "message_stop":
            break


def list_anthropic_models(config):
    """GET /v1/models -> list of model ID strings."""
    try:
        resp = requests.get(
            f"{ANTHROPIC_BASE}/models",
            headers=_anthropic_headers(config), timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [m["id"] for m in data.get("data", []) if m["type"] == "model"]
    except Exception:
        return []


def validate_anthropic(config):
    """验证 Anthropic API 密钥是否有效。"""
    try:
        resp = requests.get(
            f"{ANTHROPIC_BASE}/models",
            headers=_anthropic_headers(config), timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False
