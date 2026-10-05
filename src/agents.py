"""多 AI agent 分析：数据整理 + 新闻（可插拔） + 策略推理（加仓周期）。

核心目标：当买入信号触发时，综合估值分位、历史趋势与市场信息，
评估「本次加仓持续周期」，据此确定投入金额与资金安排；
当卖出信号触发时，分析分批卖出方案。
"""

from . import config, llm, strategy

_STRATEGY_SYSTEM = (
    "你是一名严谨的指数定投策略分析师。当买入信号触发时，综合估值分位、"
    "历史趋势与市场信息，评估「本次加仓持续周期」（预计持续多少周），"
    "并据此给出投入金额与资金安排建议；当卖出信号触发时，分析分批卖出方案。"
    "只输出 JSON 对象，字段固定为：signal、weekly_amount、estimated_cycle_weeks、"
    "confidence、reasoning、risks。其中 estimated_cycle_weeks 为整数周数（无买入则为 0），"
    "confidence 取 low/medium/high，risks 为字符串数组。"
)


def build_data_summary(records, histories) -> str:
    """DataAgent：把估值数据整理成结构化文本。"""
    lines = []
    for r in records:
        cfg = config.config_for(r["index_code"])
        metric = cfg["metric"]
        pct = r[f"{metric}_percent"]
        act = strategy.action(cfg["category"], pct)
        monthly = strategy.buy_amount(cfg["category"], pct)
        trend = _trend(histories.get(r["index_code"], []), metric)
        lines.append(
            f"- {r['name']}({r['index_code']})：{metric.upper()}分位 {pct:.2f}%，"
            f"动作 {act}，月投 {monthly:.0f} 元，近段趋势 {trend}"
        )
    return "\n".join(lines)


def collect_news(records) -> str:
    """NewsAgent：抓取财经快讯并按关键词过滤，匹配不足时兜底返回通用头条。"""
    try:
        from . import news

        keywords = _news_keywords(records)
        items = news.fetch_news(limit=40)
        rel = news.relevant_news(items, keywords, top=8)

        # 关键词命中不足时，补充通用财经头条，保证 AI 有解读素材
        if len(rel) < 5:
            seen = {it["title"] for it in rel}
            for it in items:
                if len(rel) >= 10:
                    break
                if it["title"] not in seen:
                    rel.append(it)
                    seen.add(it["title"])

        if not rel:
            return ""
        return "近期财经快讯：\n" + "\n".join(f"- {it['title']}" for it in rel)
    except Exception:  # noqa: BLE001 - 新闻不可用时不阻断主流程
        return ""


def _news_keywords(records) -> list:
    """从持仓/指数名称里提取新闻检索关键词。"""
    kws = set()
    for r in records:
        for k in ("fund_name", "name", "index_name"):
            v = r.get(k) or ""
            for w in v.replace("指数", " ").replace("ETF", " ").replace("联接", " ").split():
                if len(w) >= 2:
                    kws.add(w)
    return list(kws)


def summarize_market(news_text: str) -> str:
    """MarketAgent：把新闻解读成市场背景与风险点（AI 检查/解读环节）。"""
    if not news_text or not llm.available():
        return ""
    result = llm.chat_json(
        [
            {
                "role": "system",
                "content": (
                    "你是市场新闻解读助手。根据给出的财经快讯，输出 JSON 对象，字段："
                    "summary（一句话市场背景）、risks（字符串数组，2-4 条相关风险/关注点）。"
                ),
            },
            {"role": "user", "content": news_text},
        ]
    )
    if not isinstance(result, dict):
        return ""
    parts = []
    if result.get("summary"):
        parts.append("市场背景：" + result["summary"])
    if result.get("risks"):
        parts.append("关注点：" + "；".join(result["risks"]))
    return "\n".join(parts)


def analyze_cycle(record: dict, history: list, news: str = "") -> dict:
    """StrategyAgent：分析单个指数的加仓周期 / 卖出方案。

    record 需含 index_code 及该类别对应的估值分位字段（pe_percent / pb_percent）。
    """
    cfg = config.config_for(record["index_code"])
    category = cfg["category"]
    metric = cfg["metric"]
    pct = record[f"{metric}_percent"]
    act = strategy.action(category, pct)
    monthly = strategy.buy_amount(category, pct)
    weekly = round(monthly / 4, 2) if monthly else 0.0

    if not llm.available():
        return _rule_based_cycle(cfg, pct, act, weekly)

    prompt = _build_prompt(cfg, record, history, news, pct, act, weekly)
    result = llm.chat_json(
        [
            {"role": "system", "content": _STRATEGY_SYSTEM},
            {"role": "user", "content": prompt},
        ]
    )
    result.setdefault("signal", act)
    result.setdefault("weekly_amount", weekly)
    result.setdefault("estimated_cycle_weeks", 0)
    result.setdefault("confidence", "medium")
    result.setdefault("reasoning", "")
    result.setdefault("risks", [])
    return result


def _trend(history, metric):
    if not history:
        return "无历史数据"
    vals = [h[f"{metric}_percent"] for h in history if h.get(f"{metric}_percent") is not None]
    if len(vals) < 2:
        return "历史不足"
    diff = vals[-1] - vals[0]
    if diff > 1:
        return "上升(变贵)"
    if diff < -1:
        return "下降(变便宜)"
    return "平稳"


def _buy_rule_text(cfg) -> str:
    """用文字描述某类别的买入规则，供 prompt 使用。"""
    if cfg["category"] == "large_cap":
        tiers = "、".join(f"{t:.0f}分位以下月投{a:.0f}元" for t, a in cfg["buy_tiers"])
        return f"PE分位阶梯买入：{tiers}"
    return (
        f"{cfg['metric'].upper()}分位低于 {cfg['buy_zone']:.0f} 起步月投 {cfg['base_amount']:.0f} 元，"
        f"每下降 {cfg['step']:.0f} 个分位金额乘 {cfg['multiplier']:g}"
    )


def _build_prompt(cfg, record, history, news, pct, act, weekly) -> str:
    metric = cfg["metric"].upper()
    trend = _trend(history, cfg["metric"])
    parts = [
        f"标的：{cfg['name']}（{cfg['index_code']}），类别 {cfg['category']}，估值指标 {metric}。",
        f"当前 {metric} 分位：{pct:.2f}%。",
        f"买入规则：{_buy_rule_text(cfg)}；暂停线 {cfg['pause']:.0f} 分位；"
        f"卖出区 >{config.SELL_ZONE:.0f} 分位（80/90 分位各卖 30%）。",
        f"纪律判定动作：{act}；若买入，每周定投 {weekly:.2f} 元。",
        f"近段估值分位趋势：{trend}。",
    ]
    if news:
        parts.append(f"重点新闻：\n{news}")
    parts.append(
        "请评估：本次加仓预计持续多少周？给出 estimated_cycle_weeks（整数周）、"
        "confidence、reasoning 与 risks。若当前无买入信号，estimated_cycle_weeks 填 0，"
        "并给出卖出或观望建议。"
    )
    return "\n".join(parts)


def _rule_based_cycle(cfg, pct, act, weekly) -> dict:
    """无 API key 时的规则化估算（粗粒度，仅保证流程可跑）。"""
    result = {
        "signal": act,
        "weekly_amount": weekly,
        "estimated_cycle_weeks": 0,
        "confidence": "low",
        "reasoning": "未配置 DEEPSEEK_API_KEY，采用规则化粗略估算。",
        "risks": [],
    }
    if act == "buy":
        depth = max(0.0, cfg["pause"] - pct)
        weeks = max(4, int(round(depth * 2)))
        result["estimated_cycle_weeks"] = weeks
        result["reasoning"] += (
            f" 当前分位低于暂停线 {depth:.1f} 个百分点，粗略估算本次加仓约持续 {weeks} 周。"
        )
    elif act == "sell_zone":
        result["reasoning"] += " 已进入卖出区，关注 80/90 分位分批卖出各 30%。"
    elif act == "pause":
        result["reasoning"] += " 当前处于暂停区，不宜加仓。"
    else:
        result["reasoning"] += " 当前无买入信号，观望。"
    return result
