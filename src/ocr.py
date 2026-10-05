"""多模态 OCR：把基金持仓截图转成结构化持仓数据。

- extract_from_image：用多模态大模型（需 VISION_API_KEY，OpenAI 兼容视觉端点）。
- structure_text：把（已 OCR 出的）文本用文本大模型（DeepSeek）结构化。
"""

import base64
import json
import os
from pathlib import Path

import requests

from . import config, llm

_EXTRACT_SYSTEM = (
    "你是基金持仓截图的结构化提取工具。从图片/文本中提取每只基金的持仓信息，"
    "只输出 JSON 数组，每个元素字段为：fund_code、fund_name、holding_assets、"
    "holding_cost、holding_profit、holding_shares、unit_cost、week_nav。"
    "数字只保留数值（去掉逗号与单位，负号保留），无法识别的字段填 null。"
)


def extract_from_image(image_path: str) -> list:
    """用多模态大模型从截图提取持仓列表。"""
    key = os.environ.get(config.VISION["api_key_env"], "")
    if not key:
        raise RuntimeError(f"未配置 {config.VISION['api_key_env']}，无法进行多模态 OCR")
    model = os.environ.get(config.VISION["model_env"]) or config.VISION["model"]
    if not model:
        raise RuntimeError("未配置视觉模型名（VISION_MODEL）")

    base_url = (os.environ.get(config.VISION["base_url_env"]) or config.VISION["base_url"]).rstrip("/")
    url = base_url + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请提取这张基金持仓截图中的结构化数据。"},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ],
            },
        ],
        "temperature": config.VISION["temperature"],
        "max_tokens": config.VISION["max_tokens"],
    }
    session = requests.Session()
    session.trust_env = config.TRUST_ENV_PROXY
    resp = session.post(url, headers=headers, json=body, timeout=config.VISION["timeout"])
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def structure_text(raw_text: str) -> list:
    """把已 OCR 出的文本用文本大模型结构化（可用 DeepSeek）。"""
    if not llm.available():
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，无法结构化")
    result = llm.chat_json(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": f"请从以下文本提取结构化持仓：\n{raw_text}"},
        ]
    )
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return items
        if result and "raw" not in result:
            return [result]
    return []


def _image_data_url(image_path: str) -> str:
    path = Path(image_path)
    data = path.read_bytes()
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


def _parse_json(content: str) -> list:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        else:
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return []
            data = json.loads(text[start : end + 1])
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = data.get("items")
        return items if isinstance(items, list) else [data]
    return []


def extract_images_parallel(image_paths, max_workers: int = 4) -> list:
    """并行识别多张截图（I/O 密集，多线程加速）。

    返回 [(image_path, rows), ...]，保持输入顺序；单张失败时 rows 为空列表。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(extract_from_image, str(p)): str(p) for p in image_paths}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                results[p] = fut.result()
            except Exception:  # noqa: BLE001 - 单张失败不影响整体
                results[p] = []
    return [(p, results.get(str(p), [])) for p in image_paths]
