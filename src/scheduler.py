"""每周定时任务：抓取 → 归档 → 多 agent 分析 → 台账记录 → 限额检查 → 提醒。

另有持仓组合分析任务（run_portfolio_job），结合 Supabase 持仓库给出建议。
"""

import time
from datetime import datetime

from . import (
    advisor,
    agents,
    config,
    fetch,
    fund_classify,
    ledger,
    limits,
    notify,
    store,
    strategy,
    supabase_db,
)


def run_weekly_job() -> dict:
    """执行一次周度任务，返回 {date, records, analyses, alerts}。"""
    records = fetch.fetch_target_indices()
    store.save_records(records)

    date = records[0]["date"] if records else datetime.now().strftime("%Y-%m-%d")
    histories = {r["index_code"]: store.load_history(r["index_code"]) for r in records}
    news = agents.collect_news(records)

    analyses = []
    alerts = []
    for r in records:
        cfg = config.config_for(r["index_code"])
        category = cfg["category"]
        metric = cfg["metric"]
        pct = r[f"{metric}_percent"]
        monthly = strategy.buy_amount(category, pct)
        weekly = round(monthly / 4, 2) if monthly else 0.0

        # 记录台账（每周定投），并做限额检查
        state = ledger.record(r["index_code"], weekly, date)
        alerts.extend(limits.check(r["index_code"], state))

        # 多 agent 分析（加仓周期）
        analysis = agents.analyze_cycle(r, histories[r["index_code"]], news)
        analyses.append({**r, **analysis})

    return {"date": date, "records": records, "analyses": analyses, "alerts": alerts}


def run_portfolio_job() -> dict:
    """持仓组合分析：读取 Supabase 持仓 -> 匹配估值 -> 逐基金建议 + 组合规则提醒。"""
    if not supabase_db.configured():
        return {
            "configured": False,
            "message": "未配置 Supabase，跳过持仓组合分析。",
            "advices": [],
            "alerts": [],
        }

    static = supabase_db.select("static_funds") or []
    holdings = supabase_db.select("fund_holdings") or []

    # 以最新一周的持仓为准（简化：按 fund_code 去重，取最新记录）
    funds = {}
    for h in holdings:
        code = h.get("fund_code")
        if not code:
            continue
        if code not in funds or (h.get("week") or "") >= (funds[code].get("week") or ""):
            funds[code] = h
    funds = list(funds.values())

    # 合并静态库里的 category / index_code / index_name
    static_map = {s.get("fund_code"): s for s in static}
    for f in funds:
        s = static_map.get(f.get("fund_code"), {})
        f["category"] = f.get("category") or s.get("category") or "satellite"
        f["index_code"] = f.get("index_code") or s.get("index_code")
        f["index_name"] = f.get("index_name") or s.get("index_name")

    all_val = fetch.fetch_all_indices()

    # 新闻收集（按持仓关键词）+ 市场解读（AI 检查链路）
    news = agents.collect_news(funds)
    market_context = agents.summarize_market(news) if news else ""

    result = advisor.advise_portfolio(funds, all_val, market_context)

    # AI 分类复核（仅对 static_funds 中 pending_confirm 的基金）
    checks = []
    for s in static:
        if s.get("status") == "confirmed":
            continue
        v = fund_classify.verify(
            s.get("fund_code"), s.get("fund_name"), s.get("category"), s.get("index_name")
        )
        v["fund_code"] = s.get("fund_code")
        checks.append(v)

    result["configured"] = True
    result["funds"] = funds
    result["news"] = news
    result["market_context"] = market_context
    result["classification_checks"] = checks
    return result


def classify_pending_funds() -> list:
    """对静态库中待确认的基金做 AI 归类，返回分类结果（写入需人工确认）。"""
    if not supabase_db.configured():
        return []
    static = supabase_db.select("static_funds") or []
    results = []
    for s in static:
        if s.get("category") in ("core", "satellite", "gold") and s.get("status") == "confirmed":
            continue
        cls = fund_classify.classify(s.get("fund_code"), s.get("fund_name"))
        results.append(cls)
    return results


def run_forever(interval_seconds: int = 604800):
    """简单循环执行（默认每周）。生产环境建议改用系统 cron / 云函数定时调用 run_weekly_job()。"""
    while True:
        try:
            result = run_weekly_job()
            notify.send_console(result["alerts"], result["analyses"])
        except Exception as exc:  # noqa: BLE001
            print("周度任务失败：", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    result = run_weekly_job()
    notify.send_console(result["alerts"], result["analyses"])
