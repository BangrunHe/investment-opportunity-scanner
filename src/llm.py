"""DeepSeek API 客户端（OpenAI 兼容 /chat/completions）。"""

import json
import os

import requests

from . import config


def api_key() -> str:
    return os.environ.get(config.LLM["api_key_env"], "")


def available() -> bool:
    return bool(api_key())


def chat(messages, model=None, temperature=None, max_tokens=None) -> str:
    """调用 chat completions，返回助手文本。"""
    key = api_key()
    if not key:
        raise RuntimeError(f"未配置 {config.LLM['api_key_env']}，无法调用大模型")

    url = config.LLM["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model or config.LLM["model"],
        "messages": messages,
        "temperature": config.LLM["temperature"] if temperature is None else temperature,
        "max_tokens": config.LLM["max_tokens"] if max_tokens is None else max_tokens,
        "stream": False,
    }
    session = requests.Session()
    session.trust_env = config.TRUST_ENV_PROXY
    resp = session.post(url, headers=headers, json=body, timeout=config.LLM["timeout"])
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def chat_json(messages, **kwargs) -> dict:
    """调用并尝试解析 JSON 返回；解析失败时返回 {'raw': text}。"""
    text = chat(messages, **kwargs).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {"raw": text}
