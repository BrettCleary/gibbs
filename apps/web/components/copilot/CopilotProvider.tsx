"use client";

/**
 * Shared copilot state: whether the sidebar is open, what page the scientist is
 * on, and the bridge to the new-campaign form (the copilot's "hands").
 *
 * Pages declare themselves with `useCopilotPage`; the form registers a bridge
 * with `useCopilotFormBridge` so proposals land in its state with the changed
 * fields highlighted.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { PageContext } from "@/lib/copilot";

export type FormBridge = {
  getForm: () => Record<string, unknown>;
  applyPatch: (patch: Record<string, unknown>, rationale: string) => void;
};

type CopilotState = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  /** Campaign the current page is about (null on list/benchmark pages). */
  campaignId: string | null;
  campaignName: string | null;
  setCampaign: (id: string | null, name?: string | null) => void;
  formBridge: FormBridge | null;
  setFormBridge: (bridge: FormBridge | null) => void;
  /** Snapshot of what to send with a message. */
  pageContext: () => PageContext;
};

const Ctx = createContext<CopilotState | null>(null);

/* Sidebar open/closed lives in localStorage so it survives navigation and reloads. */
const OPEN_KEY = "gibbs.copilot-open";
const OPEN_EVENT = "gibbs:copilot-open";
const listeners = new Set<() => void>();
function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === "1";
  } catch {
    return false;
  }
}
function writeOpen(next: boolean) {
  try {
    window.localStorage.setItem(OPEN_KEY, next ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(OPEN_EVENT));
}
function subscribeOpen(cb: () => void) {
  listeners.add(cb);
  window.addEventListener(OPEN_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener(OPEN_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function CopilotProvider({ children }: { children: ReactNode }) {
  const open = useSyncExternalStore(subscribeOpen, readOpen, () => false);
  const [campaign, setCampaignState] = useState<{ id: string | null; name: string | null }>({
    id: null,
    name: null,
  });
  const [formBridge, setFormBridge] = useState<FormBridge | null>(null);

  const setOpen = useCallback((next: boolean) => writeOpen(next), []);
  const setCampaign = useCallback((id: string | null, name: string | null = null) => {
    setCampaignState((prev) => (prev.id === id && prev.name === name ? prev : { id, name }));
  }, []);

  const value = useMemo<CopilotState>(
    () => ({
      open,
      setOpen,
      toggle: () => writeOpen(!open),
      campaignId: campaign.id,
      campaignName: campaign.name,
      setCampaign,
      formBridge,
      setFormBridge,
      pageContext: () => {
        if (formBridge) return { page: "new_campaign", form: formBridge.getForm() };
        if (campaign.id) return { page: "campaign", campaign_id: campaign.id };
        return { page: "other" };
      },
    }),
    [open, setOpen, campaign, setCampaign, formBridge],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCopilot(): CopilotState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCopilot must be used inside CopilotProvider");
  return ctx;
}

/** Declare the campaign a page is about (cleared on unmount). */
export function useCopilotPage(campaignId: string | null, campaignName?: string | null) {
  const { setCampaign } = useCopilot();
  useEffect(() => {
    setCampaign(campaignId, campaignName ?? null);
    return () => setCampaign(null, null);
  }, [campaignId, campaignName, setCampaign]);
}

/** Register the new-campaign form as the copilot's hands while it is mounted. */
export function useCopilotFormBridge(bridge: FormBridge) {
  const { setFormBridge } = useCopilot();
  const latest = useRef<FormBridge>(bridge);
  useEffect(() => {
    latest.current = bridge;
  });
  useEffect(() => {
    // A stable object that always delegates to the latest render's closures.
    setFormBridge({
      getForm: () => latest.current.getForm(),
      applyPatch: (patch, rationale) => latest.current.applyPatch(patch, rationale),
    });
    return () => setFormBridge(null);
  }, [setFormBridge]);
}
