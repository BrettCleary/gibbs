"use client";

/**
 * The copilot sidebar: a persistent right panel with one continuous thread
 * that follows the scientist across pages (the current page/campaign/form is
 * sent as context with every message). Replies stream in as text and tool
 * cards; form proposals are applied to the form as they land.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, SendHorizontal, Sparkles, Square, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { applyEvent, streamReply, type Turn } from "@/lib/copilot";
import { IconButton, TechnicalLabel, Textarea } from "@/components/ui/primitives";
import { useCopilot } from "./CopilotProvider";
import { CopilotTurn } from "./CopilotMessage";

const THREAD_KEY = (scope: string) => `gibbs.copilot-chat.${scope}`;

const SUGGESTIONS: Record<"new_campaign" | "campaign" | "other", string[]> = {
  new_campaign: [
    "Set up a Cu–Au formation-energy hull campaign with EMT",
    "Find the stiffest stable Ni–Al ordering with a small budget",
    "Which elements can I use with EMT?",
  ],
  campaign: [
    "What did this campaign find, and how confident is it?",
    "Which phases are predicted stable, and what's the evidence?",
    "Did any calculations fail? Why?",
  ],
  other: [
    "Which campaigns have finished, and what did they conclude?",
    "What can you help me with?",
  ],
};

export function CopilotSidebar() {
  // One continuous thread across pages; the page context is sent per message.
  return <Thread scope="active" />;
}

function readRemembered(scope: string): string | null {
  try {
    return window.localStorage.getItem(THREAD_KEY(scope));
  } catch {
    return null;
  }
}

function remember(scope: string, id: string | null) {
  try {
    if (id) window.localStorage.setItem(THREAD_KEY(scope), id);
    else window.localStorage.removeItem(THREAD_KEY(scope));
  } catch {
    /* storage unavailable */
  }
}

function Thread({ scope }: { scope: string }) {
  const copilot = useCopilot();
  const queryClient = useQueryClient();
  const page = copilot.formBridge ? "new_campaign" : copilot.campaignId ? "campaign" : "other";

  const status = useQuery({
    queryKey: ["copilot-status"],
    queryFn: async () => (await api.GET("/copilot/status")).data ?? null,
    staleTime: 60_000,
  });

  // The thread for this scope: remembered per browser, else the most recent
  // one on the server, else created lazily on first send.
  const initial = useQuery({
    queryKey: ["copilot-thread", scope],
    queryFn: async () => {
      const remembered = readRemembered(scope);
      if (remembered) {
        const { data } = await api.GET("/copilot/chats/{chat_id}", {
          params: { path: { chat_id: remembered } },
        });
        if (data) return data;
      }
      const { data: list } = await api.GET("/copilot/chats");
      const latest = list?.[0];
      if (!latest) return null;
      const { data } = await api.GET("/copilot/chats/{chat_id}", {
        params: { path: { chat_id: latest.id } },
      });
      return data ?? null;
    },
    staleTime: Infinity,
  });

  // Local state overrides the loaded thread once the scientist interacts.
  const [local, setLocal] = useState<{ threadId: string | null; turns: Turn[] } | null>(null);
  const threadId = local ? local.threadId : (initial.data?.id ?? null);
  const turns = useMemo<Turn[]>(
    () => (local ? local.turns : ((initial.data?.transcript as Turn[] | undefined) ?? [])),
    [local, initial.data],
  );
  const setTurns = useCallback(
    (update: (prev: Turn[]) => Turn[]) =>
      setLocal((prev) => {
        const base = prev ?? {
          threadId: initial.data?.id ?? null,
          turns: (initial.data?.transcript as Turn[] | undefined) ?? [],
        };
        return { ...base, turns: update(base.turns) };
      }),
    [initial.data],
  );

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Hand focus back to the composer once a reply finishes streaming.
  useEffect(() => {
    if (!busy) inputRef.current?.focus();
  }, [busy]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns]);

  const newThread = useCallback(() => {
    abortRef.current?.abort();
    setLocal({ threadId: null, turns: [] });
    setError(null);
    remember(scope, null);
  }, [scope]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || busy) return;
      setError(null);
      setBusy(true);
      setInput("");
      let id = threadId;
      if (!id) {
        const { data, error: createError } = await api.POST("/copilot/chats", { body: {} });
        if (!data) {
          setError(
            String((createError as { detail?: unknown })?.detail ?? "could not start a thread"),
          );
          setBusy(false);
          return;
        }
        id = data.id;
        remember(scope, id);
        setLocal((prev) => ({ threadId: data.id, turns: prev?.turns ?? [] }));
      }
      const context = copilot.pageContext();
      const pending: Extract<Turn, { role: "assistant" }> = {
        role: "assistant",
        parts: [],
        streaming: true,
      };
      setTurns((prev) => [...prev, { role: "user", text: content }, pending]);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        for await (const event of streamReply(id, content, context, controller.signal)) {
          if (event.type === "done") {
            setTurns(() => event.transcript);
            queryClient.invalidateQueries({ queryKey: ["copilot-thread", scope] });
          } else if (event.type === "error") {
            // Nothing was persisted: drop the failed exchange and hand the text back.
            setError(event.detail);
            setTurns((prev) =>
              prev.filter((t) => t !== pending && !(t.role === "user" && t.text === content)),
            );
            setInput(content);
          } else {
            if (event.type === "patch")
              copilot.formBridge?.applyPatch(event.patch, event.rationale);
            applyEvent(pending, event);
            setTurns((prev) =>
              prev.map((t) => (t === pending ? { ...pending, parts: [...pending.parts] } : t)),
            );
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(String(err));
      } finally {
        if (controller.signal.aborted) {
          // Stopped by the scientist: keep whatever streamed, but settle it.
          pending.streaming = false;
          setTurns((prev) => prev.map((t) => (t === pending ? { ...pending } : t)));
        }
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, threadId, copilot, scope, setTurns, queryClient],
  );

  const contextLabel = useMemo(() => {
    if (copilot.formBridge) return "new campaign";
    if (copilot.campaignId)
      return copilot.campaignName ?? `campaign ${copilot.campaignId.slice(0, 8)}`;
    return "workspace";
  }, [copilot.formBridge, copilot.campaignId, copilot.campaignName]);

  const unavailable = status.data && !status.data.available;

  return (
    <aside
      aria-label="Copilot"
      className="flex h-full w-full flex-col border-l border-line bg-bg-elevated"
    >
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3">
        <Sparkles className="h-3.5 w-3.5 text-accent" />
        <span className="font-mono text-[12px] font-medium tracking-[0.18em] text-text">
          COPILOT
        </span>
        <span
          className="ml-1 truncate rounded-xs border border-line px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted"
          title={contextLabel}
        >
          {contextLabel}
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <IconButton
            label="New thread"
            onClick={newThread}
            disabled={turns.length === 0 && !threadId}
          >
            <Plus className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton label="Close copilot" onClick={() => copilot.setOpen(false)}>
            <X className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      </header>

      <div ref={scrollRef} className="scroll-thin flex-1 overflow-y-auto px-3 py-4">
        {turns.length === 0 ? (
          <div className="flex flex-col gap-4">
            <p className="text-[13px] leading-relaxed text-text-secondary">
              {page === "new_campaign"
                ? "Describe the study you want to run; I'll fill in the form and explain each choice. You review and press Create."
                : page === "campaign"
                  ? "Ask about this campaign's results. Every number I quote comes from its calculations, cited so you can open the evidence."
                  : "I can read your campaigns and their results, or set up a new one with you."}
            </p>
            <div className="flex flex-col gap-1.5">
              <TechnicalLabel>try</TechnicalLabel>
              {SUGGESTIONS[page].map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={busy || !!unavailable}
                  onClick={() => void send(s)}
                  className="rounded-sm border border-line px-2.5 py-1.5 text-left text-[12.5px] text-text-secondary transition-colors hover:border-line-hover hover:bg-white/[0.03] hover:text-text disabled:opacity-45"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {turns.map((t, i) => (
              <CopilotTurn key={i} turn={t} />
            ))}
          </div>
        )}
      </div>

      {(error || unavailable) && (
        <div className="border-t border-oxide/30 bg-oxide/[0.08] px-3 py-2 text-[12px] leading-relaxed text-oxide">
          {unavailable ? `Copilot offline: ${status.data?.reason}` : error}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="shrink-0 border-t border-line p-3"
      >
        <div
          onClick={() => inputRef.current?.focus()}
          className={cn(
            "flex cursor-text items-end gap-2 rounded-sm border border-line bg-white/[0.03] py-1.5 pl-2.5 pr-1.5 transition-colors",
            "hover:border-line-hover focus-within:border-accent/60 focus-within:ring-2 focus-within:ring-accent/25",
          )}
        >
          <Textarea
            ref={inputRef}
            unstyled
            minRows={1}
            maxRows={8}
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Let IME composition (e.g. CJK input) consume Enter.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send(input);
              }
            }}
            placeholder={
              page === "new_campaign" ? "e.g. Cu–Au hull with EMT, budget 15" : "Ask the copilot…"
            }
            disabled={!!unavailable}
            className="flex-1 py-1 text-[13px] text-text placeholder:text-text-muted focus:outline-none disabled:opacity-45"
          />
          {busy ? (
            <button
              type="button"
              onClick={stop}
              aria-label="Stop generating"
              title="Stop generating"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm text-text-secondary transition-colors hover:bg-white/[0.06] hover:text-text"
            >
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim() || !!unavailable}
              aria-label="Send"
              title="Send"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm text-accent transition-colors hover:bg-accent/15 disabled:opacity-35"
            >
              <SendHorizontal className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div className="mt-1.5 flex items-center justify-between font-mono text-[10px] text-text-muted">
          <span>enter to send · shift+enter for a new line</span>
          {status.data && (
            <span title={status.data.model}>{status.data.model.split(":").pop()}</span>
          )}
        </div>
      </form>
    </aside>
  );
}
