// 多模态 OCR：基金持仓截图 -> 结构化（DashScope qwen3.8-flash）

import { DASHSCOPE_BASE } from "./config.ts";

const EXTRACT_SYSTEM =
  "你是基金持仓截图的结构化提取工具。从图片中提取每只基金的持仓信息，" +
  "只输出 JSON 数组，每个元素字段为：fund_code、fund_name、holding_assets、" +
  "holding_cost、holding_profit、holding_shares、unit_cost、week_nav。" +
  "数字只保留数值（去掉逗号与单位，负号保留），无法识别的字段填 null。";

function parseList(text: string): unknown[] {
  let t = text.trim();
  if (t.startsWith("```")) t = t.replace(/```(json)?/g, "").trim();
  try {
    const d = JSON.parse(t);
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d.items)) return d.items;
    return [d];
  } catch {
    const s = t.indexOf("[");
    const e = t.lastIndexOf("]");
    if (s !== -1 && e > s) {
      try {
        return JSON.parse(t.slice(s, e + 1));
      } catch {
        return [];
      }
    }
    return [];
  }
}

export async function extractFromImage(base64: string, mimeType = "image/jpeg"): Promise<unknown[]> {
  const key = Deno.env.get("VISION_API_KEY");
  const model = Deno.env.get("VISION_MODEL") || "qwen3.8-flash";
  if (!key) throw new Error("missing VISION_API_KEY");

  const resp = await fetch(`${DASHSCOPE_BASE}/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: EXTRACT_SYSTEM },
        {
          role: "user",
          content: [
            { type: "text", text: "请提取这张基金持仓截图中的结构化数据。" },
            { type: "image_url", image_url: { url: `data:${mimeType};base64,${base64}` } },
          ],
        },
      ],
      temperature: 0.1,
      max_tokens: 1500,
    }),
  });
  if (!resp.ok) throw new Error(`ocr failed: ${resp.status} ${await resp.text()}`);
  const data = await resp.json();
  const content = data?.choices?.[0]?.message?.content ?? "";
  return parseList(content);
}
