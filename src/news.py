"""财经新闻采集：从公开源抓取快讯，并按关键词过滤相关新闻。"""

import requests

from . import config

_NEWS_URL = "https://feed.mix.sina.com.cn/api/roll/get"
_NEWS_PARAMS = {"pageid": "153", "lid": "2516", "k": "", "num": "30", "page": "1"}


def fetch_news(limit: int = 30, timeout: int = 15) -> list:
    """抓取财经快讯，返回 [{title, url, time}]。"""
    session = requests.Session()
    session.trust_env = config.TRUST_ENV_PROXY
    resp = session.get(_NEWS_URL, params=_NEWS_PARAMS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("result", {}).get("data", []) or []
    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        out.append(
            {"title": title, "url": it.get("url", ""), "time": it.get("ctime", "")}
        )
    return out[:limit]


def relevant_news(items: list, keywords: list, top: int = 8) -> list:
    """按关键词过滤相关新闻，返回 top 条；无关键词时返回前 top 条。"""
    if not keywords:
        return items[:top]
    scored = []
    for it in items:
        score = sum(1 for k in keywords if k and k in it.get("title", ""))
        if score > 0:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:top]]
