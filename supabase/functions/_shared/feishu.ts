// 飞书开放平台接口：tenant token / 群消息 / 多维表格留档 / 应用机器人发消息

export interface TokenCache {
  value: string;
  expire: number;
}

let cached: TokenCache | null = null;

export async function getTenantToken(): Promise<string> {
  if (cached && Date.now() < cached.expire) return cached.value;
  const appId = Deno.env.get("FEISHU_APP_ID");
  const appSecret = Deno.env.get("FEISHU_APP_SECRET");
  if (!appId || !appSecret) throw new Error("missing FEISHU_APP_ID / FEISHU_APP_SECRET");

  const resp = await fetch(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
    },
  );
  const data = await resp.json();
  if (!data.tenant_access_token) throw new Error(`feishu token failed: ${JSON.stringify(data)}`);
  cached = { value: data.tenant_access_token, expire: Date.now() + (data.expire - 60) * 1000 };
  return cached.value;
}

// ---------- 群消息（输入通道） ----------

export interface ChatMessage {
  message_id: string;
  msg_type: string;
  create_time?: string;
  body?: { content?: string };
  sender?: { id?: string; sender_type?: string };
}

/** 拉取群会话历史消息（轮询方式，避免飞书反向推送）
 *  取「最新的一页」再反转成时间正序：群消息变多后仍能拿到新消息，
 *  同时保持「图片 -> 回复代码」的先后顺序。 */
export async function listMessages(chatId: string, pageSize = 50): Promise<ChatMessage[]> {
  const t = await getTenantToken();
  const params = new URLSearchParams({
    container_id_type: "chat",
    container_id: chatId,
    sort_type: "ByCreateTimeDesc",
    page_size: String(pageSize),
  });

  const resp = await fetch(`https://open.feishu.cn/open-apis/im/v1/messages?${params}`, {
    headers: { Authorization: `Bearer ${t}` },
  });
  const data = await resp.json();
  if (data?.code !== 0) {
    throw new Error(`feishu list messages failed: ${JSON.stringify(data).slice(0, 200)}`);
  }
  const items = (data?.data?.items ?? []) as ChatMessage[];
  return items.reverse();
}

/** 下载群消息里的图片资源 */
export async function downloadMessageImage(messageId: string, fileKey: string): Promise<Uint8Array> {
  const t = await getTenantToken();
  const resp = await fetch(
    `https://open.feishu.cn/open-apis/im/v1/messages/${messageId}/resources/${fileKey}?type=image`,
    { headers: { Authorization: `Bearer ${t}` } },
  );
  if (!resp.ok) throw new Error(`feishu message image download failed: ${resp.status}`);
  return new Uint8Array(await resp.arrayBuffer());
}

/** 向多维表格写入一条记录（快照留档） */
export async function createRecord(
  appToken: string,
  tableId: string,
  fields: Record<string, unknown>,
): Promise<void> {
  const t = await getTenantToken();
  const resp = await fetch(
    `https://open.feishu.cn/open-apis/bitable/v1/apps/${appToken}/tables/${tableId}/records`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
      body: JSON.stringify({ fields }),
    },
  );
  const data = await resp.json();
  if (data?.code !== 0) {
    throw new Error(`feishu create record failed: ${JSON.stringify(data).slice(0, 200)}`);
  }
}

// ---------- 发消息（提醒通道） ----------

/** 发提醒：优先用应用机器人发到群，其次自定义机器人 webhook */
export async function sendReminder(text: string): Promise<string> {
  const chatId = Deno.env.get("FEISHU_CHAT_ID");
  if (chatId) {
    await sendImMessage(chatId, text);
    return "app";
  }
  if (Deno.env.get("FEISHU_BOT_WEBHOOK")) {
    await sendBotMessage(text);
    return "webhook";
  }
  console.warn("未配置 FEISHU_CHAT_ID / FEISHU_BOT_WEBHOOK，已跳过飞书提醒");
  return "skipped";
}

/** 应用机器人发消息到群（需 im:message:send_as_bot 权限，且应用已在群内） */
export async function sendImMessage(chatId: string, text: string): Promise<void> {
  const token = await getTenantToken();
  for (const c of splitText(text, 3800)) {
    const resp = await fetch(
      "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          receive_id: chatId,
          msg_type: "text",
          content: JSON.stringify({ text: c }),
        }),
      },
    );
    if (!resp.ok) {
      throw new Error(`feishu im send failed: ${resp.status} ${await resp.text()}`);
    }
  }
}

/** 备选：自定义机器人 webhook（无需消息权限） */
export async function sendBotMessage(text: string): Promise<void> {
  const webhook = Deno.env.get("FEISHU_BOT_WEBHOOK");
  if (!webhook) return;
  const secret = Deno.env.get("FEISHU_BOT_SECRET");
  for (const c of splitText(text, 3800)) {
    const body: Record<string, unknown> = { msg_type: "text", content: { text: c } };
    if (secret) {
      const timestamp = Math.floor(Date.now() / 1000).toString();
      body.timestamp = timestamp;
      body.sign = await sign(timestamp, secret);
    }
    await fetch(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
}

// 飞书自定义机器人签名：base64(hmac_sha256(key = timestamp + "\n" + secret, data = ""))
async function sign(timestamp: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(`${timestamp}\n${secret}`),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new Uint8Array(0));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

function splitText(text: string, size: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size));
  return out;
}
