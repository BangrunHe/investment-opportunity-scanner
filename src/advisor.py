"""周度投资建议：结合持仓变化 + 估值分位 + 新闻，给出每只基金与组合建议。"""

import re

from . import config, portfolio, strategy


def _code_key(code):
    """指数代码归一化键：取数字部分（去掉 SH/SZ/CSI 等前缀）。"""
    if not code:
        return ""
    key = re.sub(r"^[^0-9]*", "", str(code))
    return key or str(code)


def build_valuation_lookup(valuations):
    """把估值列表（list[dict]）按完整代码与数字键双向索引，便于模糊匹配。"""
    lookup = {}
    for v in valuations:
        code = v.get("index_code")
        if not code:
            continue
        lookup[code] = v
        key = _code_key(code)
        if key and key not in lookup:
            lookup[key] = v
    return lookup


def advise_fund(fund: dict, lookup: dict, news: str = "") -> dict:
    """单只基金建议。

    fund: {fund_code, fund_name, category, index_code, holding_assets, ...}
    lookup: build_valuation_lookup() 的结果
    news: 市场新闻解读文本（可选）
    """
    category = fund.get("category")
    if category == "gold":
        return {
            "fund_code": fund.get("fund_code"),
            "fund_name": fund.get("fund_name"),
            "category": "gold",
            "action": "rebalance",
            "reasoning": "黄金类不按估值，按 25% 基准再平衡。",
        }

    index_code = fund.get("index_code")
    val = lookup.get(index_code) if index_code else None
    if not val and index_code:
        val = lookup.get(_code_key(index_code))
    if not val:
        return {
            "fund_code": fund.get("fund_code"),
            "fund_name": fund.get("fund_name"),
            "category": category,
            "action": "unknown",
            "reasoning": f"未匹配到所属指数 {index_code} 的估值数据，请补充。",
        }

    # 纪律选择：
    # 核心（宽基/策略）基金：若指数在 5 大目标指数内用其自身纪律，否则默认按大盘 PE 纪律
    # 卫星（行业）基金：统一参考科创50(PB)纪律
    if category == "core":
        disc = config.INDICES[index_code]["category"] if index_code in config.INDICES else "large_cap"
        metric = config.CATEGORY_CONFIG[disc]["metric"]
    else:
        disc = config.INDUSTRY_DISCIPLINE  # 科创50纪律
        metric = "pb"

    pct = val.get(f"{metric}_percent")
    if pct is None:
        pct = val.get("pb_percent")
    act = strategy.action(disc, pct)
    monthly = strategy.buy_amount(disc, pct)

    reasoning = f"所属指数 {index_code} 当前 {metric.upper()} 分位 {pct:.2f}%，纪律动作 {act}。"
    if news:
        reasoning += f" 结合新闻：{news[:160]}"

    return {
        "fund_code": fund.get("fund_code"),
        "fund_name": fund.get("fund_name"),
        "category": category,
        "index_code": index_code,
        "metric": metric,
        "percentile": pct,
        "action": act,
        "monthly_amount": monthly,
        "reasoning": reasoning,
    }


def advise_portfolio(funds: list, valuations: list, news: str = "") -> dict:
    """组合层面建议：每只基金建议 + 核心-卫星/黄金再平衡提醒。"""
    lookup = build_valuation_lookup(valuations)
    advices = [advise_fund(f, lookup, news) for f in funds]
    alerts = portfolio.check_rules(funds)
    return {"advices": advices, "alerts": alerts}
