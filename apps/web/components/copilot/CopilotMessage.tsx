"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { ChevronRight, Eye, Hand, Loader2, PencilLine } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  FIELD_LABELS,
  TOOL_LABELS,
  openCalculationLog,
  type AssistantPart,
  type PatchPart,
  type ToolPart,
  type Turn,
} from "@/lib/copilot";

/* ------------------------------------------------------------ inline text */

const TOKEN = /(\[calc:[0-9a-f]+\]|\[campaign:[0-9a-f]+\]|`[^`]+`|\*\*[^*]+\*\*)/g;

function CalcChip({ id }: { id: string }) {
  const [state, setState] = useState<"idle" | "opening" | "missing">("idle");
  return (
    <button
      type="button"
      title={state === "missing" ? "no engine log for this calculation" : `open log ${id}`}
      onClick={async () => {
        setState("opening");
        const ok = await openCalculationLog(id);
        setState(ok ? "idle" : "missing");
      }}
      className={cn(
        "mx-0.5 inline-flex items-center rounded-xs border px-1 font-mono text-[11px] align-baseline transition-colors",
        state === "missing"
          ? "border-line text-text-muted"
          : "border-accent/30 bg-accent/10 text-accent-bright hover:border-accent/60",
      )}
    >
      calc {id.slice(0, 8)}
    </button>
  );
}

function inline(text: string): ReactNode[] {
  return text.split(TOKEN).map((chunk, i) => {
    if (!chunk) return null;
    const calc = chunk.match(/^\[calc:([0-9a-f]+)\]$/);
    if (calc) return <CalcChip key={i} id={calc[1]} />;
    const camp = chunk.match(/^\[campaign:([0-9a-f]+)\]$/);
    if (camp)
      return (
        <Link
          key={i}
          href={`/campaigns/${camp[1]}`}
          className="mx-0.5 inline-flex items-center rounded-xs border border-verdigris/30 bg-verdigris/10 px-1 font-mono text-[11px] text-verdigris hover:border-verdigris/60"
        >
          campaign {camp[1].slice(0, 8)}
        </Link>
      );
    if (chunk.startsWith("`"))
      return (
        <code key={i} className="rounded-xs bg-white/[0.06] px-1 font-mono text-[12px]">
          {chunk.slice(1, -1)}
        </code>
      );
    if (chunk.startsWith("**"))
      return (
        <strong key={i} className="font-medium text-text">
          {chunk.slice(2, -2)}
        </strong>
      );
    return chunk;
  });
}

/** Minimal markdown: paragraphs, `-`/`*`/numbered lists, inline code/bold, citations. */
export function RichText({ text, className }: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.split("\n");
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) {
      blocks.push(
        <p key={blocks.length} className="leading-relaxed">
          {inline(para.join(" "))}
        </p>,
      );
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      const Tag = list.ordered ? "ol" : "ul";
      blocks.push(
        <Tag
          key={blocks.length}
          className={cn("space-y-1 pl-4", list.ordered ? "list-decimal" : "list-disc")}
        >
          {list.items.map((item, i) => (
            <li key={i} className="leading-relaxed marker:text-text-muted">
              {inline(item)}
            </li>
          ))}
        </Tag>,
      );
      list = null;
    }
  };
  for (const raw of lines) {
    const line = raw.replace(/^#{1,6}\s+/, "");
    const m = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/);
    if (m) {
      flushPara();
      const ordered = m[1] != null;
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(m[2]);
    } else if (line.trim() === "") {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line.trim());
    }
  }
  flushPara();
  flushList();
  return <div className={cn("space-y-2 text-[13px] text-text-secondary", className)}>{blocks}</div>;
}

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
  if (part.type === "text") return <RichText text={part.text} />;
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
