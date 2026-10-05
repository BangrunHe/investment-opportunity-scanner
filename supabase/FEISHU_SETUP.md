# Feishu Setup

Follow these steps in order. When you finish you will have **one group** and **one table**,
plus the five values the backend needs.

| Value you will end up with | Used for |
|---|---|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | App credentials |
| `FEISHU_CHAT_ID` | The group used for input and notifications |
| `FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID` | The archive table |

> Mainland China: <https://open.feishu.cn/app> · International (Lark): <https://open.larksuite.com/app>

---

## 0 · Prerequisites

Feishu apps belong to an organisation (a "tenant"). If you do not have one yet, create a free
team in the Feishu client first — a personal team is enough.

You need to be an **admin** of that team, or hold **developer** rights. On a team you created
yourself you already are.

---

## 1 · Create a custom app

1. Open <https://open.feishu.cn/app> and click **Create Custom App**.
2. Fill in a name (for example `Fund Assistant`), a description and an icon.
3. Open the app you just created.

---

## 2 · Get the App ID and App Secret

In the app, open **Credentials & Basic Info** in the left sidebar.

| What you see | Where it goes |
|---|---|
| **App ID** (starts with `cli_`) | `FEISHU_APP_ID` |
| **App Secret** (click *Show*) | `FEISHU_APP_SECRET` |

---

## 3 · Add the Bot capability

App → **Add Features** → find **Bot** → click **+ Add**.

Without this the app cannot be added to a group and cannot send messages.

---

## 4 · Configure scopes

App → **Permissions & Scopes**. Search for and add all five:

| Scope | Why |
|---|---|
| `im:message.group_msg` | Read group messages — required for the input channel |
| `im:resource` | Download images attached to messages |
| `im:message:send_as_bot` | Send messages as the app |
| `im:chat:readonly` | List the groups the app belongs to (needed to look up the group id) |
| `bitable:app` | Write rows to the archive table |

> If a name does not match exactly, search for the keywords **message**, **resource**,
> **chat** and **bitable**.

---

## 5 · Publish a version

App → **Version Management & Release** → **Create Version** → enter a version number
(such as `1.0.0`) → **Submit for release**.

- If you are the admin, approve it yourself in the admin console.
- **Scopes and the bot capability do not take effect until a version is published.** Calls
  will fail with permission errors otherwise.
- If you add scopes later, publish a new version.

---

## 6 · Create a group and add the app bot

1. Create a group in Feishu (it can contain only you).
2. Group settings → **Bots** → **Add Bot** → pick **your app** from the list.

Notes:

- Pick the **app** — not "Custom Bot". These are separate entries in the list.
- The Feishu mobile client does offer this entry point, so you can do this step on a phone.
- This single group serves as both the input channel (you send screenshots here) and the
  notification channel (the weekly plan arrives here).

---

## 7 · Create the archive table

1. Create a Bitable named something like `Holdings Archive`.
2. Add these fields — **the names must match exactly**:

| Field | Type | Notes |
|---|---|---|
| `图片` | Attachment | Written by the app; leave empty in manual use |
| `基金代码` | Text | Fund code |
| `状态` | Text | Written by the app, e.g. `已识别` |
| `识别结果` | Text | Written by the app |

> The field names are Chinese because the app writes to them by name. Keep them as-is.

3. **Add the app to the table as a document app.** This is the step people most often miss.

   Open the table in a **desktop browser** (this entry point does not exist on mobile):
   top-right **`...`** → **`...More`** → **Add Document App** → search for your app →
   grant **Can edit**. If the table has advanced permissions enabled, grant **Can manage**.

   Two hard requirements — the app will not appear in the search dialog unless both hold:

   | Requirement | If unmet |
   |---|---|
   | The app has at least one cloud-document scope (`bitable:app`) | App not searchable |
   | A published version exists whose **availability scope includes the table owner** (you) | App not searchable |

   *Alternative that works on mobile:* add the **group containing the app bot** as a
   collaborator via the table's **Share** dialog.

---

## 8 · Get the Bitable tokens

Open the table in a browser and read the address bar:

```
https://<tenant>.feishu.cn/base/<app_token>?table=<table_id>&view=<view_id>
```

| Part | Where it goes |
|---|---|
| The segment after `/base/` | `FEISHU_BITABLE_APP_TOKEN` |
| The segment after `table=` (starts with `tbl`) | `FEISHU_BITABLE_TABLE_ID` |

The `/base/` segment is either a random string or, on older tables, starts with `bascn`.

> If the URL looks like `/wiki/<token>?table=tbl...`, that token is a **wiki node token, not
> the app token**. Open the table as a standalone Bitable first, or resolve the wiki node to
> its real app token through the API.
>
> On mobile, use **`...` → Copy Link** and paste it somewhere to read the values. If the link
> comes back shortened, use a desktop browser instead.

---

## 9 · Get the group id

Call the Feishu API — no extra tooling required.

**a. Exchange the app credentials for a tenant access token**

```bash
curl -s -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d '{"app_id":"cli_xxxx","app_secret":"xxxx"}'
```

Copy `tenant_access_token` from the response.

**b. List the groups the app bot belongs to**

```bash
curl -s "https://open.feishu.cn/open-apis/im/v1/chats?page_size=50" \
  -H "Authorization: Bearer <tenant_access_token>"
```

Every entry in `data.items` carries a `chat_id` (starts with `oc`). The one matching your
group is **`FEISHU_CHAT_ID`**.

If the list is empty, check: the bot capability is enabled, a version is published, the app
bot was actually added to the group, and `im:chat:readonly` is granted.

---

## 10 · Where the values go

Add all five to **Supabase → Edge Functions → Secrets**:

| Secret | Source |
|---|---|
| `FEISHU_APP_ID` | Step 2 |
| `FEISHU_APP_SECRET` | Step 2 |
| `FEISHU_BITABLE_APP_TOKEN` | Step 8 |
| `FEISHU_BITABLE_TABLE_ID` | Step 8 |
| `FEISHU_CHAT_ID` | Step 9 |

The LLM and OCR keys are covered in the [backend README](README.md), section 3.

---

## 11 · Troubleshooting

| Symptom | Cause |
|---|---|
| My app does not appear in the Share dialog | Wrong entry point. Use `...` → `...More` → **Add Document App**. It does not exist on mobile — use a desktop browser |
| Still cannot find the app in **Add Document App** | One of: no cloud-document scope granted / no published version / the published version's availability scope does not include the table owner |
| `need scope: im:message.group_msg` | The read-group-messages scope is missing. Add it and publish a new version if required |
| There is no "Custom Bot" entry in group settings | Not needed for this project. Add **the app** as the bot instead |
| Sending fails with `no permission` | `im:message:send_as_bot` is missing, the version was not published, or the app was removed from the group |
| Step 9 returns no groups | Bot capability off, no published version, app not in the group, or `im:chat:readonly` missing |
| Reading records returns `code 230027` | Insufficient scope — add the scope named in the error message |
