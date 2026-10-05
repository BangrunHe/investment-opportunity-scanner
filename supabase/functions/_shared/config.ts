// 常量与默认纪律参数（与本地 Python src/config.py 保持一致）

export const DANJUAN_API = "https://danjuanfunds.com/djapi/index_eva/dj";
export const DEEPSEEK_BASE = "https://api.deepseek.com";
export const DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1";
export const NEWS_URL = "https://feed.mix.sina.com.cn/api/roll/get";

// 目标指数：index_code -> 名称/类别
export const INDICES: Record<string, { name: string; category: string }> = {
  SH000300: { name: "沪深300", category: "large_cap" },
  SH000905: { name: "中证500", category: "large_cap" },
  SH000852: { name: "中证1000", category: "large_cap" },
  SZ399006: { name: "创业板指", category: "chinext" },
  SH000688: { name: "科创50", category: "star50" },
};

// 纪律参数类型
export interface TierRule {
  metric: "pe";
  buy_tiers: [number, number][]; // 升序：[阈值, 月投金额]
  pause: number;
}
export interface StepRule {
  metric: "pb";
  buy_zone: number;
  base_amount: number;
  step: number;
  multiplier: number;
  pause: number;
}
export interface SellRule {
  zone: number;
  steps: number[];
  fraction: number;
}
export interface PortfolioRule {
  satellite_max_ratio: number;
  gold_baseline_ratio: number;
  gold_rebalance_band: number;
}
export interface StrategyConfig {
  large_cap: TierRule;
  chinext: StepRule;
  star50: StepRule;
  sell: SellRule;
  portfolio: PortfolioRule;
  industry_discipline: string;
}

export const DEFAULT_CONFIG: StrategyConfig = {
  large_cap: { metric: "pe", buy_tiers: [[10, 2000], [20, 1000], [30, 500]], pause: 35 },
  chinext: { metric: "pb", buy_zone: 40, base_amount: 300, step: 10, multiplier: 1.5, pause: 50 },
  star50: { metric: "pb", buy_zone: 30, base_amount: 500, step: 10, multiplier: 2.0, pause: 40 },
  sell: { zone: 70, steps: [80, 90], fraction: 0.30 },
  portfolio: { satellite_max_ratio: 0.40, gold_baseline_ratio: 0.25, gold_rebalance_band: 0.07 },
  industry_discipline: "star50",
};

// 类别 -> 规则
export function categoryRule(cfg: StrategyConfig, category: string): TierRule | StepRule {
  if (category === "large_cap") return cfg.large_cap;
  if (category === "chinext") return cfg.chinext;
  if (category === "star50") return cfg.star50;
  return cfg.star50; // 行业/卫星默认科创50纪律
}

export const round2 = (n: number) => Math.round(n * 100) / 100;
