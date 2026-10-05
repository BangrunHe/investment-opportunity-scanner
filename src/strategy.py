"""买卖纪律纯函数：给定类别与估值分位（百分位，0~100），输出确定性决策。"""

import math

from . import config


def buy_amount(category: str, percentile: float) -> float:
    """返回月定投金额（元）；不满足买入条件时返回 0.0。"""
    cfg = config.CATEGORY_CONFIG[category]

    if category == "large_cap":
        for threshold, amount in cfg["buy_tiers"]:
            if percentile < threshold:
                return amount
        return 0.0

    if percentile < cfg["buy_zone"]:
        steps = math.floor((cfg["buy_zone"] - percentile) / cfg["step"])
        return round(cfg["base_amount"] * (cfg["multiplier"] ** steps), 2)
    return 0.0


def action(category: str, percentile: float) -> str:
    """返回当前动作：buy / hold / pause / sell_zone。"""
    if buy_amount(category, percentile) > 0:
        return "buy"
    if percentile > config.SELL_ZONE:
        return "sell_zone"
    if percentile > config.CATEGORY_CONFIG[category]["pause"]:
        return "pause"
    return "hold"


def crossed_sell_steps(percentile: float, last_sell_level: float) -> list:
    """返回本次估值相对上次卖出档位新跨越的卖出档位（如 [80.0]）。"""
    return [
        step
        for step in config.SELL_STEPS
        if step > last_sell_level and percentile >= step
    ]
