"use client";

/** Minimal markdown renderer shared by the copilot transcript and the final
 * report: headings, paragraphs, `-`/`*`/numbered lists, inline code/bold, and
 * `[calc:…]` / `[campaign:…]` citation chips. Deliberately not a markdown
 * library — the only authors are our own prompts, so the grammar is small and
 * anything unrecognised degrades to plain text rather than to markup. */

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { openCalculationLog } from "@/lib/copilot";

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

export function inline(text: string): ReactNode[] {
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
    // Headings first: the report narrative is written with `## Results` /
    // `## Recommendation`, which used to be stripped to bare paragraphs.
    const heading = raw.match(/^\s*(#{1,6})\s+(.*\S)\s*$/);
    if (heading) {
      flushPara();
      flushList();
      blocks.push(
        <h3
          key={blocks.length}
          className={cn(
            "pt-2 font-medium text-text first:pt-0",
            heading[1].length <= 2 ? "text-[1.08em]" : "text-[1em]",
          )}
        >
          {inline(heading[2])}
        </h3>,
      );
      continue;
    }
    const line = raw.trim();
    const m = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/);
    if (m) {
      flushPara();
      const ordered = m[1] != null;
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push(m[2]);
    } else if (line === "") {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return <div className={cn("space-y-2", className)}>{blocks}</div>;
}
