ALTER TABLE "science"."campaigns" ADD COLUMN "user_id" text;--> statement-breakpoint
ALTER TABLE "science"."campaigns" ADD CONSTRAINT "campaigns_user_id_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "app_auth"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "campaigns_user_id_created_at_idx" ON "science"."campaigns" USING btree ("user_id","created_at");