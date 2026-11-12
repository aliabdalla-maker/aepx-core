CREATE TABLE "agents" (
	"id" serial PRIMARY KEY,
	"name" text NOT NULL UNIQUE,
	"role" text NOT NULL,
	"portal_slug" text,
	"status" text DEFAULT 'idle' NOT NULL,
	"trust_score" integer DEFAULT 60 NOT NULL,
	"last_heartbeat_at" timestamp DEFAULT now()
);
--> statement-breakpoint
CREATE TABLE "connections" (
	"id" serial PRIMARY KEY,
	"portal_slug" text NOT NULL,
	"target" text NOT NULL,
	"target_kind" text DEFAULT 'service' NOT NULL,
	"protocol" text DEFAULT 'REST' NOT NULL,
	"status" text DEFAULT 'planned' NOT NULL,
	"notes" text DEFAULT '' NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "events" (
	"id" serial PRIMARY KEY,
	"portal_slug" text,
	"kind" text NOT NULL,
	"message" text NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "portals" (
	"slug" text PRIMARY KEY,
	"name" text NOT NULL,
	"code" text NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"color" text DEFAULT '#7dd3fc' NOT NULL,
	"base_url" text DEFAULT '' NOT NULL,
	"status" text DEFAULT 'unknown' NOT NULL,
	"latency_ms" integer,
	"last_checked_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tasks" (
	"id" serial PRIMARY KEY,
	"portal_slug" text NOT NULL,
	"title" text NOT NULL,
	"kind" text DEFAULT 'integration' NOT NULL,
	"status" text DEFAULT 'backlog' NOT NULL,
	"priority" text DEFAULT 'P2' NOT NULL,
	"agent" text DEFAULT '' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE INDEX "connections_portal_idx" ON "connections" ("portal_slug");--> statement-breakpoint
CREATE INDEX "events_created_idx" ON "events" ("created_at");--> statement-breakpoint
CREATE INDEX "tasks_portal_idx" ON "tasks" ("portal_slug");--> statement-breakpoint
ALTER TABLE "agents" ADD CONSTRAINT "agents_portal_slug_portals_slug_fkey" FOREIGN KEY ("portal_slug") REFERENCES "portals"("slug") ON DELETE SET NULL;--> statement-breakpoint
ALTER TABLE "connections" ADD CONSTRAINT "connections_portal_slug_portals_slug_fkey" FOREIGN KEY ("portal_slug") REFERENCES "portals"("slug") ON DELETE CASCADE;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_portal_slug_portals_slug_fkey" FOREIGN KEY ("portal_slug") REFERENCES "portals"("slug") ON DELETE CASCADE;