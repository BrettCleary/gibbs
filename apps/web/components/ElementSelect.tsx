"use client";

/**
 * Searchable element picker backed by GET /campaigns/elements. Filters by
 * symbol or name, greys out elements the selected engine cannot handle, and
 * flags non-FCC elements (modelled on a hypothetical FCC lattice).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ElementRead } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Input } from "@/components/ui/primitives";

export function useElementCatalog() {
  return useQuery({
    queryKey: ["elements"],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns/elements");
      return data ?? [];
    },
    staleTime: 5 * 60_000,
  });
}

export function ElementSelect({
  value,
  onChange,
  engine,
  exclude,
  placeholder,
}: {
  value: string;
  onChange: (symbol: string) => void;
  /** "hidden" | "emt" | "espresso" — which engine's support to enforce. */
  engine: string;
  /** symbol to grey out (the other element of the pair) */
  exclude?: string;
  placeholder?: string;
}) {
  const catalog = useElementCatalog();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (catalog.data ?? []).filter(
      (e) => !q || e.symbol.toLowerCase().startsWith(q) || e.name.toLowerCase().includes(q),
    );
  }, [catalog.data, query]);

  const supported = (e: ElementRead) => (e.engines as Record<string, boolean>)[engine] !== false && e.symbol !== exclude;
  const selected = catalog.data?.find((e) => e.symbol === value);

  useEffect(() => {
    const onDoc = (ev: MouseEvent) => {
      if (root.current && !root.current.contains(ev.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const choose = (e: ElementRead) => {
    if (!supported(e)) return;
    onChange(e.symbol);
    setQuery("");
    setOpen(false);
  };

  return (
    <div ref={root} className="relative">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        value={open ? query : value}
        placeholder={placeholder ?? "element"}
        onFocus={() => {
          setOpen(true);
          setQuery("");
          setCursor(0);
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setCursor(0);
        }}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, items.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
          if (e.key === "Enter") { e.preventDefault(); if (items[cursor]) choose(items[cursor]); }
          if (e.key === "Escape") setOpen(false);
        }}
        className={cn("font-mono", !selected && value && "text-oxide")}
      />
      {selected && !open && (
        <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          {selected.name}
          {!selected.fcc_native && <span className="text-brass">· {selected.structure}</span>}
        </span>
      )}
      {open && (
        <ul
          role="listbox"
          className="scroll-thin absolute z-20 mt-1 max-h-64 w-72 overflow-y-auto rounded-sm border border-line bg-surface shadow-lg"
        >
          {catalog.isLoading && <li className="px-3 py-2 text-[12px] text-text-muted">Loading elements…</li>}
          {items.length === 0 && !catalog.isLoading && (
            <li className="px-3 py-2 text-[12px] text-text-muted">No element matches "{query}"</li>
          )}
          {items.map((e, i) => {
            const ok = supported(e);
            return (
              <li
                key={e.symbol}
                role="option"
                aria-selected={e.symbol === value}
                aria-disabled={!ok}
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(ev) => { ev.preventDefault(); choose(e); }}
                title={
                  !ok
                    ? e.symbol === exclude
                      ? "already chosen as the other element"
                      : engine === "emt"
                        ? "no EMT parameters for this element"
                        : "no pseudopotential on disk — run: python -m alloylab.pseudos " + e.symbol
                    : e.note ?? undefined
                }
                className={cn(
                  "flex cursor-pointer items-baseline gap-3 px-3 py-1.5 text-[13px]",
                  i === cursor && ok && "bg-accent/[0.08]",
                  !ok && "cursor-not-allowed opacity-40",
                )}
              >
                <span className="w-7 font-mono font-semibold">{e.symbol}</span>
                <span className="text-text-secondary">{e.name}</span>
                <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
                  Z{e.atomic_number} · {e.structure}
                  {!e.fcc_native && <span className="text-brass"> · hypothetical fcc</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
