"""Supabase（PostgREST）客户端：个人持仓数据库读写。

使用 REST API（无需 supabase-py 依赖）。鉴权 key 建议使用 service_role（仅本机/云端
安全环境）或启用 RLS 后的受限 anon key，确保持仓信息不泄露。
"""

import os

import requests

from . import config


def _credentials():
    url = os.environ.get(config.SUPABASE["url_env"], "").rstrip("/")
    key = os.environ.get(config.SUPABASE["key_env"], "")
    return url, key


def configured() -> bool:
    url, key = _credentials()
    return bool(url and key)


def _headers(api_key, prefer=None):
    h = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _request(method, table, api_key, base_url, params=None, json=None, prefer=None):
    session = requests.Session()
    session.trust_env = config.TRUST_ENV_PROXY
    url = f"{base_url}/rest/v1/{table}"
    resp = session.request(
        method,
        url,
        headers=_headers(api_key, prefer),
        params=params,
        json=json,
        timeout=config.SUPABASE["timeout"],
    )
    resp.raise_for_status()
    return resp.json() if resp.content else None


def _require_configured():
    if not configured():
        raise RuntimeError("未配置 SUPABASE_URL / SUPABASE_KEY")


def insert(table, rows):
    """插入单条 dict 或列表，返回插入后的记录。"""
    _require_configured()
    url, key = _credentials()
    return _request("POST", table, key, url, json=rows, prefer="return=representation")


def upsert(table, rows, on_conflict=None):
    """插入或按唯一列合并更新，返回合并后的记录。

    on_conflict: 冲突判定列，如 "fund_code" 或 "week,fund_code"（复合）。
    """
    _require_configured()
    url, key = _credentials()
    params = {"on_conflict": on_conflict} if on_conflict else None
    return _request(
        "POST",
        table,
        key,
        url,
        params=params,
        json=rows,
        prefer="resolution=merge-duplicates,return=representation",
    )


def select(table, filters="*", eq=None):
    """查询。filters 如 "*" 或 "fund_code,category"；eq 为 {column: value}。"""
    _require_configured()
    url, key = _credentials()
    params = {"select": filters}
    if eq:
        for col, val in eq.items():
            params[col] = f"eq.{val}"
    return _request("GET", table, key, url, params=params)


def update(table, id_value, data, id_col="id"):
    """按主键列更新记录，返回更新后的记录。"""
    _require_configured()
    url, key = _credentials()
    return _request(
        "PATCH",
        table,
        key,
        url,
        params={id_col: f"eq.{id_value}"},
        json=data,
        prefer="return=representation",
    )


def delete(table, eq):
    """按条件删除记录。eq 为 {column: value}，返回被删除的记录。"""
    _require_configured()
    url, key = _credentials()
    params = {}
    for col, val in eq.items():
        params[col] = f"eq.{val}"
    return _request("DELETE", table, key, url, params=params, prefer="return=representation")


def run_sql(query: str, api_key: str = None) -> dict:
    """通过 pg-meta 执行任意 SQL（建表等 DDL），需 service_role key。

    api_key 默认取 SUPABASE_SERVICE_KEY，缺省则回退 SUPABASE_KEY。
    """
    url, key = _credentials()
    sql_key = api_key or os.environ.get(config.SUPABASE["service_key_env"]) or key
    if not url:
        raise RuntimeError("未配置 SUPABASE_URL")
    endpoint = f"{url}/pg-meta/default/query"
    session = requests.Session()
    session.trust_env = config.TRUST_ENV_PROXY
    resp = session.post(
        endpoint,
        headers=_headers(sql_key),
        json={"query": query},
        timeout=config.SUPABASE["timeout"],
    )
    resp.raise_for_status()
    return resp.json() if resp.content else None
