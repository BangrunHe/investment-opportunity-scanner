// 财经新闻采集（新浪财经快讯）

import { NEWS_URL } from "./config.ts";

export interface NewsItem {
  title: string;
  url: string;
  time: string;
}

export interface NewsResult {
  items: NewsItem[];
  error?: string;
}

/** 抓取财经快讯；失败时返回 error 便于排查 */
export async function fetchNews(limit = 30): Promise<NewsResult> {
  const url = `${NEWS_URL}?pageid=153&lid=2516&k=&num=${limit}&page=1`;
  try {
    const resp = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        Accept: "application/json",
      },
    });
    if (!resp.ok) return { items: [], error: `HTTP ${resp.status}` };
    const text = await resp.text();
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(text);
    } catch {
      return { items: [], error: `非 JSON 响应（前 80 字）：${text.slice(0, 80)}` };
    }
    const raw = ((data?.result as Record<string, unknown>)?.data ?? []) as unknown[];
    const items = raw
      .map((it) => {
        const o = it as Record<string, unknown>;
        return { title: String(o.title ?? ""), url: String(o.url ?? ""), time: String(o.ctime ?? "") };
      })
      .filter((x) => x.title)
      .slice(0, limit);
    return { items };
  } catch (e) {
    return { items: [], error: String(e) };
  }
}

export function relevantNews(items: NewsItem[], keywords: string[], top = 8): NewsItem[] {
  if (!keywords.length) return items.slice(0, top);
  const scored = items
    .map((it) => ({
      score: keywords.reduce((s, k) => s + (k && it.title.includes(k) ? 1 : 0), 0),
      it,
    }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored.slice(0, top).map((x) => x.it);
}
