"""抓取蛋卷基金估值中心数据，过滤出目标指数。"""

import time
from datetime import datetime

import requests

from . import config

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://danjuanfunds.com/rn/value-center",
}


def fetch_raw(session=None, timeout: int = 15) -> list:
    """请求估值接口，返回原始 items 列表。"""
    own_session = session is None
    if own_session:
        session = requests.Session()
        session.trust_env = config.TRUST_ENV_PROXY
    resp = session.get(config.DANJUAN_API, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("result_code") != 0:
        raise RuntimeError(f"蛋卷接口返回异常：result_code={payload.get('result_code')}")
    return payload["data"]["items"]


def fetch_target_indices(retries: int = 3, backoff: float = 2.0) -> list:
    """抓取并过滤目标指数，返回标准化记录列表。"""
    last_err = None
    for attempt in range(retries):
        try:
            items = fetch_raw()
            return [
                normalize(item)
                for item in items
                if item.get("index_code") in config.INDICES
            ]
        except Exception as exc:  # noqa: BLE001 - 记录后重试
            last_err = exc
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"抓取失败（已重试 {retries} 次）：{last_err}")


def fetch_all_indices(retries: int = 3, backoff: float = 2.0) -> list:
    """抓取估值中心全部指数的标准化记录（用于任意基金所属指数估值查询）。"""
    last_err = None
    for attempt in range(retries):
        try:
            items = fetch_raw()
            return [normalize(item) for item in items]
        except Exception as exc:  # noqa: BLE001 - 记录后重试
            last_err = exc
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"抓取失败（已重试 {retries} 次）：{last_err}")


def normalize(item: dict) -> dict:
    """把蛋卷接口的一条 item 标准化为内部记录。

    目标指数取配置里的中文名与类别；其它指数回退为接口自带名称、类别 unknown。
    """
    meta = config.INDICES.get(item["index_code"], {})
    return {
        "index_code": item["index_code"],
        "name": meta.get("name") or item.get("name") or "",
        "category": meta.get("category", "unknown"),
        "date": _ts_to_date(item.get("ts")),
        "ts": item.get("ts"),
        "pe": item.get("pe"),
        "pb": item.get("pb"),
        "pe_percent": _to_percent(item.get("pe_percentile")),
        "pb_percent": _to_percent(item.get("pb_percentile")),
        "roe": item.get("roe"),
        "yeild": item.get("yeild"),
    }


def _to_percent(frac):
    """0~1 小数换算为百分位（0~100）。"""
    if frac is None:
        return None
    return round(frac * 100, 4)


def _ts_to_date(ts_ms):
    """毫秒时间戳换算为 YYYY-MM-DD。"""
    if not ts_ms:
        return None
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
