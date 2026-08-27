/** Tiny class joiner — no dependency needed for our usage. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
