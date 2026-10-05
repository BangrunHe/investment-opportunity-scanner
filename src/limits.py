"""投资限额检查：累计投入或加仓连续周数超限时，输出停止加仓/卖出提醒。"""

from . import config


def check(index_code: str, state: dict) -> list:
    """返回提醒列表，每个提醒为 {level, code, message}。

    level: critical（停止加仓）
    code:  over_invest / over_cycle
    """
    cfg = config.config_for(index_code)
    limit = config.LIMITS.get(cfg["category"], {})
    alerts = []

    max_invest = limit.get("max_cumulative_invest")
    if max_invest and state.get("total_invested", 0.0) >= max_invest:
        alerts.append(
            {
                "level": "critical",
                "code": "over_invest",
                "message": (
                    f"{cfg['name']} 累计投入 {state['total_invested']:.0f} 元已达上限 "
                    f"{max_invest:.0f} 元，建议停止加仓。"
                ),
            }
        )

    max_weeks = limit.get("max_cycle_weeks")
    if max_weeks and state.get("consecutive_buy_weeks", 0) >= max_weeks:
        alerts.append(
            {
                "level": "critical",
                "code": "over_cycle",
                "message": (
                    f"{cfg['name']} 本次加仓已连续 {state['consecutive_buy_weeks']} 周，"
                    f"达上限 {max_weeks} 周，建议停止加仓并评估卖出。"
                ),
            }
        )

    return alerts
