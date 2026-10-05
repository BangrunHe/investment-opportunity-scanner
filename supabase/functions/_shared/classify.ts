// AI 基金归属指数分类
//
// 雪球基金只提供 63 个指数，基金真实跟踪的指数可能不在其中（如「港股通创新药」）。
// 策略：要求 AI 从列表里挑「行业/主题最接近」的作为代理指数；
//       若 AI 返回了列表外的代码，会带纠正信息重试一次。

import { chatJson } from "./llm.ts";
import { fetchAllValuations } from "./danjuan.ts";

export interface IndexOption {
  index_code: string | null;
  name: string;
}

export async function availableIndexOptions(): Promise<IndexOption[]> {
  const vals = await fetchAllValuations();
  const opts: IndexOption[] = vals
    .filter((v) => v.index_code)
    .map((v) => ({ index_code: v.index_code, name: v.name }));
  opts.push({ index_code: null, name: "黄金类（黄金/贵金属基金）" });
  return opts;
}

const SYSTEM =
  "你是一名基金研究分析师。给定基金代码、名称与「可选指数列表」，" +
  "为该基金选出用于估值跟踪的指数。\n" +
  "【硬性规则】\n" +
  "1. index_code 必须**逐字复制**自「可选指数列表」，严禁使用列表之外的代码。\n" +
  "2. 基金实际跟踪的指数可能不在列表里；此时请挑选**行业/主题最接近**的列表内指数作为代理。" +
  "参考：「港股通创新药/生物医药」→ 中证医疗或全指医药；「港股通互联网」→ 中国互联；" +
  "「半导体/芯片/电子」→ 中证电子；「军工」→ 中证军工；「白酒/食品饮料」→ 中证白酒或国证食品。\n" +
  "3. 除黄金类外，index_code 一律不得为 null。\n" +
  "4. 黄金/贵金属类基金：index_code 填 null、category 填 gold。\n" +
  "只输出 JSON 对象，字段固定为：index_code、index_name、category、confidence、reasoning。\n" +
  "category 取值：core（宽基/策略指数基金）、satellite（行业/主题指数基金）、gold（黄金类）。\n" +
  "confidence：完全对应填 high；代理匹配填 low。\n" +
  "reasoning 中请同时说明「该基金实际跟踪的指数」与「你选了哪个代理指数及原因」。";

/** 校验 index_code 必须在列表内；黄金返回 null */
function validateCode(
  code: unknown,
  category: string,
  indexName: string | undefined,
  options: IndexOption[],
): string | null {
  if (category === "gold") return null;
  const valid = new Set(options.map((o) => o.index_code));
  if (typeof code === "string" && valid.has(code)) return code;
  // 名称兜底匹配
  if (indexName) {
    for (const o of options) {
      const n = o.name || "";
      if (n && (n.includes(indexName) || indexName.includes(n))) return o.index_code;
    }
  }
  return null;
}

export async function classify(
  fund_code: string,
  fund_name: string,
  options: IndexOption[],
): Promise<Record<string, unknown>> {
  const optsText = options.map((o) => `- ${o.index_code ?? "null"} : ${o.name}`).join("\n");
  const userPrompt =
    `基金代码：${fund_code}\n基金名称：${fund_name}\n\n` +
    `可选指数列表（index_code : 名称）：\n${optsText}\n\n` +
    `请从上面列表中选出一个 index_code 作为该基金的估值跟踪指数。`;

  const messages: Record<string, unknown>[] = [
    { role: "system", content: SYSTEM },
    { role: "user", content: userPrompt },
  ];

  let result = await chatJson(messages);
  let category = (result.category as string) || "satellite";
  let indexCode = validateCode(
    result.index_code,
    category,
    result.index_name as string | undefined,
    options,
  );

  // 若 AI 返回了列表外的代码（通常是基金真实跟踪的指数，雪球没有），
  // 带纠正信息重试一次，强制它从列表里挑代理指数
  if (!indexCode && category !== "gold") {
    messages.push({ role: "assistant", content: JSON.stringify(result) });
    messages.push({
      role: "user",
      content:
        `你给出的 index_code = ${JSON.stringify(result.index_code)} 不在可选列表中。\n` +
        `请改为从列表中挑选「行业/主题最接近」的那一个作为代理指数，例如：\n` +
        `  · 港股通创新药 / 生物医药 → 中证医疗（SZ399989）或 全指医药（SH000991）\n` +
        `  · 港股通互联网 → 中国互联（CSIH11136）\n` +
        `  · 半导体 / 芯片 → 中证电子（CSI930652）\n` +
        `只输出 JSON，且 index_code 必须是列表里原样存在的代码。`,
    });
    const retry = await chatJson(messages);
    const retryCode = validateCode(
      retry.index_code,
      (retry.category as string) || category,
      retry.index_name as string | undefined,
      options,
    );
    if (retryCode) {
      result = retry;
      category = (retry.category as string) || category;
      indexCode = retryCode;
    }
  }

  return {
    fund_code,
    fund_name,
    index_code: indexCode,
    index_name: (result.index_name as string) || "",
    category,
    confidence: (result.confidence as string) || "low",
    reasoning: (result.reasoning as string) || "",
  };
}
