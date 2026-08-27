/**
 * Gibbs mark — a G built from the common-tangent construction: the crossbar is
 * a tie-line and its two nodes are the coexisting phases it connects. The stem
 * drops from the right node, closing the letter.
 *
 * Drawn on a 24-unit grid, r=8 about (12,12). The arc opens ~70 degrees on the
 * right (24 deg to 315 deg), which the tie-line spans. Uniform stroke rather
 * than the tapered original: the taper stops resolving below ~32px, and the
 * visual system calls for even hairline weights.
 */
export function GibbsMark({
  size = 18,
  weight = 1.4,
  className,
}: {
  size?: number;
  weight?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={className}
    >
      <path
        d="M19.31 8.75A8 8 0 1 0 17.66 17.66"
        stroke="currentColor"
        strokeWidth={weight}
        strokeLinecap="round"
      />
      <path
        d="M6.6 12h13.4v7.6"
        stroke="currentColor"
        strokeWidth={weight}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="6.6" cy="12" r={weight * 1.07} fill="currentColor" />
      <circle cx="20" cy="12" r={weight * 1.07} fill="currentColor" />
    </svg>
  );
}

/** Mark + wordmark, stacked. For the login card and any full-brand surface. */
export function GibbsLockup({ className }: { className?: string }) {
  return (
    <div className={className}>
      <GibbsMark size={34} weight={1.15} className="text-accent" />
      <span className="mt-3 block font-mono text-[13px] font-medium tracking-[0.22em] text-text">
        GIBBS
      </span>
    </div>
  );
}
