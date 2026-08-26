"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { BenchmarkRun } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function BenchmarksPage() {
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<"ising" | "alloy" | "fcc" | "phase">("phase");
  const [budget, setBudget] = useState(10);
  const [nSeeds, setNSeeds] = useState(3);

  const benchmarks = useQuery({
    queryKey: ["benchmarks"],
    queryFn: async () => {
      const { data } = await api.GET("/benchmarks");
      return data ?? [];
    },
    refetchInterval: (q) =>
      q.state.data?.some((b) => b.status === "RUNNING") ? 3000 : false,
  });

  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/benchmarks", {
        body: {
          problem,
          strategies: ["random", "grid", "uncertainty"],
          budget,
          seeds: Array.from({ length: nSeeds }, (_, i) => i + 1),
          lattice_size: 16,
          temperature_min: 1.5,
          temperature_max: 3.5,
        },
      });
      if (error) throw error;
      return data!;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["benchmarks"] }),
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">Benchmark Mode</h1>
          <p className="mt-1 max-w-2xl text-[13px] text-[var(--text-dim)]">
            Does smarter experiment selection reconstruct the ground truth with
            fewer expensive queries? Ising runs score the Tc estimate against a
            high-budget scan; alloy runs score hull reconstruction (missed and
            false stable phases, hull error) against the exact hidden Hamiltonian
            — a fresh one per seed.
          </p>
        </div>
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <label className="flex flex-col gap-1 text-[12px] text-[var(--text-dim)]">
            problem
            <select
              value={problem}
              onChange={(e) => setProblem(e.target.value as "ising" | "alloy" | "fcc" | "phase")}
              className="mono rounded-sm border border-[var(--border)] bg-[var(--panel-2)] px-2 py-1.5 text-sm text-[var(--text)]"
            >
              <option value="phase">Ni–Al phase diagram</option>
              <option value="fcc">FCC Ni–Al (icet)</option>
              <option value="alloy">binary alloy</option>
              <option value="ising">ising</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-[var(--text-dim)]">
            budget / run
            <input
              type="number"
              min={4}
              max={60}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              className="mono w-24 rounded-sm border border-[var(--border)] bg-[var(--panel-2)] px-2 py-1.5 text-sm text-[var(--text)]"
            />
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-[var(--text-dim)]">
            seeds
            <input
              type="number"
              min={1}
              max={10}
              value={nSeeds}
              onChange={(e) => setNSeeds(Number(e.target.value))}
              className="mono w-20 rounded-sm border border-[var(--border)] bg-[var(--panel-2)] px-2 py-1.5 text-sm text-[var(--text)]"
            />
          </label>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-sm bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-black disabled:opacity-50"
          >
            {create.isPending ? "Launching…" : "Run benchmark"}
          </button>
        </form>
      </div>

      {(benchmarks.data ?? []).map((b) => (
        <BenchmarkCard key={b.id} benchmark={b} />
      ))}
      {benchmarks.data?.length === 0 && (
        <div className="panel px-4 py-8 text-center text-[var(--text-dim)]">
          No benchmarks yet.
        </div>
      )}
    </div>
  );
}

type IsingStats = {
  mean_tc_error: number;
  max_tc_error: number;
  mean_tc_std: number;
  n_runs: number;
};
type AlloyStats = {
  mean_hull_rmse: number;
  mean_missed_stable: number;
  mean_false_stable: number;
  n_runs: number;
};
type PhaseStats = {
  mean_boundary_error: number;
  max_boundary_error: number;
  n_runs: number;
};

function BenchmarkCard({ benchmark: b }: { benchmark: BenchmarkRun }) {
  const problem = String(b.summary?.problem ?? b.config?.problem ?? "ising");
  const isPhase = problem === "phase";
  const isAlloy = problem === "alloy" || problem === "fcc";
  const per = (b.summary?.per_strategy ?? {}) as Record<
    string,
    IsingStats & AlloyStats & PhaseStats
  >;
  const score = (s: IsingStats & AlloyStats & PhaseStats) =>
    isPhase ? s.mean_boundary_error : isAlloy ? s.mean_hull_rmse : s.mean_tc_error;
  const best = Object.entries(per).sort((x, y) => score(x[1]) - score(y[1]))[0]?.[0];

  return (
    <div className="panel">
      <div className="flex items-center gap-4 border-b border-[var(--border)] px-4 py-2.5">
        <span className="mono text-[11px] text-[var(--text-dim)]">
          {new Date(b.created_at).toLocaleString()}
        </span>
        <StatusBadge status={b.status} />
        <span className="mono text-[12px] text-[var(--text-dim)]">
          {isPhase ? "Ni–Al phase diagram" : problem === "fcc" ? "FCC Ni–Al" : problem === "alloy" ? "binary alloy" : "ising"} · budget {String(b.config?.budget)} ·{" "}
          {(b.config?.seeds as number[] | undefined)?.length ?? "?"} seeds
          {!isAlloy && b.summary?.tc_true != null &&
            ` · ground-truth Tc = ${Number(b.summary.tc_true).toFixed(3)}`}
        </span>
        {b.error && <span className="text-sm text-[var(--bad)]">{b.error}</span>}
      </div>
      {b.status === "RUNNING" && (
        <p className="px-4 py-4 text-sm text-[var(--text-dim)]">
          Running ground truth and strategy comparisons…
        </p>
      )}
      {Object.keys(per).length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="mono border-b border-[var(--border)] text-left text-[11px] text-[var(--text-dim)]">
              <th className="px-4 py-2">strategy</th>
              <th className="px-4 py-2">queries</th>
              {isPhase ? (
                <>
                  <th className="px-4 py-2">mean |Tc error| (K)</th>
                  <th className="px-4 py-2">max |Tc error| (K)</th>
                  <th className="px-4 py-2">—</th>
                </>
              ) : isAlloy ? (
                <>
                  <th className="px-4 py-2">mean hull RMSE</th>
                  <th className="px-4 py-2">missed stable / run</th>
                  <th className="px-4 py-2">false stable / run</th>
                </>
              ) : (
                <>
                  <th className="px-4 py-2">mean |Tc error|</th>
                  <th className="px-4 py-2">max |Tc error|</th>
                  <th className="px-4 py-2">mean reported σ(Tc)</th>
                </>
              )}
              <th className="px-4 py-2">runs</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(per)
              .sort((x, y) => score(x[1]) - score(y[1]))
              .map(([name, stats]) => (
                <tr key={name} className="border-b border-[var(--border)] last:border-b-0">
                  <td className="mono px-4 py-2">
                    {name}
                    {name === best && (
                      <span className="ml-2 text-[11px] text-[var(--good)]">◂ best</span>
                    )}
                  </td>
                  <td className="mono px-4 py-2">{String(b.config?.budget)}</td>
                  {isPhase ? (
                    <>
                      <td className="mono px-4 py-2">{stats.mean_boundary_error.toFixed(0)}</td>
                      <td className="mono px-4 py-2">{stats.max_boundary_error.toFixed(0)}</td>
                      <td className="mono px-4 py-2">—</td>
                    </>
                  ) : isAlloy ? (
                    <>
                      <td className="mono px-4 py-2">{stats.mean_hull_rmse.toFixed(4)}</td>
                      <td className="mono px-4 py-2">{stats.mean_missed_stable.toFixed(1)}</td>
                      <td className="mono px-4 py-2">{stats.mean_false_stable.toFixed(1)}</td>
                    </>
                  ) : (
                    <>
                      <td className="mono px-4 py-2">{stats.mean_tc_error.toFixed(4)}</td>
                      <td className="mono px-4 py-2">{stats.max_tc_error.toFixed(4)}</td>
                      <td className="mono px-4 py-2">{stats.mean_tc_std.toFixed(4)}</td>
                    </>
                  )}
                  <td className="mono px-4 py-2">{stats.n_runs}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
