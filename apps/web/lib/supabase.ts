import { createClient } from "@supabase/supabase-js";

/**
 * Browser/edge Supabase client (anon key). Server code that needs full SQL
 * should use the Drizzle client in `@/db` instead.
 */
export function getSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error("NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set");
  }
  return createClient(url, key);
}
