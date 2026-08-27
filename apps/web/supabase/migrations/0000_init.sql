CREATE TABLE "agent_events" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"agent_run_id" varchar(32),
	"campaign_id" varchar(32) NOT NULL,
	"event_type" varchar(50) NOT NULL,
	"hypothesis" text,
	"reasoning_summary" text,
	"action" text,
	"tool_name" varchar(100),
	"tool_input" jsonb,
	"tool_output_reference" varchar(200),
	"payload" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agent_runs" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"campaign_id" varchar(32) NOT NULL,
	"model" varchar(100) DEFAULT 'heuristic' NOT NULL,
	"status" varchar(20) DEFAULT 'RUNNING' NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone,
	"token_usage" jsonb
);
--> statement-breakpoint
CREATE TABLE "benchmark_runs" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"status" varchar(20) DEFAULT 'RUNNING' NOT NULL,
	"config" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"results" jsonb,
	"summary" jsonb,
	"error" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "calculations" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"campaign_id" varchar(32) NOT NULL,
	"structure_id" varchar(32),
	"calculation_type" varchar(40) DEFAULT 'MONTE_CARLO' NOT NULL,
	"engine" varchar(100) DEFAULT 'alloyscience.ising.IsingSimulator' NOT NULL,
	"status" varchar(20) DEFAULT 'QUEUED' NOT NULL,
	"input_parameters" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"output" jsonb,
	"provenance" jsonb,
	"failure_category" varchar(60),
	"failure_metadata" jsonb,
	"retry_of" varchar(32),
	"changed_parameters" jsonb,
	"reason_for_change" text,
	"resolution" varchar(20),
	"stdout_artifact" varchar(500),
	"stderr_artifact" varchar(500),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"started_at" timestamp with time zone,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "campaigns" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"name" varchar(200) NOT NULL,
	"objective" text NOT NULL,
	"problem_type" varchar(50) DEFAULT 'ising_v0' NOT NULL,
	"strategy" varchar(50) DEFAULT 'agent' NOT NULL,
	"temperature_min" double precision DEFAULT 1.5 NOT NULL,
	"temperature_max" double precision DEFAULT 3.5 NOT NULL,
	"composition_min" double precision,
	"composition_max" double precision,
	"elements" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"lattice_size" integer DEFAULT 24 NOT NULL,
	"simulation_budget" integer DEFAULT 20 NOT NULL,
	"simulations_used" integer DEFAULT 0 NOT NULL,
	"target_uncertainty" double precision,
	"failure_rate" double precision DEFAULT 0 NOT NULL,
	"status" varchar(30) DEFAULT 'CREATED' NOT NULL,
	"stopping_rationale" text,
	"problem_config" jsonb,
	"report" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "structures" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"campaign_id" varchar(32) NOT NULL,
	"label" varchar(50) NOT NULL,
	"chemical_formula" varchar(100) DEFAULT '' NOT NULL,
	"composition" double precision NOT NULL,
	"n_sites" integer NOT NULL,
	"occupations" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"shape" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"features" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"lattice" jsonb,
	"positions" jsonb,
	"atomic_numbers" jsonb,
	"extra" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "surrogate_models" (
	"id" varchar(32) PRIMARY KEY NOT NULL,
	"campaign_id" varchar(32) NOT NULL,
	"type" varchar(50) DEFAULT 'response_surrogate' NOT NULL,
	"version" integer DEFAULT 1 NOT NULL,
	"training_calculation_ids" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"parameters" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"validation_metrics" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"artifact" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "agent_events" ADD CONSTRAINT "agent_events_agent_run_id_agent_runs_id_fk" FOREIGN KEY ("agent_run_id") REFERENCES "public"."agent_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_events" ADD CONSTRAINT "agent_events_campaign_id_campaigns_id_fk" FOREIGN KEY ("campaign_id") REFERENCES "public"."campaigns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_campaign_id_campaigns_id_fk" FOREIGN KEY ("campaign_id") REFERENCES "public"."campaigns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "calculations" ADD CONSTRAINT "calculations_campaign_id_campaigns_id_fk" FOREIGN KEY ("campaign_id") REFERENCES "public"."campaigns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "calculations" ADD CONSTRAINT "calculations_structure_id_structures_id_fk" FOREIGN KEY ("structure_id") REFERENCES "public"."structures"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "calculations" ADD CONSTRAINT "calculations_retry_of_calculations_id_fk" FOREIGN KEY ("retry_of") REFERENCES "public"."calculations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "structures" ADD CONSTRAINT "structures_campaign_id_campaigns_id_fk" FOREIGN KEY ("campaign_id") REFERENCES "public"."campaigns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "surrogate_models" ADD CONSTRAINT "surrogate_models_campaign_id_campaigns_id_fk" FOREIGN KEY ("campaign_id") REFERENCES "public"."campaigns"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "ix_agent_events_campaign_id" ON "agent_events" USING btree ("campaign_id");--> statement-breakpoint
CREATE INDEX "ix_agent_events_event_type" ON "agent_events" USING btree ("event_type");--> statement-breakpoint
CREATE INDEX "ix_agent_runs_campaign_id" ON "agent_runs" USING btree ("campaign_id");--> statement-breakpoint
CREATE INDEX "ix_calculations_campaign_id" ON "calculations" USING btree ("campaign_id");--> statement-breakpoint
CREATE INDEX "ix_calculations_structure_id" ON "calculations" USING btree ("structure_id");--> statement-breakpoint
CREATE INDEX "ix_calculations_status" ON "calculations" USING btree ("status");--> statement-breakpoint
CREATE INDEX "ix_structures_campaign_id" ON "structures" USING btree ("campaign_id");--> statement-breakpoint
CREATE INDEX "ix_structures_label" ON "structures" USING btree ("label");--> statement-breakpoint
CREATE INDEX "ix_surrogate_models_campaign_id" ON "surrogate_models" USING btree ("campaign_id");