"""信号引擎：把单次估值转成可执行的买卖信号，并维护卖出档位状态。"""

from . import config, strategy


def evaluate(category: str, percentile: float, last_sell_level: float = 0.0) -> dict:
    """评估一次估值，返回结构化信号。

    percentile 取该类别对应的估值分位（大盘宽基取 PE，成长取 PB）。
    last_sell_level 为已触发的最高卖出档位（0 表示尚未卖出），用于卖出事件去重。
    """
    act = strategy.action(category, percentile)
    monthly = strategy.buy_amount(category, percentile)
    sell_steps = strategy.crossed_sell_steps(percentile, last_sell_level)

    return {
        "action": act,
        "monthly_amount": monthly,
        "weekly_amount": round(monthly / 4, 2) if monthly else 0.0,
        "sell_steps": sell_steps,
        "sell_fraction_each": config.SELL_FRACTION,
        "new_sell_level": sell_steps[-1] if sell_steps else last_sell_level,
    }


class SignalEngine:
    """维护每个指数的卖出档位状态，逐个指数评估并生成信号。"""

    def __init__(self):
        self._sell_levels = {}

    def evaluate_record(self, record: dict) -> dict:
        cfg = config.config_for(record["index_code"])
        category = cfg["category"]
        metric = cfg["metric"]
        percentile = record[f"{metric}_percent"]

        last = self._sell_levels.get(record["index_code"], 0.0)
        sig = evaluate(category, percentile, last_sell_level=last)
        if sig["new_sell_level"] > last:
            self._sell_levels[record["index_code"]] = sig["new_sell_level"]

        sig.update(
            {
                "index_code": record["index_code"],
                "name": record["name"],
                "category": category,
                "metric": metric,
                "percentile": percentile,
            }
        )
        return sig
