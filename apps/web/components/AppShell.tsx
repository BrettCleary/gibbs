"use client";

/**
 * Authenticated app chrome: top bar, page content, and the copilot sidebar
 * docked on the right (an overlay below the xl breakpoint).
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from "react";
import { cn } from "@/lib/cn";
import { TopBar } from "@/components/TopBar";
import { CopilotProvider, useCopilot } from "@/components/copilot/CopilotProvider";
import { CopilotSidebar } from "@/components/copilot/CopilotSidebar";

const MIN_W = 320;
const MAX_W = 720;
const DEFAULT_W = 400;
const WIDTH_KEY = "gibbs.copilot-width";

const clamp = (w: number) => Math.min(MAX_W, Math.max(MIN_W, Math.round(w)));

const WIDTH_EVENT = "gibbs:copilot-width";
const readWidth = () => {
  try {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY));
    return saved ? clamp(saved) : DEFAULT_W;
  } catch {
    return DEFAULT_W;
  }
};
const subscribeWidth = (cb: () => void) => {
  window.addEventListener(WIDTH_EVENT, cb);
  return () => window.removeEventListener(WIDTH_EVENT, cb);
};

/** Sidebar width in px, persisted per browser and clamped to a sane range. */
function useSidebarWidth() {
  const width = useSyncExternalStore(subscribeWidth, readWidth, () => DEFAULT_W);
  const commit = useCallback((w: number) => {
    try {
      window.localStorage.setItem(WIDTH_KEY, String(clamp(w)));
    } catch {
      /* storage unavailable */
    }
    window.dispatchEvent(new Event(WIDTH_EVENT));
  }, []);
  return [width, commit] as const;
}

/**
 * Drag handle on the sidebar's left edge. Pointer capture keeps the drag alive
 * when the cursor outruns the 6px strip; width is derived from the pointer's
 * distance to the right viewport edge so there's no accumulated delta drift.
 */
function ResizeHandle({
  width,
  onResize,
  onReset,
  onDragChange,
}: {
  width: number;
  onResize: (w: number) => void;
  onReset: () => void;
  onDragChange: (dragging: boolean) => void;
}) {
  const [dragging, setDraggingState] = useState(false);
  const setDragging = (d: boolean) => {
    setDraggingState(d);
    onDragChange(d);
  };
  const raf = useRef(0);
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize copilot"
      aria-valuenow={width}
      aria-valuemin={MIN_W}
      aria-valuemax={MAX_W}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onResize(width + 24);
        else if (e.key === "ArrowRight") onResize(width - 24);
        else return;
        e.preventDefault();
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        setDragging(true);
      }}
      onPointerMove={(e) => {
        if (!dragging) return;
        const x = e.clientX;
        cancelAnimationFrame(raf.current);
        raf.current = requestAnimationFrame(() => onResize(window.innerWidth - x));
      }}
      onPointerUp={(e) => {
        e.currentTarget.releasePointerCapture(e.pointerId);
        setDragging(false);
      }}
      onPointerCancel={() => setDragging(false)}
      className={cn(
        "group absolute inset-y-0 -left-[3px] z-10 w-[6px] cursor-col-resize touch-none select-none",
        "focus-visible:outline-none",
      )}
    >
      <div
        className={cn(
          "mx-auto h-full w-px transition-colors duration-150",
          dragging
            ? "bg-accent"
            : "bg-transparent group-hover:bg-accent/60 group-focus-visible:bg-accent/60",
        )}
      />
    </div>
  );
}

function Shell({ user, children }: { user: { email: string; name: string }; children: ReactNode }) {
  const { open, setOpen } = useCopilot();
  const [width, setWidth] = useSidebarWidth();

  // Suppress text selection / iframe hijacking while a resize drag is live.
  const [resizing, setResizing] = useState(false);
  useEffect(() => {
    if (!resizing) return;
    const prev = document.body.style.cursor;
    document.body.style.cursor = "col-resize";
    document.body.classList.add("select-none");
    return () => {
      document.body.style.cursor = prev;
      document.body.classList.remove("select-none");
    };
  }, [resizing]);
  return (
    <div className="relative isolate">
      <div
        aria-hidden
        className="bg-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px]"
      />
      <TopBar user={user} />
      <div
        className={cn(
          !resizing && "transition-[padding] duration-200",
          open && "xl:pr-[var(--copilot-w)]",
        )}
        style={{ "--copilot-w": `${width}px` } as CSSProperties}
      >
        <main className="mx-auto w-full max-w-[1400px] px-4 pb-16 pt-6 md:px-8 md:pt-8">
          {children}
        </main>
      </div>
      {open && (
        <>
          <button
            type="button"
            aria-label="Close copilot"
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-30 bg-bg/60 backdrop-blur-[2px] xl:hidden"
          />
          <div className="fixed bottom-0 right-0 top-12 z-40 max-w-full" style={{ width }}>
            <ResizeHandle
              width={width}
              onResize={setWidth}
              onReset={() => setWidth(DEFAULT_W)}
              onDragChange={setResizing}
            />
            <CopilotSidebar />
          </div>
        </>
      )}
    </div>
  );
}

export function AppShell(props: { user: { email: string; name: string }; children: ReactNode }) {
  return (
    <CopilotProvider>
      <Shell {...props} />
    </CopilotProvider>
  );
}
