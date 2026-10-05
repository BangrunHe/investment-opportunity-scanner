// 买卖纪律纯函数（转写自 src/strategy.py）

import { categoryRule, round2, type StrategyConfig, type TierRule, type StepRule } from "./config.ts";

export function buyAmount(rule: TierRule | StepRule, percentile: number): number {
  if ("buy_tiers" in rule) {
    for (const [threshold, amount] of rule.buy_tiers) {
      if (percentile < threshold) return amount;
    }
    return 0;
  }
  if (percentile < rule.buy_zone) {
    const steps = Math.floor((rule.buy_zone - percentile) / rule.step);
    return round2(rule.base_amount * Math.pow(rule.multiplier, steps));
  }
  return 0;
}

export function action(cfg: StrategyConfig, category: string, percentile: number): string {
  const rule = categoryRule(cfg, category);
  if (buyAmount(rule, percentile) > 0) return "buy";
  if (percentile > cfg.sell.zone) return "sell_zone";
  if (percentile > rule.pause) return "pause";
  return "hold";
}

export function crossedSellSteps(cfg: StrategyConfig, percentile: number, lastSellLevel: number): number[] {
  return cfg.sell.steps.filter((s) => s > lastSellLevel && percentile >= s);
}
