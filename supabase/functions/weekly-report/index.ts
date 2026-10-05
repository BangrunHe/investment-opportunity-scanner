// Edge Function：weekly-report
// 每周一由 pg_cron 触发：读持仓+估值 -> 新闻 -> AI分类 -> 组合建议 -> 飞书提醒

import { supabase } from "../_shared/supabaseClient.ts";
import { DEFAULT_CONFIG, type StrategyConfig } from "../_shared/config.ts";
import { fetchAllValuations } from "../_shared/danjuan.ts";
import { availableIndexOptions, classify } from "../_shared/classify.ts";
import { fetchNews, relevantNews } from "../_shared/news.ts";
import { advisePortfolio } from "../_shared/advisor.ts";
import { sendReminder } from "../_shared/feishu.ts";
import { latestHoldingsSummary } from "../_shared/holdings.ts";
import { chatJson } from "../_shared/llm.ts";

// 操作类型 -> 展示文案（数组顺序即报告里的分组顺序）
const ACTION_META: Record<string, { label: string; emoji: string }> = {
  buy: { label: "建议买入", emoji: "🟢" },
  hold: { label: "继续持有", emoji: "🟡" },
  pause: { label: "暂停定投", emoji: "⏸️" },
  sell_zone: { label: "进入卖出区", emoji: "🔴" },
  rebalance: { label: "黄金再平衡", emoji: "⚖️" },
  unknown: { label: "未匹配指数（需补充）", emoji: "❔" },
};
const ACTION_ORDER = ["buy", "hold", "pause", "sell_zone", "rebalance", "unknown"];

async function loadConfig(db: ReturnType<typeof supabase>): Promise<StrategyConfig> {
  const cfg: StrategyConfig = structuredClone(DEFAULT_CONFIG);
  const { data } = await db.from("strategy_config").select("key,value");
  for (const row of data ?? []) {
    const v = row.value as unknown;
    if (row.key === "large_cap") cfg.large_cap = v as StrategyConfig["large_cap"];
    else if (row.key === "chinext") cfg.chinext = v as StrategyConfig["chinext"];
    else if (row.key === "star50") cfg.star50 = v as StrategyConfig["star50"];
    else if (row.key === "sell") cfg.sell = v as StrategyConfig["sell"];
    else if (row.key === "portfolio") cfg.portfolio = v as StrategyConfig["portfolio"];
    else if (row.key === "industry_discipline") cfg.industry_discipline = v as string;
  }
  return cfg;
}

async function summarizeMarket(newsText: string): Promise<{ text: string; error?: string }> {
  if (!newsText) return { text: "", error: "没有可用新闻" };
  try {
    const r = await chatJson([
      {
        role: "system",
        content:
          "你是市场新闻解读助手。根据给出的财经快讯，输出 JSON 对象：" +
          "summary（一句话市场背景，60 字内）、risks（字符串数组，2-4 条，每条 40 字内）。\n" +
          "优先解读与中国 A 股 / 港股相关、以及影响用户持仓行业（医药、互联网、新能源、红利低波、黄金）的消息；" +
          "若快讯中确实没有相关国内信息，再简要概述全球市场。不要罗列与持仓无关的国际琐闻。",
      },
      { role: "user", content: newsText },
    ]);
    if (typeof r !== "object" || r === null) return { text: "", error: "模型返回异常" };
    const parts: string[] = [];
    if (r.summary) parts.push("市场背景：" + r.summary);
    if (Array.isArray(r.risks) && r.risks.length) parts.push("关注点：" + (r.risks as string[]).join("；"));
    return { text: parts.join("\n") };
  } catch (e) {
    return { text: "", error: String(e) };
  }
}

Deno.serve(async () => {
  try {
    const db = supabase();
    const cfg = await loadConfig(db);

    // 1. 估值
    const valuations = await fetchAllValuations();

    // 2. 静态库 + 最新持仓
    const { data: staticRows } = await db.from("static_funds").select("*");
    const { data: holdingRows } = await db.from("fund_holdings").select("*");

    const fundsMap: Record<string, Record<string, unknown>> = {};
    for (const h of holdingRows ?? []) {
      const code = h.fund_code as string;
      if (!code) continue;
      if (!fundsMap[code] || (h.week as string) >= (fundsMap[code].week as string)) fundsMap[code] = h;
    }
    const fundList = Object.values(fundsMap);

    const staticMap = new Map((staticRows ?? []).map((s) => [s.fund_code, s]));
    for (const f of fundList) {
      const s = staticMap.get(f.fund_code as string);
      f.category = f.category || s?.category || "satellite";
      f.index_code = f.index_code || s?.index_code;
      f.index_name = f.index_name || s?.index_name;
    }

    // 3. AI 分类（仅对尚未分类的基金）
    const options = await availableIndexOptions();
    for (const s of staticRows ?? []) {
      if (s.index_code || s.status === "confirmed") continue;
      const cls = await classify(s.fund_code as string, s.fund_name as string, options);
      await db
        .from("static_funds")
        .update({
          index_code: cls.index_code,
          index_name: cls.index_name,
          category: cls.category,
          status: "pending_confirm",
        })
        .eq("fund_code", s.fund_code);
      const f = fundList.find((x) => x.fund_code === s.fund_code);
      if (f) {
        f.index_code = cls.index_code;
        f.index_name = cls.index_name;
        f.category = cls.category;
      }
    }

    // 4. 新闻 + 市场解读
    //    关键词只用「指数名」（新闻里可能出现），基金全名太长几乎不会命中
    const keywords = Array.from(
      new Set(fundList.map((f) => String(f.index_name ?? "")).filter((s) => s.length >= 2)),
    );
    const newsRes = await fetchNews(40);
    const rel = relevantNews(newsRes.items, keywords, 10);
    // 命中不足时补充通用财经头条，保证 AI 有解读素材（否则市场解读会整段为空）
    if (rel.length < 5) {
      const seen = new Set(rel.map((x) => x.title));
      for (const it of newsRes.items) {
        if (rel.length >= 10) break;
        if (!seen.has(it.title)) {
          rel.push(it);
          seen.add(it.title);
        }
      }
    }
    const newsText = rel.length ? "近期财经快讯：\n" + rel.map((n) => `- ${n.title}`).join("\n") : "";
    const market = await summarizeMarket(newsText);
    const marketContext = market.text;

    // 5. 组合建议
    const { advices, alerts } = advisePortfolio(fundList, valuations, cfg);

    // 6. 组织飞书消息：按「操作类型」分组，而不是按持仓逐只列
    const lines: string[] = ["【周度定投提醒】", ""];
    for (const key of ACTION_ORDER) {
      const items = advices.filter((a) => String(a.action ?? "unknown") === key);
      if (!items.length) continue;
      const meta = ACTION_META[key] ?? { label: key, emoji: "•" };
      lines.push(`${meta.emoji} ${meta.label}（${items.length} 只）`);
      for (const a of items) {
        lines.push(`  · ${a.fund_name}（${a.fund_code ?? "-"}）`);
        lines.push(`    ${a.reasoning}`);
      }
      lines.push("");
    }

    if (marketContext) {
      lines.push("【市场解读】");
      lines.push(marketContext);
      lines.push("");
    }

    lines.push("【组合提醒】");
    if (alerts.length) {
      for (const al of alerts) lines.push(`· ${al.message}`);
    } else {
      lines.push("· 无");
    }

    // 持仓总览（每只基金取最新一周记录）
    lines.push("");
    lines.push(await latestHoldingsSummary());

    const notify = await sendReminder(lines.join("\n"));

    return new Response(
      JSON.stringify({
        ok: true,
        funds: fundList.length,
        advices,
        notify,
        // 诊断字段
        news_total: newsRes.items.length,
        news_relevant: rel.length,
        news_error: newsRes.error ?? null,
        market_error: market.error ?? null,
        market_len: marketContext.length,
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: String(e) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
