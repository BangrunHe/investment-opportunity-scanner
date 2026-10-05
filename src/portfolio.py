"""核心-卫星体系与黄金再平衡规则（纯函数）。"""

from . import config


def weights(funds) -> dict:
    """按类别统计持仓占比。

    funds: [{category: 'core'|'satellite'|'gold', holding_assets: float}, ...]
    返回 {total, core_ratio, satellite_ratio, gold_ratio}
    """
    total = sum((f.get("holding_assets") or 0.0) for f in funds)
    if total <= 0:
        return {
            "total": 0.0,
            "core_ratio": 0.0,
            "satellite_ratio": 0.0,
            "gold_ratio": 0.0,
        }

    def ratio(cat):
        return sum((f.get("holding_assets") or 0.0) for f in funds if f.get("category") == cat) / total

    return {
        "total": total,
        "core_ratio": ratio("core"),
        "satellite_ratio": ratio("satellite"),
        "gold_ratio": ratio("gold"),
    }


def check_rules(funds) -> list:
    """返回组合层面的提醒列表（卫星超限 / 黄金再平衡）。"""
    w = weights(funds)
    cfg = config.PORTFOLIO
    alerts = []

    if w["satellite_ratio"] > cfg["satellite_max_ratio"]:
        alerts.append(
            {
                "level": "critical",
                "code": "satellite_over",
                "message": (
                    f"卫星基金占比 {w['satellite_ratio']:.1%}，超过 {cfg['satellite_max_ratio']:.0%} "
                    "上限，建议减仓卫星基金。"
                ),
            }
        )

    # 黄金再平衡：仅当组合中实际持有黄金时才检查（避免无黄金时误报「加仓黄金」）
    if w["gold_ratio"] > 0:
        dev = w["gold_ratio"] - cfg["gold_baseline_ratio"]
        if abs(dev) > cfg["gold_rebalance_band"]:
            action = "加仓" if dev < 0 else "减仓"
            alerts.append(
                {
                    "level": "warn",
                    "code": "gold_rebalance",
                    "message": (
                        f"黄金占比 {w['gold_ratio']:.1%}，偏离基准 {cfg['gold_baseline_ratio']:.0%} "
                        f"超过 {cfg['gold_rebalance_band']:.0%}，建议{action}至 {cfg['gold_baseline_ratio']:.0%}。"
                    ),
                }
            )

    return alerts
