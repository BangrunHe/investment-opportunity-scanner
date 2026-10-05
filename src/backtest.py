"""纪律回测：按历史估值分位重放，输出买卖信号时间线与资金计划。

说明：蛋卷估值接口只提供估值（PE/PB）与分位，不含指数点位。
本 MVP 的回测聚焦「纪律是否被正确触发」——输出信号时间线、月定投金额、
累计投入与卖出事件；基于价格/净值的收益率回测需另行接入价格数据源。
"""

from . import config, strategy


def replay(history: list) -> list:
    """按日期升序重放某指数历史，返回逐条信号记录。

    history 需按 date 升序；每条需含 category 及对应估值指标的分位字段。
    """
    events = []
    last_sell = 0.0
    for rec in history:
        category = rec["category"]
        metric = config.CATEGORY_CONFIG[category]["metric"]
        percentile = rec[f"{metric}_percent"]
        act = strategy.action(category, percentile)
        monthly = strategy.buy_amount(category, percentile)
        crossed = strategy.crossed_sell_steps(percentile, last_sell)
        if crossed:
            last_sell = crossed[-1]
        events.append(
            {
                "date": rec["date"],
                "percentile": percentile,
                "action": act,
                "monthly_amount": monthly,
                "sell_steps": crossed,
            }
        )
    return events


def summarize(events: list) -> dict:
    """汇总回测结果：买入期数、累计投入、卖出次数等。"""
    buys = [e for e in events if e["action"] == "buy"]
    sell_events = [s for e in events for s in e["sell_steps"]]
    return {
        "periods": len(events),
        "buy_periods": len(buys),
        "total_invested": round(sum(e["monthly_amount"] for e in buys), 2),
        "sell_events": len(sell_events),
        "sell_steps": sell_events,
    }
