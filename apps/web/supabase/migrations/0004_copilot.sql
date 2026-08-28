CREATE TABLE "agent"."agent_config" (
	"id" serial PRIMARY KEY NOT NULL,
	"max_output_tokens" integer DEFAULT 4096 NOT NULL,
	"temperature" integer,
	"top_p" integer,
	"provider_options" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"base_url" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent"."agent_config" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."agent_skill_set" (
	"agent_id" integer NOT NULL,
	"skill_set_id" integer NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "agent_skill_set_agent_id_skill_set_id_pk" PRIMARY KEY("agent_id","skill_set_id")
);
--> statement-breakpoint
ALTER TABLE "agent"."agent_skill_set" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."agent_tool_set" (
	"agent_id" integer NOT NULL,
	"tool_set_id" integer NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "agent_tool_set_agent_id_tool_set_id_pk" PRIMARY KEY("agent_id","tool_set_id")
);
--> statement-breakpoint
ALTER TABLE "agent"."agent_tool_set" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."agent" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"system_prompt" text NOT NULL,
	"foundation_model" text,
	"enable_all_tools" boolean DEFAULT false NOT NULL,
	"agent_config_id" integer NOT NULL,
	"tag" text,
	"description" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "agent_name_unique" UNIQUE("name")
);
--> statement-breakpoint
ALTER TABLE "agent"."agent" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."message_skill" (
	"message_id" integer NOT NULL,
	"skill_set_id" integer NOT NULL,
	"skill_name" text NOT NULL,
	CONSTRAINT "message_skill_message_id_skill_set_id_skill_name_pk" PRIMARY KEY("message_id","skill_set_id","skill_name")
);
--> statement-breakpoint
ALTER TABLE "agent"."message_skill" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."skill_set" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"description" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "skill_set_name_unique" UNIQUE("name")
);
--> statement-breakpoint
ALTER TABLE "agent"."skill_set" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."skill_set_skill" (
	"skill_set_id" integer NOT NULL,
	"skill_name" text NOT NULL,
	"description" text,
	"content" text NOT NULL,
	CONSTRAINT "skill_set_skill_skill_set_id_skill_name_pk" PRIMARY KEY("skill_set_id","skill_name")
);
--> statement-breakpoint
ALTER TABLE "agent"."skill_set_skill" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."tool_set" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"description" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "tool_set_name_unique" UNIQUE("name")
);
--> statement-breakpoint
ALTER TABLE "agent"."tool_set" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."tool_set_tool" (
	"tool_set_id" integer NOT NULL,
	"tool_name" text NOT NULL,
	CONSTRAINT "tool_set_tool_tool_set_id_tool_name_pk" PRIMARY KEY("tool_set_id","tool_name")
);
--> statement-breakpoint
ALTER TABLE "agent"."tool_set_tool" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."chat" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"user_id" text NOT NULL,
	"title" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent"."chat" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."messages" (
	"id" serial PRIMARY KEY NOT NULL,
	"chat_id" uuid NOT NULL,
	"role" text NOT NULL,
	"message" text NOT NULL,
	"total_tokens" integer DEFAULT 0 NOT NULL,
	"component_type" text,
	"component_data" jsonb,
	"trace_id" text,
	"page_context" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent"."messages" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "agent"."tool_call" (
	"id" serial PRIMARY KEY NOT NULL,
	"message_id" integer NOT NULL,
	"call_id" text NOT NULL,
	"name" text NOT NULL,
	"arguments" text NOT NULL,
	"output" text,
	"status" text DEFAULT 'pending' NOT NULL,
	"position" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent"."tool_call" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "agent"."agent_skill_set" ADD CONSTRAINT "agent_skill_set_agent_id_agent_id_fk" FOREIGN KEY ("agent_id") REFERENCES "agent"."agent"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."agent_skill_set" ADD CONSTRAINT "agent_skill_set_skill_set_id_skill_set_id_fk" FOREIGN KEY ("skill_set_id") REFERENCES "agent"."skill_set"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."agent_tool_set" ADD CONSTRAINT "agent_tool_set_agent_id_agent_id_fk" FOREIGN KEY ("agent_id") REFERENCES "agent"."agent"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."agent_tool_set" ADD CONSTRAINT "agent_tool_set_tool_set_id_tool_set_id_fk" FOREIGN KEY ("tool_set_id") REFERENCES "agent"."tool_set"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."agent" ADD CONSTRAINT "agent_agent_config_id_agent_config_id_fk" FOREIGN KEY ("agent_config_id") REFERENCES "agent"."agent_config"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."message_skill" ADD CONSTRAINT "message_skill_message_id_messages_id_fk" FOREIGN KEY ("message_id") REFERENCES "agent"."messages"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."message_skill" ADD CONSTRAINT "message_skill_skill_set_id_skill_name_skill_set_skill_skill_set_id_skill_name_fk" FOREIGN KEY ("skill_set_id","skill_name") REFERENCES "agent"."skill_set_skill"("skill_set_id","skill_name") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."skill_set_skill" ADD CONSTRAINT "skill_set_skill_skill_set_id_skill_set_id_fk" FOREIGN KEY ("skill_set_id") REFERENCES "agent"."skill_set"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."tool_set_tool" ADD CONSTRAINT "tool_set_tool_tool_set_id_tool_set_id_fk" FOREIGN KEY ("tool_set_id") REFERENCES "agent"."tool_set"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."chat" ADD CONSTRAINT "chat_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "app_auth"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."messages" ADD CONSTRAINT "messages_chat_id_chat_id_fk" FOREIGN KEY ("chat_id") REFERENCES "agent"."chat"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent"."tool_call" ADD CONSTRAINT "tool_call_message_id_messages_id_fk" FOREIGN KEY ("message_id") REFERENCES "agent"."messages"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "message_skill_message_id_idx" ON "agent"."message_skill" USING btree ("message_id");--> statement-breakpoint
CREATE UNIQUE INDEX "message_skill_unique_idx" ON "agent"."message_skill" USING btree ("message_id","skill_set_id","skill_name");--> statement-breakpoint
CREATE INDEX "skill_set_skill_skill_name_idx" ON "agent"."skill_set_skill" USING btree ("skill_name");--> statement-breakpoint
CREATE INDEX "tool_set_tool_tool_name_idx" ON "agent"."tool_set_tool" USING btree ("tool_name");--> statement-breakpoint
CREATE INDEX "chat_user_id_updated_at_idx" ON "agent"."chat" USING btree ("user_id","updated_at");--> statement-breakpoint
CREATE INDEX "messages_chat_id_created_at_id_idx" ON "agent"."messages" USING btree ("chat_id","created_at","id");--> statement-breakpoint
CREATE INDEX "tool_call_message_id_idx" ON "agent"."tool_call" USING btree ("message_id");
