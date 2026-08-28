import { index, integer, jsonb, serial, text, timestamp, uuid } from "drizzle-orm/pg-core";
import { agent } from "./schemas";
import { user } from "./auth";

/**
 * Copilot chat model: a chat owns an ordered timeline of messages, and each
 * assistant message owns the tool calls the model made while producing it.
 * The Pydantic AI message history is rebuilt from these rows for each turn;
 * nothing is stored as an opaque history blob.
 */

const ts = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });

export const chat = agent
  .table(
    "chat",
    {
      id: uuid("id").defaultRandom().primaryKey(),
      userId: text("user_id")
        .notNull()
        .references(() => user.id, { onDelete: "cascade" }),
      title: text("title").notNull(),
      createdAt: ts("created_at").notNull().defaultNow(),
      updatedAt: ts("updated_at").notNull().defaultNow(),
    },
    (t) => [index("chat_user_id_updated_at_idx").on(t.userId, t.updatedAt)],
  )
  .enableRLS();

export const messages = agent
  .table(
    "messages",
    {
      id: serial("id").primaryKey(),
      chatId: uuid("chat_id")
        .notNull()
        .references(() => chat.id, { onDelete: "cascade" }),
      /** "user" | "assistant" */
      role: text("role").notNull(),
      message: text("message").notNull(),
      totalTokens: integer("total_tokens").notNull().default(0),
      /** Display-only structured payload, e.g. "form_patch" with {patch, rationale}. */
      componentType: text("component_type"),
      componentData: jsonb("component_data").$type<Record<string, unknown>>(),
      /** OpenTelemetry / Arize trace id of the agent run that produced this message. */
      traceId: text("trace_id"),
      /** What the scientist was looking at when they sent this (user rows only). */
      pageContext: jsonb("page_context").$type<Record<string, unknown>>(),
      createdAt: ts("created_at").notNull().defaultNow(),
      updatedAt: ts("updated_at").notNull().defaultNow(),
    },
    (t) => [
      // Every chat read is "this chat's messages in timeline order".
      index("messages_chat_id_created_at_id_idx").on(t.chatId, t.createdAt, t.id),
    ],
  )
  .enableRLS();

export const toolCall = agent
  .table(
    "tool_call",
    {
      id: serial("id").primaryKey(),
      messageId: integer("message_id")
        .notNull()
        .references(() => messages.id, { onDelete: "cascade" }),
      /** The model's tool_call_id, needed to rebuild the history the model saw. */
      callId: text("call_id").notNull(),
      name: text("name").notNull(),
      /** Tool arguments as JSON text. */
      arguments: text("arguments").notNull(),
      /** Tool return value as JSON text (or the retry/error message). */
      output: text("output"),
      /** "ok" | "error" | "pending" */
      status: text("status").notNull().default("pending"),
      /** Position within the assistant turn. */
      position: integer("position").notNull().default(0),
      createdAt: ts("created_at").notNull().defaultNow(),
      updatedAt: ts("updated_at").notNull().defaultNow(),
    },
    (t) => [index("tool_call_message_id_idx").on(t.messageId)],
  )
  .enableRLS();

export type Chat = typeof chat.$inferSelect;
export type NewChat = typeof chat.$inferInsert;
export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
export type ToolCall = typeof toolCall.$inferSelect;
export type NewToolCall = typeof toolCall.$inferInsert;
