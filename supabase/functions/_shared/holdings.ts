// 持仓处理共用逻辑：多模态 OCR + 基金代码解析 + 写库（幂等 upsert）

import { encodeBase64 } from "jsr:@std/encoding/base64";
import { supabase } from "./supabaseClient.ts";
import { extractFromImage } from "./ocr.ts";

const NUM_FIELDS = [
  "holding_assets",
  "holding_cost",
  "holding_profit",
  "holding_shares",
  "unit_cost",
  "week_nav",
];

export interface Holding {
  fund_code?: string | null;
  fund_name?: string | null;
  holding_assets?: number | null;
  holding_cost?: number | null;
  holding_profit?: number | null;
  holding_shares?: number | null;
  unit_cost?: number | null;
  week_nav?: number | null;
}

export interface WriteResult {
  results: string[]; // 成功写入的说明
  missing: string[]; // 缺基金代码的基金名
}

function toNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return v;
  const n = Number(String(v).replace(/,/g, "").trim());
  return Number.isNaN(n) ? null : n;
}

function cleanHolding(row: Record<string, unknown>): Holding {
  const out: Record<string, unknown> = { ...row };
  for (const f of NUM_FIELDS) out[f] = toNum(out[f]);
  return out as Holding;
}

/** 当前周（周一到周日，北京时间） */
export function currentWeek(): string {
  const now = new Date(Date.now() + 8 * 3600 * 1000);
  const day = now.getUTCDay();
  const diff = (day + 6) % 7;
  const monday = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - diff));
  const sunday = new Date(monday.getTime() + 6 * 86400 * 1000);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return `${fmt(monday)}~${fmt(sunday)}`;
}

/** 多维表格位置（用于留档） */
export function tableConfig(): { appToken: string; tableId: string } {
  const appToken = Deno.env.get("FEISHU_BITABLE_APP_TOKEN");
  const tableId = Deno.env.get("FEISHU_BITABLE_TABLE_ID");
  if (!appToken || !tableId) {
    throw new Error("缺少 FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID");
  }
  return { appToken, tableId };
}

/** 图片字节 -> 结构化持仓（多模态 OCR） */
export async function ocrToRows(bytes: Uint8Array): Promise<Holding[]> {
  const base64 = encodeBase64(bytes);
  const rows = await extractFromImage(base64, "image/jpeg");
  return rows.map((r) => cleanHolding(r as Record<string, unknown>)).filter((r) => r.fund_name);
}

/** 按基金名从静态库反查基金代码（已入过库的基金） */
export async function lookupCodeByName(name: string): Promise<string> {
  const db = supabase();
  const { data } = await db.from("static_funds").select("fund_code").eq("fund_name", name).limit(1);
  return (data?.[0]?.fund_code as string) ?? "";
}

/** 写入持仓：static_funds + fund_holdings + holding_snapshots（幂等） */
export async function writeHoldings(
  rows: Holding[],
  providedCode: string,
  week: string,
): Promise<WriteResult> {
  const db = supabase();
  const results: string[] = [];
  const missing: string[] = [];

  for (const h of rows) {
    const name = String(h.fund_name ?? "").trim();
    if (!name) continue;

    const code = providedCode || (await lookupCodeByName(name));
    if (!code) {
      missing.push(name);
      continue;
    }

    // 静态库：仅新增，不覆盖已有分类
    await db.from("static_funds").upsert(
      { fund_code: code, fund_name: name, status: "pending_classify" },
      { onConflict: "fund_code", ignoreDuplicates: true },
    );
    await db.from("fund_holdings").upsert(
      {
        fund_code: code,
        fund_name: name,
        holding_assets: h.holding_assets,
        holding_cost: h.holding_cost,
        holding_profit: h.holding_profit,
        holding_shares: h.holding_shares,
        unit_cost: h.unit_cost,
        week_nav: h.week_nav,
        week,
      },
      { onConflict: "week,fund_code" },
    );
    await db.from("holding_snapshots").upsert(
      { week, fund_code: code, fund_name: name, holding_assets: h.holding_assets },
      { onConflict: "week,fund_code" },
    );
    results.push(`${name}（${code}）：已写入`);
  }

  return { results, missing };
}

// ---------- 纯文本等宽表格（飞书文本消息不支持真表格，用对齐模拟） ----------

const WIDE = /[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/;

/** 显示宽度：中文/全角算 2，其余算 1 */
export function displayWidth(s: string): number {
  let w = 0;
  for (const ch of s) w += WIDE.test(ch) ? 2 : 1;
  return w;
}

function padRight(s: string, width: number): string {
  return s + " ".repeat(Math.max(0, width - displayWidth(s)));
}

function padLeft(s: string, width: number): string {
  return " ".repeat(Math.max(0, width - displayWidth(s))) + s;
}

function truncateDisplay(s: string, max: number): string {
  if (displayWidth(s) <= max) return s;
  let out = "";
  let w = 0;
  for (const ch of s) {
    const cw = displayWidth(ch);
    if (w + cw > max - 1) break;
    out += ch;
    w += cw;
  }
  return out + "…";
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface HoldingLine {
  fund_code: string;
  fund_name: string;
  holding_assets: number | null;
  category?: string | null;
}

// 分类展示名与排序（宽基 -> 卫星 -> 黄金 -> 未分类）
const CATEGORY_LABEL: Record<string, string> = {
  core: "宽基",
  satellite: "卫星",
  gold: "黄金",
};
const CATEGORY_ORDER: Record<string, number> = { core: 0, satellite: 1, gold: 2 };

const CAT_W = 6;
const NAME_W = 20;
const AMT_W = 12;
const PCT_W = 7;

function fmtTotal(v: number): string {
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function renderHoldingsTable(rows: HoldingLine[], title: string): string {
  const total = rows.reduce((s, r) => s + (r.holding_assets || 0), 0);
  const sorted = [...rows].sort((a, b) => {
    const ca = CATEGORY_ORDER[String(a.category ?? "")] ?? 9;
    const cb = CATEGORY_ORDER[String(b.category ?? "")] ?? 9;
    if (ca !== cb) return ca - cb;
    return (b.holding_assets || 0) - (a.holding_assets || 0); // 同类内金额降序
  });

  const lines = [
    title,
    padRight("分类", CAT_W) +
      padRight("基金", NAME_W) +
      padLeft("金额", AMT_W) +
      padLeft("占比", PCT_W),
    "─".repeat(CAT_W + NAME_W + AMT_W + PCT_W),
  ];
  for (const r of sorted) {
    const pct = total > 0 ? ((r.holding_assets || 0) / total) * 100 : 0;
    lines.push(
      padRight(CATEGORY_LABEL[String(r.category ?? "")] ?? "未分类", CAT_W) +
        padRight(truncateDisplay(r.fund_name || r.fund_code, NAME_W), NAME_W) +
        padLeft(fmtNum(r.holding_assets), AMT_W) +
        padLeft(pct.toFixed(1) + "%", PCT_W),
    );
  }
  return lines.join("\n");
}

/** fund_code -> category（分类存在静态库） */
async function categoryMap(): Promise<Map<string, string>> {
  const db = supabase();
  const { data } = await db.from("static_funds").select("fund_code,category");
  return new Map(
    (data ?? []).map((s) => [s.fund_code as string, String(s.category ?? "")] as [string, string]),
  );
}

/** 指定周的持仓总览（用于「刚入库」的反馈） */
export async function holdingsSummary(week: string): Promise<string> {
  const db = supabase();
  const { data } = await db
    .from("fund_holdings")
    .select("fund_code,fund_name,holding_assets")
    .eq("week", week);

  const rows = (data ?? []) as HoldingLine[];
  if (!rows.length) return "（暂无持仓记录）";

  const cats = await categoryMap();
  for (const r of rows) r.category = cats.get(r.fund_code) ?? "";
  return renderHoldingsTable(rows, `📋 当前持仓（${rows.length} 只 · ${week}）`);
}

/** 持仓总览：每只基金取「最新一周」的记录（用于周报；跨周也能显示全） */
export async function latestHoldingsSummary(): Promise<string> {
  const db = supabase();
  const { data } = await db
    .from("fund_holdings")
    .select("fund_code,fund_name,holding_assets,week")
    .order("week", { ascending: true });

  const rows = (data ?? []) as (HoldingLine & { week: string })[];
  if (!rows.length) return "（暂无持仓记录）";

  // 升序遍历，后面的（更新的周）覆盖前面的
  const latest = new Map<string, HoldingLine & { week: string }>();
  for (const r of rows) latest.set(r.fund_code, r);
  const list = Array.from(latest.values());

  const cats = await categoryMap();
  for (const r of list) r.category = cats.get(r.fund_code) ?? "";

  const total = list.reduce((s, r) => s + (r.holding_assets || 0), 0);
  return renderHoldingsTable(list, `📋 持仓总览（${list.length} 只 · 合计 ${fmtTotal(total)} 元）`);
}
