"use client";

/**
 * Gibbs UI primitives. These encode the visual system (layered surfaces,
 * mono instrumentation labels, sparse accents, 2–4px radii) so pages compose
 * from a shared vocabulary instead of re-declaring class strings.
 */

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  type ComponentProps,
  type ReactNode,
} from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------- surfaces */

export function Surface({
  className,
  interactive,
  ...rest
}: ComponentProps<"div"> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-md border border-line bg-bg-elevated",
        interactive && "transition-colors duration-200 hover:border-line-hover",
        className,
      )}
      {...rest}
    />
  );
}

/** A nested, translucent surface inside a panel. */
export function Inset({ className, ...rest }: ComponentProps<"div">) {
  return (
    <div className={cn("rounded-sm border border-line bg-white/[0.025]", className)} {...rest} />
  );
}

export function PanelHeader({
  title,
  aside,
  className,
}: {
  title: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2",
        className,
      )}
    >
      <SectionLabel>{title}</SectionLabel>
      {aside != null && <div className="text-[11px] text-text-muted">{aside}</div>}
    </div>
  );
}

export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-line", className)} />;
}

/* -------------------------------------------------------------- typography */

export function TechnicalLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn("font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted", className)}
    >
      {children}
    </span>
  );
}

export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h2
      className={cn(
        "font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-secondary",
        className,
      )}
    >
      {children}
    </h2>
  );
}

export function PageTitle({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <TechnicalLabel className="mb-2 block">{eyebrow}</TechnicalLabel>}
        <h1 className="text-2xl font-medium tracking-tight text-text md:text-[28px]">{title}</h1>
        {description && (
          <p className="mt-2 text-[13.5px] leading-relaxed text-text-secondary">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A numeric readout: label above, mono value, optional detail line. */
export function Metric({
  label,
  value,
  detail,
  tone = "default",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "default" | "accent" | "good" | "warn" | "bad";
  className?: string;
}) {
  const toneClass = {
    default: "text-text",
    accent: "text-accent-bright",
    good: "text-verdigris",
    warn: "text-brass",
    bad: "text-oxide",
  }[tone];
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <TechnicalLabel>{label}</TechnicalLabel>
      <div className={cn("font-mono text-[15px] leading-tight tabular-nums", toneClass)}>
        {value}
      </div>
      {detail != null && (
        <div className="truncate font-mono text-[11px] text-text-muted">{detail}</div>
      )}
    </div>
  );
}

export function DataValue({
  children,
  dim,
  className,
}: {
  children: ReactNode;
  dim?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("font-mono tabular-nums", dim ? "text-text-muted" : "text-text", className)}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ status */

export type Tone = "neutral" | "accent" | "good" | "warn" | "bad";

const STATUS_TONE: Record<string, Tone> = {
  CREATED: "neutral",
  QUEUED: "neutral",
  RUNNING: "accent",
  PAUSED: "warn",
  COMPLETED: "good",
  SUCCEEDED: "good",
  FAILED: "bad",
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-text-muted",
  accent: "text-accent-bright",
  good: "text-verdigris",
  warn: "text-brass",
  bad: "text-oxide",
};
const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-steel",
  accent: "bg-accent-bright",
  good: "bg-verdigris",
  warn: "bg-brass",
  bad: "bg-oxide",
};

export function StatusDot({
  tone,
  pulse,
  className,
}: {
  tone: Tone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        TONE_DOT[tone],
        pulse && "animate-pulse-dot",
        className,
      )}
    />
  );
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-xs border border-line bg-white/[0.02] px-1.5 py-[3px] font-mono text-[10px] uppercase tracking-[0.12em]",
        TONE_TEXT[tone],
        className,
      )}
    >
      <StatusDot tone={tone} pulse={status === "RUNNING"} />
      {status}
    </span>
  );
}

/** Inline tag for problem type / engine / etc. Quiet by design. */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-xs border border-line px-1.5 py-[3px] font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- controls */

type ButtonVariant = "primary" | "secondary" | "ghost" | "good" | "warn";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "border-accent/40 bg-accent/15 text-accent-bright hover:bg-accent/25 hover:border-accent/60 active:bg-accent/30",
  secondary:
    "border-line bg-white/[0.03] text-text hover:bg-white/[0.06] hover:border-line-hover active:bg-white/[0.08]",
  ghost:
    "border-transparent text-text-secondary hover:text-text hover:bg-white/[0.04] active:bg-white/[0.06]",
  good: "border-verdigris/40 bg-verdigris/15 text-verdigris hover:bg-verdigris/25 hover:border-verdigris/60 active:bg-verdigris/30",
  warn: "border-brass/40 bg-brass/15 text-brass hover:bg-brass/25 hover:border-brass/60 active:bg-brass/30",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ComponentProps<"button"> & {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-sm border font-medium transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
        "disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "h-7 px-2.5 text-[12px]" : "h-8 px-3.5 text-[13px]",
        BUTTON_VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  className,
  children,
  ...rest
}: ComponentProps<"button"> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-sm border border-transparent text-text-secondary transition-colors hover:border-line hover:bg-white/[0.04] hover:text-text",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

const CONTROL =
  "h-8 w-full rounded-sm border border-line bg-white/[0.03] px-2.5 font-mono text-[13px] text-text " +
  "placeholder:text-text-muted transition-colors duration-150 hover:border-line-hover " +
  "focus:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/25 " +
  "disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-oxide/60";

export function Input({ className, ...rest }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, className)} {...rest} />;
}

/**
 * Autosizing textarea. Grows with content from `minRows` to `maxRows`
 * (measured from the real line-height, so soft-wrapped lines count), then
 * scrolls internally. Pass `unstyled` to opt out of the control chrome when
 * composing it inside your own bordered container (e.g. a chat composer).
 */
export const Textarea = forwardRef<
  HTMLTextAreaElement,
  ComponentProps<"textarea"> & { minRows?: number; maxRows?: number; unstyled?: boolean }
>(function Textarea({ className, minRows = 1, maxRows = 8, unstyled, value, ...rest }, ref) {
  const inner = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => inner.current as HTMLTextAreaElement);

  const resize = useCallback(() => {
    const el = inner.current;
    if (!el) return;
    const cs = getComputedStyle(el);
    const line = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;
    const pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    const border = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth);
    const min = line * minRows + pad + border;
    const max = line * maxRows + pad + border;
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight + border, min), max);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight + border > max ? "auto" : "hidden";
  }, [minRows, maxRows]);

  useLayoutEffect(resize, [resize, value]);
  useLayoutEffect(() => {
    const el = inner.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    return () => ro.disconnect();
  }, [resize]);

  return (
    <textarea
      ref={inner}
      rows={minRows}
      value={value}
      className={cn(
        unstyled ? "w-full bg-transparent" : CONTROL.replace("h-8 ", "py-1.5 "),
        "scroll-thin resize-none leading-relaxed",
        className,
      )}
      {...rest}
    />
  );
});

export function Select({ className, ...rest }: ComponentProps<"select">) {
  return <select className={cn(CONTROL, "cursor-pointer", className)} {...rest} />;
}

export function Field({
  label,
  hint,
  className,
  children,
  ...rest
}: Omit<ComponentProps<"label">, "children"> & {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1.5", className)} {...rest}>
      <TechnicalLabel className="leading-snug">{label}</TechnicalLabel>
      {children}
      {hint && <span className="text-[11px] text-text-muted">{hint}</span>}
    </label>
  );
}

/* -------------------------------------------------------------- indicators */

export function ProgressBar({
  value,
  max,
  tone = "accent",
  className,
}: {
  value: number;
  max: number;
  tone?: "accent" | "good" | "warn";
  className?: string;
}) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const fill = { accent: "bg-accent", good: "bg-verdigris", warn: "bg-brass" }[tone];
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn("h-1 w-full overflow-hidden rounded-full bg-white/[0.06]", className)}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-300", fill)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-2 px-5 py-8", className)}>
      <TechnicalLabel>{title}</TechnicalLabel>
      {description && (
        <p className="max-w-md text-[13px] leading-relaxed text-text-secondary">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children, className }: { children: ReactNode; className?: string }) {
  if (!children) return null;
  return (
    <p
      role="alert"
      className={cn(
        "rounded-sm border border-oxide/30 bg-oxide/10 px-3 py-2 text-[12.5px] text-oxide",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function LoadingNote({ children = "Loading…" }: { children?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-1 py-6 text-[13px] text-text-muted">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ tables */

export function Table({ className, ...rest }: ComponentProps<"table">) {
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className={cn("w-full border-collapse text-[13px]", className)} {...rest} />
    </div>
  );
}

export function Th({ className, align, ...rest }: ComponentProps<"th"> & { align?: "right" }) {
  return (
    <th
      className={cn(
        "border-b border-line px-4 py-2 text-left font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted",
        align === "right" && "text-right",
        className,
      )}
      {...rest}
    />
  );
}

export function Td({ className, align, ...rest }: ComponentProps<"td"> & { align?: "right" }) {
  return (
    <td
      className={cn(
        "border-b border-line px-4 py-2 align-middle tabular-nums",
        align === "right" && "text-right",
        className,
      )}
      {...rest}
    />
  );
}

export function Tr({
  className,
  selected,
  clickable,
  ...rest
}: ComponentProps<"tr"> & { selected?: boolean; clickable?: boolean }) {
  return (
    <tr
      className={cn(
        "transition-colors duration-100 last:[&>td]:border-b-0",
        clickable && "cursor-pointer hover:bg-white/[0.03]",
        selected && "bg-accent/[0.07] hover:bg-accent/[0.09]",
        className,
      )}
      {...rest}
    />
  );
}
