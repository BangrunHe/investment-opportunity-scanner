// Supabase 客户端（Edge Function 内自动注入 URL / service_role key）

import { createClient } from "jsr:@supabase/supabase-js@2";

export function supabase() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}
