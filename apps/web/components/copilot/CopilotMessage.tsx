"use client";

import { useState } from "react";
import { ChevronRight, Eye, Hand, Loader2, PencilLine } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  FIELD_LABELS,
  TOOL_LABELS,
  type AssistantPart,
  type PatchPart,
  type ToolPart,
  type Turn,
} from "@/lib/copilot";
import { RichText } from "@/components/ui/RichText";

/* ------------------------------------------------------------- tool cards */

function summarizeArgs(args: Record<string, unknown>): string {
  const bits: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    if (k === "patch" || k === "rationale") continue;
    if (typeof v === "string" && /^[0-9a-f]{32}$/.test(v))
      bits.push(`${k.replace(/_id$/, "")} ${v.slice(0, 8)}`);
    else if (v != null) bits.push(`${k}=${String(v)}`);
  }
  return bits.join(" · ");
}

function ToolCard({ part }: { part: ToolPart }) {
  const [open, setOpen] = useState(false);
  const meta = TOOL_LABELS[part.name] ?? { label: part.name, kind: "eyes" as const };
  const Icon = meta.kind === "hands" ? Hand : Eye;
  const pending = part.ok == null;
  return (
    <div className="rounded-sm border border-line bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left font-mono text-[11px] text-text-secondary hover:text-text"
      >
        {pending ? (
          <Loader2 className="h-3 w-3 animate-spin text-accent" />
        ) : (
          <Icon className={cn("h-3 w-3", part.ok ? "text-accent" : "text-oxide")} />
        )}
        <span className={cn(part.ok === false && "text-oxide")}>{meta.label}</span>
        <span className="truncate text-text-muted">{summarizeArgs(part.args)}</span>
        <ChevronRight
          className={cn("ml-auto h-3 w-3 shrink-0 transition-transform", open && "rotate-90")}
        />
      </button>
      {open && (
        <pre className="scroll-thin max-h-56 overflow-auto border-t border-line px-2.5 py-2 font-mono text-[10.5px] leading-snug text-text-muted">
          {JSON.stringify({ args: part.args, result: part.result ?? "(pending)" }, null, 1)}
        </pre>
      )}
    </div>
  );
}

function PatchCard({ part }: { part: PatchPart }) {
  return (
    <div className="rounded-sm border border-brass/30 bg-brass/[0.06]">
      <div className="flex items-center gap-2 px-2.5 py-1.5 font-mono text-[11px] text-brass">
        <PencilLine className="h-3 w-3" />
        proposed form changes
        <span className="ml-auto text-[10px] uppercase tracking-[0.14em] text-brass-dim">
          applied · review &amp; create
        </span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 border-t border-brass/20 px-2.5 py-2 font-mono text-[11.5px]">
        {Object.entries(part.patch).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-text-muted">{FIELD_LABELS[k] ?? k}</dt>
            <dd className="text-text">{String(v)}</dd>
          </div>
        ))}
      </dl>
      {part.rationale && (
        <p className="border-t border-brass/20 px-2.5 py-1.5 text-[12px] leading-relaxed text-text-secondary">
          {part.rationale}
        </p>
      )}
    </div>
  );
}

function Part({ part }: { part: AssistantPart }) {
  if (part.type === "text")
    return <RichText text={part.text} className="text-[13px] text-text-secondary" />;
  if (part.type === "patch") return <PatchCard part={part} />;
  return <ToolCard part={part} />;
}

/* ------------------------------------------------------------------ turns */

export function CopilotTurn({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] whitespace-pre-wrap rounded-md rounded-br-xs border border-line bg-white/[0.04] px-3 py-2 text-[13px] leading-relaxed text-text">
          {turn.text}
        </div>
      </div>
    );
  }
  const parts = turn.parts;
  // Group consecutive tool parts so a burst of reads renders as one compact stack.
  const groups: AssistantPart[][] = [];
  for (const p of parts) {
    const last = groups[groups.length - 1];
    if (last && last[0].type === "tool" && p.type === "tool") last.push(p);
    else groups.push([p]);
  }
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g, i) => (
        <div key={i} className={cn(g[0].type === "tool" && "flex flex-col gap-1")}>
          {g.map((p, j) => (
            <Part key={j} part={p} />
          ))}
        </div>
      ))}
      {turn.streaming && parts.length === 0 && (
        <div className="flex items-center gap-2 font-mono text-[11px] text-text-muted">
          <Loader2 className="h-3 w-3 animate-spin" /> thinking
        </div>
      )}
    </div>
  );
}
