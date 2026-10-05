// DeepSeek 文本大模型（OpenAI 兼容 chat/completions）

import { DEEPSEEK_BASE } from "./config.ts";

function parseJson(text: string): unknown {
  let t = text.trim();
  if (t.startsWith("```")) t = t.replace(/```(json)?/g, "").trim();
  try {
    return JSON.parse(t);
  } catch {
    const s = t.indexOf("{");
    const e = t.lastIndexOf("}");
    if (s !== -1 && e > s) {
      try {
        return JSON.parse(t.slice(s, e + 1));
      } catch {
        return { raw: t };
      }
    }
    return { raw: t };
  }
}

export async function chatJson(
  messages: unknown[],
  opts?: { max_tokens?: number; temperature?: number },
): Promise<Record<string, unknown>> {
  const key = Deno.env.get("DEEPSEEK_API_KEY");
  if (!key) throw new Error("missing DEEPSEEK_API_KEY");
  const resp = await fetch(`${DEEPSEEK_BASE}/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model: "deepseek-chat",
      messages,
      temperature: opts?.temperature ?? 0.3,
      max_tokens: opts?.max_tokens ?? 1200,
      stream: false,
    }),
  });
  if (!resp.ok) throw new Error(`llm failed: ${resp.status} ${await resp.text()}`);
  const data = await resp.json();
  const text = (data?.choices?.[0]?.message?.content ?? "").trim();
  return parseJson(text) as Record<string, unknown>;
}
