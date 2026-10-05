// 周度投资建议（转写自 src/advisor.py）

import { INDICES, categoryRule, type StrategyConfig } from "./config.ts";
import { action, buyAmount } from "./strategy.ts";
import { checkRules, type FundAsset } from "./portfolio.ts";
import type { Valuation } from "./danjuan.ts";

export function codeKey(code: string): string {
  if (!code) return "";
  const key = code.replace(/^[^0-9]*/, "");
  return key || code;
}

export function buildLookup(vals: Valuation[]): Record<string, Valuation> {
  const lookup: Record<string, Valuation> = {};
  for (const v of vals) {
    if (!v.index_code) continue;
    lookup[v.index_code] = v;
    const k = codeKey(v.index_code);
    if (k && !(k in lookup)) lookup[k] = v;
  }
  return lookup;
}

export interface FundRecord extends FundAsset {
  fund_code?: string;
  fund_name?: string;
  index_code?: string;
}

export function adviseFund(
  fund: FundRecord,
  lookup: Record<string, Valuation>,
  cfg: StrategyConfig,
): Record<string, unknown> {
  const category = fund.category;
  if (category === "gold") {
    return {
      fund_code: fund.fund_code,
      fund_name: fund.fund_name,
      category: "gold",
      action: "rebalance",
      reasoning: "黄金类不按估值，按 25% 基准再平衡。",
    };
  }

  const index_code = fund.index_code;
  let val: Valuation | undefined = index_code ? lookup[index_code] : undefined;
  if (!val && index_code) val = lookup[codeKey(index_code)];
  if (!val) {
    return {
      fund_code: fund.fund_code,
      fund_name: fund.fund_name,
      category,
      action: "unknown",
      reasoning: `未匹配到所属指数 ${index_code ?? "null"} 的估值数据，请补充。`,
    };
  }

  let disc: string;
  let metric: "pe" | "pb";
  if (category === "core") {
    disc = index_code && index_code in INDICES ? INDICES[index_code].category : "large_cap";
  } else {
    disc = cfg.industry_discipline; // 行业/卫星 -> 科创50纪律
  }
  metric = (categoryRule(cfg, disc) as { metric: "pe" | "pb" }).metric;

  const pct = metric === "pe" ? val.pe_percent : val.pb_percent;
  const percentile = pct ?? val.pb_percent ?? 0;
  const act = action(cfg, disc, percentile);
  const monthly = buyAmount(categoryRule(cfg, disc), percentile);

  // 简洁理由（新闻在报告的「市场解读」段落统一呈现，不在这里重复）
  const indexLabel = fund.index_name || val.name || index_code || "未知指数";
  const reasoning =
    `${indexLabel} ${metric.toUpperCase()} 分位 ${percentile.toFixed(2)}%，纪律动作 ${act}。` +
    (monthly > 0 ? ` 建议月投 ${monthly} 元。` : "");

  return {
    fund_code: fund.fund_code,
    fund_name: fund.fund_name,
    category,
    index_code,
    index_name: fund.index_name ?? val.name ?? "",
    metric,
    percentile,
    action: act,
    monthly_amount: monthly,
    reasoning,
  };
}

export function advisePortfolio(
  funds: FundRecord[],
  valuations: Valuation[],
  cfg: StrategyConfig,
): { advices: Record<string, unknown>[]; alerts: ReturnType<typeof checkRules> } {
  const lookup = buildLookup(valuations);
  const advices = funds.map((f) => adviseFund(f, lookup, cfg));
  const alerts = checkRules(cfg, funds);
  return { advices, alerts };
}
