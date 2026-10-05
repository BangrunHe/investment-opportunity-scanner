// 雪球基金（蛋卷）估值抓取（转写自 src/fetch.py）

import { DANJUAN_API } from "./config.ts";

export interface Valuation {
  index_code: string;
  name: string;
  pe: number | null;
  pb: number | null;
  pe_percent: number | null; // 百分位 0~100
  pb_percent: number | null;
}

const toPercent = (frac: number | null) =>
  frac == null ? null : Math.round(frac * 10000) / 100;

export async function fetchAllValuations(): Promise<Valuation[]> {
  const resp = await fetch(DANJUAN_API, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
      Accept: "application/json",
      Referer: "https://danjuanfunds.com/rn/value-center",
    },
  });
  if (!resp.ok) throw new Error(`danjuan fetch failed: ${resp.status}`);
  const data = await resp.json();
  const items: any[] = data?.data?.items ?? [];
  return items.map((it) => ({
    index_code: it.index_code,
    name: it.name ?? "",
    pe: it.pe ?? null,
    pb: it.pb ?? null,
    pe_percent: toPercent(it.pe_percentile),
    pb_percent: toPercent(it.pb_percentile),
  }));
}
