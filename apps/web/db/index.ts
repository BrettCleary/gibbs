import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

/**
 * Server-side Drizzle client over the Supabase Postgres connection.
 *
 * DATABASE_URL should be the Supabase *session-mode* pooler URI (port 5432)
 * or the direct connection; for the *transaction* pooler (port 6543) prepared
 * statements must stay disabled, which `prepare: false` handles.
 */
function connectionString(): string {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set (Supabase Postgres connection string)");
  return url;
}

let _client: ReturnType<typeof postgres> | undefined;

export function getDb() {
  if (!_client) _client = postgres(connectionString(), { prepare: false, max: 4 });
  return drizzle(_client, { schema });
}

export type Db = ReturnType<typeof getDb>;
export { schema };
