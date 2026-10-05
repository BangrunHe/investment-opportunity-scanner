// 核心-卫星体系与黄金再平衡（转写自 src/portfolio.py）

import type { StrategyConfig } from "./config.ts";

export interface FundAsset {
  category?: string;
  holding_assets?: number;
}

export function weights(funds: FundAsset[]) {
  const total = funds.reduce((s, f) => s + (f.holding_assets || 0), 0);
  if (total <= 0) {
    return { total: 0, core_ratio: 0, satellite_ratio: 0, gold_ratio: 0 };
  }
  const ratio = (cat: string) =>
    funds.filter((f) => f.category === cat).reduce((s, f) => s + (f.holding_assets || 0), 0) / total;
  return {
    total,
    core_ratio: ratio("core"),
    satellite_ratio: ratio("satellite"),
    gold_ratio: ratio("gold"),
  };
}

export interface Alert {
  level: "critical" | "warn";
  code: string;
  message: string;
}

export function checkRules(cfg: StrategyConfig, funds: FundAsset[]): Alert[] {
  const w = weights(funds);
  const alerts: Alert[] = [];

  if (w.satellite_ratio > cfg.portfolio.satellite_max_ratio) {
    alerts.push({
      level: "critical",
      code: "satellite_over",
      message: `卫星基金占比 ${(w.satellite_ratio * 100).toFixed(1)}%，超过 ${(cfg.portfolio.satellite_max_ratio * 100).toFixed(0)}% 上限，建议减仓卫星基金。`,
    });
  }

  // 仅当实际持有黄金时才做再平衡检查
  if (w.gold_ratio > 0) {
    const dev = w.gold_ratio - cfg.portfolio.gold_baseline_ratio;
    if (Math.abs(dev) > cfg.portfolio.gold_rebalance_band) {
      const action = dev < 0 ? "加仓" : "减仓";
      alerts.push({
        level: "warn",
        code: "gold_rebalance",
        message: `黄金占比 ${(w.gold_ratio * 100).toFixed(1)}%，偏离基准 ${(cfg.portfolio.gold_baseline_ratio * 100).toFixed(0)}% 超过 ${(cfg.portfolio.gold_rebalance_band * 100).toFixed(0)}%，建议${action}至 ${(cfg.portfolio.gold_baseline_ratio * 100).toFixed(0)}%。`,
      });
    }
  }

  return alerts;
}
