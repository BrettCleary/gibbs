"use client";

/** Final Report View (plan section 16): recommendation, reasoning trail,
 * confidence, uncertainties, failures, limitations. Composed as a document:
 * one large recommendation moment, then quiet evidence sections. */

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import {
  DataValue,
  ErrorNote,
  LoadingNote,
  Metric,
  SectionLabel,
  StatusBadge,
  Surface,
  TechnicalLabel,
} from "@/components/ui/primitives";

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const report = useQuery({
    queryKey: ["report", id],
    queryFn: async () => {
      const { data, error } = await api.GET("/campaigns/{campaign_id}/report", {
        params: { path: { campaign_id: id } },
      });
      if (error) throw error;
      return data!;
    },
  });
  const r = report.data;
  if (!r) {
    return report.isError ? (
      <ErrorNote>Could not load the report.</ErrorNote>
    ) : (
      <LoadingNote>Generating report</LoadingNote>
    );
  }

  const cand = r.recommendation?.candidate as Record<string, any> | null | undefined;
  const narrative = (r.llm_narrative ?? r.narrative ?? "").split("\n\n").filter(Boolean);
  const failures = Object.entries((r.failures.by_category ?? {}) as Record<string, unknown>);

  return (
    <article className="mx-auto flex max-w-4xl flex-col gap-10">
      {/* ------------------------------------------------------ masthead */}
      <header className="flex flex-col gap-4">
        <Link
          href={`/campaigns/${id}`}
          className="inline-flex w-fit items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted transition-colors hover:text-text"
        >
          <ArrowLeft className="h-3 w-3" /> campaign
        </Link>
        <div className="flex flex-wrap items-center gap-2.5">
          <TechnicalLabel>Scientific report</TechnicalLabel>
          <StatusBadge status={r.status} />
          <span className="ml-auto font-mono text-[11px] text-text-muted">
            generated {new Date(r.generated_at).toLocaleString()}
          </span>
        </div>
        <h1 className="text-2xl font-medium tracking-tight text-text md:text-[30px] md:leading-tight">
          {r.title}
        </h1>
      </header>

      {/* -------------------------------------------- recommendation moment */}
      <section className="relative overflow-hidden rounded-md border border-verdigris/25 bg-verdigris/[0.05] px-6 py-6 md:px-8 md:py-7">
        <div aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-verdigris/10 blur-3xl" />
        <SectionLabel className="text-verdigris/80">Recommendation</SectionLabel>
        {r.recommendation?.text ? (
          <p className="mt-3 max-w-2xl text-[17px] leading-relaxed text-text md:text-[19px]">
            {String(r.recommendation.text)}
          </p>
        ) : (
          <p className="mt-3 text-[14px] text-text-secondary">
            No recommendation recorded{r.status !== "COMPLETED" ? " — campaign not finished" : ""}.
          </p>
        )}
        {cand && (
          <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-verdigris/15 pt-5 sm:grid-cols-4">
            <Metric label="structure" value={cand.label} tone="good" />
            <Metric label="x_Al" value={Number(cand.x).toFixed(3)} />
            <Metric label="bulk modulus" value={`${Number(cand.bulk_modulus).toFixed(0)} GPa`} />
            <Metric label="ΔE_form" value={`${Number(cand.e_form).toFixed(3)} eV`} />
            <Metric label="0 K" value={cand.stable_0k ? "stable" : "unstable"} tone={cand.stable_0k ? "good" : "bad"} />
            <Metric label="at threshold" value={String(cand.stability_at_threshold)} tone={cand.stability_at_threshold === "ordered" ? "good" : cand.stability_at_threshold === "disordered" ? "bad" : "default"} />
            <Metric label="source" value={cand.measured ? "measured" : "predicted"} tone={cand.measured ? "default" : "accent"} />
          </div>
        )}
      </section>

      {/* --------------------------------------------------------- summary */}
      <Section title="Summary">
        <div className="max-w-2xl space-y-3 text-[14.5px] leading-relaxed text-text">
          {narrative.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          {narrative.length === 0 && <p className="text-text-secondary">No narrative yet.</p>}
        </div>
        {r.llm_narrative && (
          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
            prose written by the LLM from the structured facts below
          </p>
        )}
      </Section>

      <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
        <Section title="Key results">
          {r.key_results.length === 0 ? (
            <p className="text-[13px] text-text-secondary">None yet.</p>
          ) : (
            <ul className="space-y-2 text-[13.5px] leading-relaxed">
              {r.key_results.map((k, i) => (
                <li key={i} className="flex gap-3">
                  <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-accent" />
                  <span>{k}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Model & confidence">
          <Facts
            rows={[
              ["model", `${String(r.model.type ?? "—")} v${String(r.model.version ?? "—")}`],
              ["training points", String(r.model.n_training_points ?? "—")],
              r.model.loocv_rmse != null && ["CE LOOCV RMSE", `${Number(r.model.loocv_rmse).toFixed(4)} eV/atom`],
              r.model.bulk_modulus_loocv_gpa != null && ["B LOOCV", `${Number(r.model.bulk_modulus_loocv_gpa).toFixed(1)} GPa`],
              r.model.tc_mean != null && ["Tc", `${Number(r.model.tc_mean).toFixed(3)} ± ${Number(r.model.tc_std).toFixed(3)}`],
              r.model.max_tc_std != null && ["max σ(Tc)", `${Number(r.model.max_tc_std).toFixed(0)} K`],
            ]}
          />
        </Section>

        <Section title="Budget & engines">
          <Facts
            rows={[
              ["budget used", `${String(r.budget.used)} / ${String(r.budget.total)}`],
              ...Object.entries((r.budget.successful_by_type ?? {}) as Record<string, unknown>).map(
                ([k, v]) => [k.toLowerCase().replace("_", " "), `${String(v)} succeeded`] as [string, string],
              ),
              ["failed / retried", `${String(r.budget.failed)} / ${String(r.budget.retries)}`],
              ["engine time", `${Number(r.budget.total_compute_seconds).toFixed(0)} s`],
              ["engines", r.engines.join(", ") || "—"],
            ]}
          />
        </Section>

        <Section title="Failures">
          {failures.length === 0 ? (
            <p className="text-[13px] text-text-secondary">No failed calculations.</p>
          ) : (
            <Facts
              rows={[
                ...failures.map(([k, v]) => [k, `× ${String(v)}`] as [string, string]),
                ["retried with adjusted settings", String(r.failures.n_retried)],
              ]}
              keyTone="bad"
            />
          )}
        </Section>
      </div>

      <Section title="Limitations">
        <ul className="space-y-2 text-[13.5px] leading-relaxed text-text-secondary">
          {r.limitations.map((l, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-brass" />
              <span>{l}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Reasoning trail · ${r.decision_trail.length} decisions`}>
        <ol className="relative ml-1 border-l border-line pl-5">
          {r.decision_trail.map((d, i) => (
            <li key={i} className="relative pb-5 last:pb-0">
              <span className="absolute -left-[25px] top-[7px] h-[7px] w-[7px] rounded-full border border-bg bg-steel" />
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
                {String(i + 1).padStart(2, "0")} · {new Date(d.at as string).toLocaleTimeString()}
              </div>
              <p className="mt-1 text-[13.5px] leading-relaxed text-text">{d.hypothesis as string}</p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-text-secondary">→ {d.action as string}</p>
            </li>
          ))}
        </ol>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <SectionLabel className="mb-3">{title}</SectionLabel>
      {children}
    </section>
  );
}

function Facts({
  rows,
  keyTone,
}: {
  rows: Array<[string, string] | false | null | undefined>;
  keyTone?: "bad";
}) {
  return (
    <Surface className="overflow-hidden">
      <dl className="divide-y divide-line">
        {rows.filter(Boolean).map((row) => {
          const [k, v] = row as [string, string];
          return (
            <div key={k} className="flex items-baseline justify-between gap-4 px-4 py-2">
              <dt className={keyTone === "bad" ? "font-mono text-[12px] text-oxide" : "text-[12.5px] text-text-secondary"}>
                {k}
              </dt>
              <dd>
                <DataValue className="text-[12.5px]">{v}</DataValue>
              </dd>
            </div>
          );
        })}
      </dl>
    </Surface>
  );
}
