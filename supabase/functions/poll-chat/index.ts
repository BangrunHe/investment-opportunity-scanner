// Edge Function：poll-chat（群消息模式）
// 轮询群会话，拾取用户发的持仓截图 -> OCR -> 入库 -> 群里反馈 -> 留档到多维表格
// 不依赖飞书反向推送（飞书 -> Supabase），改为主动拉取（Supabase -> 飞书），更稳定。
//
// 基金代码策略（方案 C）：
//   1. 按 OCR 出的基金名从静态库反查；查到直接入库
//   2. 查不到 -> 在群里问用户要 6 位代码，用户回复后自动补全入库

import { supabase } from "../_shared/supabaseClient.ts";
import {
  createRecord,
  downloadMessageImage,
  listMessages,
  sendImMessage,
  type ChatMessage,
} from "../_shared/feishu.ts";
import {
  currentWeek,
  holdingsSummary,
  lookupCodeByName,
  ocrToRows,
  tableConfig,
  writeHoldings,
  type Holding,
} from "../_shared/holdings.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const MAX_PER_RUN = 10; // 单次最多处理多少条消息，避免函数超时

function parseContent(m: ChatMessage): Record<string, unknown> {
  try {
    return JSON.parse(m.body?.content ?? "{}") as Record<string, unknown>;
  } catch {
    return {};
  }
}

function extractCode(text: string): string {
  const m = text.match(/(\d{6})/);
  return m ? m[1] : "";
}

async function archive(appToken: string, tableId: string, code: string, results: string[]) {
  // 往多维表格写一条留档（图片字段需额外上传，这里只写文本字段）
  try {
    await createRecord(appToken, tableId, {
      基金代码: code,
      状态: "已识别",
      识别结果: results.join("\n"),
    });
  } catch (e) {
    console.warn("留档失败：", String(e));
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });

  try {
    const chatId = Deno.env.get("FEISHU_CHAT_ID");
    if (!chatId) throw new Error("缺少 FEISHU_CHAT_ID");

    const db = supabase();
    const week = currentWeek();
    const { appToken, tableId } = tableConfig();

    // 已处理过的消息（幂等）
    const { data: doneRows } = await db.from("processed_messages").select("message_id");
    const done = new Set((doneRows ?? []).map((r) => r.message_id as string));

    const messages = await listMessages(chatId);
    const handled: unknown[] = [];
    let count = 0;

    for (const m of messages) {
      if (count >= MAX_PER_RUN) break;
      if (done.has(m.message_id)) continue;
      // 跳过机器人自己发的消息
      if ((m.sender?.sender_type ?? "") === "app") continue;

      try {
        if (m.msg_type === "image") {
          const imageKey = String(parseContent(m).image_key ?? "");
          if (!imageKey) throw new Error("图片消息缺少 image_key");

          const bytes = await downloadMessageImage(m.message_id, imageKey);
          const rows = await ocrToRows(bytes);

          if (!rows.length) {
            await sendImMessage(chatId, "⚠️ 没识别出持仓信息，请确认截图是基金持仓页。");
          } else {
            const name = String(rows[0].fund_name ?? "");
            const code = await lookupCodeByName(name);
            if (code) {
              const { results } = await writeHoldings(rows, code, week);
              await sendImMessage(chatId, `✅ 已入库\n\n${await holdingsSummary(week)}`);
              await archive(appToken, tableId, code, results);
              handled.push({ type: "image", name, code, results });
            } else {
              await db.from("pending_snapshots").insert({
                message_id: m.message_id,
                fund_name: name,
                payload: rows,
              });
              await sendImMessage(
                chatId,
                `❓ 未找到「${name}」的基金代码。\n请回复 6 位代码（如 110022），我会自动补上入库。`,
              );
              handled.push({ type: "image", name, code: null });
            }
          }
        } else if (m.msg_type === "text") {
          const text = String(parseContent(m).text ?? "");
          const code = extractCode(text);
          if (!code) continue; // 不是代码消息，忽略（不计入已处理）

          const { data: pend } = await db
            .from("pending_snapshots")
            .select("*")
            .order("created_at", { ascending: false })
            .limit(1);
          const p = pend?.[0];
          if (!p) continue; // 没有待补快照，忽略

          const rows = (p.payload ?? []) as Holding[];
          const { results } = await writeHoldings(rows, code, week);
          await db.from("pending_snapshots").delete().eq("id", p.id);
          await sendImMessage(chatId, `✅ 已补全并入库（${code}）\n\n${await holdingsSummary(week)}`);
          await archive(appToken, tableId, code, results);
          handled.push({ type: "text", code, results });
        } else {
          continue; // 其它类型不处理，也不标记已处理
        }
      } catch (e) {
        console.warn(`处理消息 ${m.message_id} 失败：`, String(e));
        handled.push({ type: m.msg_type, error: String(e) });
      }

      // 标记为已处理
      await db.from("processed_messages").insert({ message_id: m.message_id });
      count++;
    }

    return new Response(JSON.stringify({ ok: true, scanned: messages.length, handled }), {
      headers: { ...cors, "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, message: String(e) }), {
      status: 400,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  }
});
