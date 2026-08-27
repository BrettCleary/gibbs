"use client";

/** Final Report View (plan section 16): recommendation, reasoning trail,
 * confidence, uncertainties, failures, limitations. */

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const report = useQuery({
    queryKey: ["report", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/campaigns/{campaign_id}/report", { params: { path: { campaign_id: id } } });
      if (error) throw error;
      return data!;
    },
  });
  const r = report.data;
  if (!r) return <p className="text-[var(--text-dim)]">Generating report…</p>;

  const cand = r.recommendation?.candidate as Record<string, any> | null | undefined;
  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <section className="panel">
      <div className="border-b border-[var(--border)] px-4 py-2.5">
        <h2 className="mono text-[11px] font-bold tracking-wider text-[var(--text-dim)]">{title}</h2>
      </div>
      <div className="p-4 text-[13px] leading-relaxed">{children}</div>
    </section>
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5">
      <div className="flex items-baseline gap-3">
        <Link href={`/campaigns/${id}`} className="mono text-[11px] text-[var(--accent)]">← campaign</Link>
        <h1 className="text-lg font-semibold">{r.title}</h1>
        <StatusBadge status={r.status} />
        <span className="mono ml-auto text-[11px] text-[var(--text-dim)]">generated {new Date(r.generated_at).toLocaleString()}</span>
      </div>

      <Section title="RECOMMENDATION">
        {r.recommendation?.text ? (
          <p className="text-[var(--good)]">{String(r.recommendation.text)}</p>
        ) : (
          <p className="text-[var(--text-dim)]">No recommendation recorded{r.status !== "COMPLETED" ? " (campaign not finished)" : ""}.</p>
        )}
        {cand && (
          <div className="mono mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[12px] md:grid-cols-4">
            <span>label <b>{cand.label}</b></span>
            <span>x_Al <b>{Number(cand.x).toFixed(3)}</b></span>
            <span>B <b>{Number(cand.bulk_modulus).toFixed(0)} GPa</b></span>
            <span>ΔE_form <b>{Number(cand.e_form).toFixed(3)} eV</b></span>
            <span>0 K <b>{cand.stable_0k ? "stable" : "unstable"}</b></span>
            <span>at threshold <b>{cand.stability_at_threshold}</b></span>
            <span>source <b>{cand.measured ? "measured" : "predicted"}</b></span>
          </div>
        )}
      </Section>

      <Section title="SUMMARY">
        {(r.llm_narrative ?? r.narrative ?? "").split("\n\n").map((p, i) => (
          <p key={i} className="mb-2 last:mb-0">{p}</p>
        ))}
        {r.llm_narrative && <p className="mono mt-2 text-[10px] text-[var(--text-dim)]">narrative written by the LLM from the structured facts below</p>}
      </Section>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Section title="KEY RESULTS">
          <ul className="list-disc space-y-1 pl-4">{r.key_results.map((k, i) => <li key={i}>{k}</li>)}</ul>
          {r.key_results.length === 0 && <p className="text-[var(--text-dim)]">None yet.</p>}
        </Section>
        <Section title="MODEL & CONFIDENCE">
          <dl className="mono grid grid-cols-2 gap-y-1 text-[12px]">
            <dt className="text-[var(--text-dim)]">model</dt><dd>{String(r.model.type ?? "—")} v{String(r.model.version ?? "—")}</dd>
            <dt className="text-[var(--text-dim)]">training points</dt><dd>{String(r.model.n_training_points ?? "—")}</dd>
            {r.model.loocv_rmse != null && (<><dt className="text-[var(--text-dim)]">CE LOOCV RMSE</dt><dd>{Number(r.model.loocv_rmse).toFixed(4)} eV/atom</dd></>)}
            {r.model.bulk_modulus_loocv_gpa != null && (<><dt className="text-[var(--text-dim)]">B LOOCV</dt><dd>{Number(r.model.bulk_modulus_loocv_gpa).toFixed(1)} GPa</dd></>)}
            {r.model.tc_mean != null && (<><dt className="text-[var(--text-dim)]">Tc</dt><dd>{Number(r.model.tc_mean).toFixed(3)} ± {Number(r.model.tc_std).toFixed(3)}</dd></>)}
            {r.model.max_tc_std != null && (<><dt className="text-[var(--text-dim)]">max σ(Tc)</dt><dd>{Number(r.model.max_tc_std).toFixed(0)} K</dd></>)}
          </dl>
        </Section>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Section title="BUDGET & ENGINES">
          <dl className="mono grid grid-cols-2 gap-y-1 text-[12px]">
            <dt className="text-[var(--text-dim)]">budget used</dt><dd>{String(r.budget.used)} / {String(r.budget.total)}</dd>
            {Object.entries((r.budget.successful_by_type ?? {}) as Record<string, unknown>).map(([k, v]) => (<span key={k} className="contents"><dt className="text-[var(--text-dim)]">{k.toLowerCase().replace("_", " ")}</dt><dd>{String(v)} succeeded</dd></span>))}
            <dt className="text-[var(--text-dim)]">failed / retried</dt><dd>{String(r.budget.failed)} / {String(r.budget.retries)}</dd>
            <dt className="text-[var(--text-dim)]">engine time</dt><dd>{Number(r.budget.total_compute_seconds).toFixed(0)} s</dd>
            <dt className="text-[var(--text-dim)]">engines</dt><dd>{r.engines.join(", ") || "—"}</dd>
          </dl>
        </Section>
        <Section title="FAILURES">
          {Object.keys(r.failures.by_category ?? {}).length === 0 ? (
            <p className="text-[var(--text-dim)]">No failed calculations.</p>
          ) : (
            <ul className="mono list-disc space-y-1 pl-4 text-[12px]">
              {Object.entries(r.failures.by_category as Record<string, unknown>).map(([k, v]) => <li key={k}><span className="text-[var(--bad)]">{k}</span> × {String(v)}</li>)}
              <li>{String(r.failures.n_retried)} retried with adjusted settings</li>
            </ul>
          )}
        </Section>
      </div>

      <Section title="LIMITATIONS">
        <ul className="list-disc space-y-1 pl-4 text-[var(--warn)]">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </Section>

      <Section title={`REASONING TRAIL (${r.decision_trail.length} DECISIONS)`}>
        <ol className="space-y-2">
          {r.decision_trail.map((d, i) => (
            <li key={i} className="border-l-2 border-[var(--border)] pl-3">
              <div className="mono text-[10px] text-[var(--text-dim)]">{i + 1} · {new Date(d.at as string).toLocaleTimeString()}</div>
              <div>{d.hypothesis as string}</div>
              <div className="text-[var(--text-dim)]">→ {d.action as string}</div>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
