import { boolean, index, text, timestamp, uniqueIndex } from "drizzle-orm/pg-core";
import { appAuth } from "./schemas";

/**
 * Better Auth core tables (email + password). Field names follow the Better
 * Auth schema so the Drizzle adapter needs no field mapping. The Python API
 * reads `session`/`user` to authenticate requests (gibbs/api/auth.py).
 */
const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const user = appAuth
  .table("user", {
    id: text("id").primaryKey(),
    name: text("name").notNull(),
    email: text("email").notNull().unique(),
    emailVerified: boolean("email_verified").notNull().default(false),
    image: text("image"),
    createdAt: ts("created_at").defaultNow().notNull(),
    updatedAt: ts("updated_at")
      .defaultNow()
      .$onUpdate(() => new Date())
      .notNull(),
  })
  .enableRLS();

export const session = appAuth
  .table(
    "session",
    {
      id: text("id").primaryKey(),
      expiresAt: ts("expires_at").notNull(),
      token: text("token").notNull().unique(),
      createdAt: ts("created_at").defaultNow().notNull(),
      updatedAt: ts("updated_at")
        .defaultNow()
        .$onUpdate(() => new Date())
        .notNull(),
      ipAddress: text("ip_address"),
      userAgent: text("user_agent"),
      userId: text("user_id")
        .notNull()
        .references(() => user.id, { onDelete: "cascade" }),
    },
    (t) => [index("ix_session_user_id").on(t.userId)],
  )
  .enableRLS();

export const account = appAuth
  .table(
    "account",
    {
      id: text("id").primaryKey(),
      /** Better Auth ≥1.7: identity issuer (e.g. "credential" for email+password). */
      issuer: text("issuer").notNull(),
      accountId: text("account_id").notNull(),
      providerId: text("provider_id").notNull(),
      userId: text("user_id")
        .notNull()
        .references(() => user.id, { onDelete: "cascade" }),
      accessToken: text("access_token"),
      refreshToken: text("refresh_token"),
      idToken: text("id_token"),
      accessTokenExpiresAt: ts("access_token_expires_at"),
      refreshTokenExpiresAt: ts("refresh_token_expires_at"),
      scope: text("scope"),
      password: text("password"),
      createdAt: ts("created_at").defaultNow().notNull(),
      updatedAt: ts("updated_at")
        .defaultNow()
        .$onUpdate(() => new Date())
        .notNull(),
    },
    (t) => [
      index("ix_account_user_id").on(t.userId),
      uniqueIndex("ux_account_issuer_account_id").on(t.issuer, t.accountId),
    ],
  )
  .enableRLS();

export const verification = appAuth
  .table(
    "verification",
    {
      id: text("id").primaryKey(),
      identifier: text("identifier").notNull(),
      value: text("value").notNull(),
      expiresAt: ts("expires_at").notNull(),
      createdAt: ts("created_at").defaultNow().notNull(),
      updatedAt: ts("updated_at")
        .defaultNow()
        .$onUpdate(() => new Date())
        .notNull(),
    },
    (t) => [index("ix_verification_identifier").on(t.identifier)],
  )
  .enableRLS();

export type User = typeof user.$inferSelect;
export type Session = typeof session.$inferSelect;
