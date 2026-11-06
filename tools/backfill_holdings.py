"""把历史各周的持仓回填成**完整快照**（一次性迁移脚本）。

背景
----
早期 `writeHoldings()` 只写入当周截图 OCR 到的那几只基金，把每周当作「全量」。
但你实际是增量上传（只发有变动的那几只），于是每周只含当周的子集：
群里回执看着像「之前的基金丢了」，跨周对比、占比、总资产也全部失真。

修复后 Edge Function 每次入库都会自动「顺延」未上传的基金（见
`supabase/functions/_shared/holdings.ts` 的 `carryForward`），新数据不会再错。
本脚本负责回填**已经入库的历史周次**。

规则：按周升序，把「此前出现过、但本周没有行」的基金，用其历史最新值补进本周。
本周已有的行一律不动（不覆盖你后来手工修正的数值）。

前置：.env 已配 SUPABASE_URL / SUPABASE_KEY
用法：
  python tools/backfill_holdings.py            # 预演：只打印将要补的内容
  python tools/backfill_holdings.py --apply    # 真正写库
"""

import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402

TABLE_COLS = (
    "fund_code,fund_name,holding_assets,holding_cost,holding_profit,"
    "holding_shares,unit_cost,week_nav,week"
)


def _base():
    url = os.environ.get(config.SUPABASE["url_env"], "").rstrip("/")
    key = os.environ.get(config.SUPABASE["key_env"], "")
    if not (url and key):
        raise SystemExit("请先在 .env 配置 SUPABASE_URL / SUPABASE_KEY")
    return url, key


def _proxy():
    """Supabase 在境外，需要代理；config.TRUST_ENV_PROXY 为 False（国内站点不走代理），
    所以这里用 http 代理显式指定：优先 SUPABASE_PROXY，否则探测本机常见端口。"""
    explicit = os.environ.get("SUPABASE_PROXY", "").strip()
    if explicit:
        return {"http": explicit, "https": explicit}

    import socket

    for port in (7897, 7890, 10809, 1080):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=2).close()
            p = f"http://127.0.0.1:{port}"
            return {"http": p, "https": p}
        except OSError:
            continue
    return None


def _headers(key, prefer=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _request(method, path, key, base, tries=20, **kwargs):
    """Supabase 出网不稳定（Cloudflare），失败自动重试。"""
    last = None
    prefer = kwargs.pop("prefer", None)
    proxies = _proxy()
    for i in range(tries):
        try:
            s = requests.Session()
            s.trust_env = config.TRUST_ENV_PROXY
            resp = s.request(
                method,
                f"{base}/rest/v1/{path}",
                headers=_headers(key, prefer),
                proxies=proxies,
                timeout=config.SUPABASE["timeout"],
                **kwargs,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json() if resp.content else None
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(0.4 * (i + 1), 3))
    raise SystemExit(f"请求 {path} 连续失败 {tries} 次：{last}")


def fetch_all(base, key, table, cols):
    """分页拉全表（PostgREST 单次默认上限 1000 行）。"""
    rows, offset, page = [], 0, 1000
    while True:
        batch = _request(
            "GET",
            table,
            key,
            base,
            params={"select": cols, "limit": page, "offset": offset, "order": "week.asc"},
        )
        rows.extend(batch or [])
        if not batch or len(batch) < page:
            return rows
        offset += page


def plan_backfill(rows):
    """按周升序推演：返回 (缺失行列表, 每周统计)。"""
    by_week = {}
    for r in rows:
        by_week.setdefault(r["week"], []).append(r)

    weeks = sorted(by_week)
    known = {}  # fund_code -> 该基金目前为止的最新一条
    missing = []
    stats = []

    for w in weeks:
        cur = {r["fund_code"] for r in by_week[w]}
        # 本周已有的行先并入 known（同周内以最后一条为准）
        for r in by_week[w]:
            known[r["fund_code"]] = r

        filled = []
        for code, r in known.items():
            if code in cur:
                continue
            row = {c: r.get(c) for c in TABLE_COLS.split(",")}
            row["week"] = w
            missing.append(row)
            filled.append(row.get("fund_name") or code)
        stats.append((w, len(cur), len(filled), len(cur) + len(filled)))
    return missing, stats


def main() -> None:
    apply = "--apply" in sys.argv
    base, key = _base()

    print("读取 fund_holdings ...")
    rows = fetch_all(base, key, "fund_holdings", TABLE_COLS)
    print(f"共 {len(rows)} 行\n")
    if not rows:
        raise SystemExit("没有持仓数据，无需回填。")

    missing, stats = plan_backfill(rows)

    print(f"{'周':<26}{'原有':>6}{'补':>6}{'回填后':>8}")
    print("─" * 48)
    for w, cur, fill, total in stats:
        print(f"{w:<26}{cur:>6}{fill:>6}{total:>8}")

    if not missing:
        print("\n✅ 每周都已是完整快照，无需回填。")
        return

    print(f"\n待补 {len(missing)} 行：")
    for r in missing[:20]:
        print(f"  {r['week']}  {r['fund_code']}  {r.get('fund_name')}  {r.get('holding_assets')}")
    if len(missing) > 20:
        print(f"  ... 另有 {len(missing) - 20} 行")

    if not apply:
        print("\n（预演模式，未写库。加 --apply 执行）")
        return

    print("\n写入 fund_holdings ...")
    _request(
        "POST",
        "fund_holdings",
        key,
        base,
        params={"on_conflict": "week,fund_code"},
        json=missing,
        prefer="resolution=merge-duplicates",
    )

    print("写入 holding_snapshots ...")
    snaps = [
        {
            "week": r["week"],
            "fund_code": r["fund_code"],
            "fund_name": r["fund_name"],
            "holding_assets": r["holding_assets"],
        }
        for r in missing
    ]
    _request(
        "POST",
        "holding_snapshots",
        key,
        base,
        params={"on_conflict": "week,fund_code"},
        json=snaps,
        prefer="resolution=merge-duplicates",
    )

    after = fetch_all(base, key, "fund_holdings", TABLE_COLS)
    print(f"\n✅ 回填完成：{len(rows)} -> {len(after)} 行")
    _, stats2 = plan_backfill(after)
    for w, cur, fill, total in stats2:
        print(f"  {w}  {total} 只" + ("  ⚠️ 仍有空缺" if fill else ""))


if __name__ == "__main__":
    main()
