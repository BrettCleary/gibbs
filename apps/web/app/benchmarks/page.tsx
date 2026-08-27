"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import type { BenchmarkRun } from "@alloylab/api-client";
import { api } from "@/lib/api";
import {
  Button,
  DataValue,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  LoadingNote,
  PageTitle,
  PanelHeader,
  Select,
  StatusBadge,
  Surface,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/ui/primitives";

type Problem = "ising" | "alloy" | "fcc" | "phase" | "property";

const PROBLEM_LABEL: Record<Problem, string> = {
  property: "stiff & stable search",
  phase: "Ni–Al phase diagram",
  fcc: "FCC Ni–Al (icet)",
  alloy: "binary alloy",
  ising: "ising",
};

export default function BenchmarksPage() {
  const queryClient = useQueryClient();
  const [problem, setProblem] = useState<Problem>("property");
  const [budget, setBudget] = useState(10);
  const [nSeeds, setNSeeds] = useState(3);

  const benchmarks = useQuery({
    queryKey: ["benchmarks"],
    queryFn: async () => {
      const { data } = await api.GET("/benchmarks");
      return data ?? [];
    },
    refetchInterval: (q) => (q.state.data?.some((b) => b.status === "RUNNING") ? 3000 : false),
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
    <div className="flex flex-col gap-8">
      <PageTitle
        eyebrow="Evaluation"
        title="Benchmark mode"
        description="Does smarter experiment selection reconstruct the ground truth with fewer expensive queries? Every strategy gets the same budget against the same hidden Hamiltonian — a fresh one per seed — and is scored on regret, hull reconstruction, or boundary error."
      />

      <Surface>
        <form
          className="flex flex-wrap items-end gap-4 px-5 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field label="problem" className="w-56">
            <Select value={problem} onChange={(e) => setProblem(e.target.value as Problem)}>
              {(Object.keys(PROBLEM_LABEL) as Problem[]).map((p) => (
                <option key={p} value={p}>
                  {PROBLEM_LABEL[p]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="budget / run" className="w-28">
            <Input type="number" min={4} max={60} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </Field>
          <Field label="seeds" className="w-24">
            <Input type="number" min={1} max={10} value={nSeeds} onChange={(e) => setNSeeds(Number(e.target.value))} />
          </Field>
          <div className="flex items-center gap-3">
            <Button type="submit" variant="primary" icon={<Play className="h-3.5 w-3.5" />} loading={create.isPending}>
              {create.isPending ? "Launching" : "Run benchmark"}
            </Button>
            <span className="font-mono text-[11px] text-text-muted">random · grid · uncertainty</span>
          </div>
          {create.error && (
            <ErrorNote className="basis-full">
              {String((create.error as any)?.detail ?? create.error)}
            </ErrorNote>
          )}
        </form>
      </Surface>

      {benchmarks.isLoading && <LoadingNote>Loading benchmarks</LoadingNote>}
      {benchmarks.isError && (
        <Surface>
          <EmptyState
            title="API unreachable"
            description="The web app could not reach the AlloyLab API, so no benchmark runs can be listed or launched."
          />
        </Surface>
      )}
      {benchmarks.data?.length === 0 && (
        <Surface>
          <EmptyState
            title="No benchmarks yet"
            description="Launch one above. Runs compute a high-budget ground truth first, then score each strategy with the same finite budget."
          />
        </Surface>
      )}
      {(benchmarks.data ?? []).map((b) => (
        <BenchmarkCard key={b.id} benchmark={b} />
      ))}
    </div>
  );
}

type IsingStats = { mean_tc_error: number; max_tc_error: number; mean_tc_std: number; n_runs: number };
type AlloyStats = { mean_hull_rmse: number; mean_missed_stable: number; mean_false_stable: number; n_runs: number };
type PhaseStats = { mean_boundary_error: number; max_boundary_error: number; n_runs: number };
type PropertyStats = { mean_regret_gpa: number; max_regret_gpa: number; frac_truly_stable: number; n_runs: number };
type Stats = IsingStats & AlloyStats & PhaseStats & PropertyStats;

function BenchmarkCard({ benchmark: b }: { benchmark: BenchmarkRun }) {
  const problem = String(b.summary?.problem ?? b.config?.problem ?? "ising") as Problem;
  const isPhase = problem === "phase";
  const isProperty = problem === "property";
  const isAlloy = problem === "alloy" || problem === "fcc";
  const per = (b.summary?.per_strategy ?? {}) as Record<string, Stats>;
  const score = (s: Stats) =>
    isProperty ? s.mean_regret_gpa : isPhase ? s.mean_boundary_error : isAlloy ? s.mean_hull_rmse : s.mean_tc_error;
  const ranked = Object.entries(per).sort((x, y) => score(x[1]) - score(y[1]));
  const best = ranked[0]?.[0];

  const columns: Array<[string, (s: Stats) => string]> = isProperty
    ? [
        ["mean regret (GPa)", (s) => s.mean_regret_gpa.toFixed(1)],
        ["max regret (GPa)", (s) => s.max_regret_gpa.toFixed(1)],
        ["truly stable", (s) => `${(s.frac_truly_stable * 100).toFixed(0)}%`],
      ]
    : isPhase
      ? [
          ["mean |Tc error| (K)", (s) => s.mean_boundary_error.toFixed(0)],
          ["max |Tc error| (K)", (s) => s.max_boundary_error.toFixed(0)],
        ]
      : isAlloy
        ? [
            ["mean hull RMSE", (s) => s.mean_hull_rmse.toFixed(4)],
            ["missed stable / run", (s) => s.mean_missed_stable.toFixed(1)],
            ["false stable / run", (s) => s.mean_false_stable.toFixed(1)],
          ]
        : [
            ["mean |Tc error|", (s) => s.mean_tc_error.toFixed(4)],
            ["max |Tc error|", (s) => s.max_tc_error.toFixed(4)],
            ["mean reported σ(Tc)", (s) => s.mean_tc_std.toFixed(4)],
          ];

  return (
    <Surface className="animate-fade-up">
      <PanelHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span>{PROBLEM_LABEL[problem] ?? problem}</span>
            <StatusBadge status={b.status} />
          </span>
        }
        aside={
          <span className="font-mono">
            budget {String(b.config?.budget)} · {(b.config?.seeds as number[] | undefined)?.length ?? "?"} seeds
            {!isAlloy && b.summary?.tc_true != null && ` · true Tc ${Number(b.summary.tc_true).toFixed(3)}`}
            {" · "}
            {new Date(b.created_at).toLocaleString()}
          </span>
        }
      />
      {b.error && <ErrorNote className="m-4">{b.error}</ErrorNote>}
      {b.status === "RUNNING" && <LoadingNote>Running ground truth and strategy comparisons</LoadingNote>}
      {ranked.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>Strategy</Th>
              <Th align="right">Queries</Th>
              {columns.map(([h]) => (
                <Th key={h} align="right">
                  {h}
                </Th>
              ))}
              <Th align="right">Runs</Th>
            </tr>
          </thead>
          <tbody>
            {ranked.map(([name, stats], i) => (
              <Tr key={name} selected={name === best}>
                <Td>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-text-muted">{i + 1}</span>
                    <DataValue className="text-[12.5px]">{name}</DataValue>
                    {name === best && (
                      <span className="rounded-xs border border-verdigris/40 px-1 font-mono text-[9px] uppercase tracking-[0.14em] text-verdigris">
                        best
                      </span>
                    )}
                  </span>
                </Td>
                <Td align="right">
                  <DataValue dim className="text-[12.5px]">{String(b.config?.budget)}</DataValue>
                </Td>
                {columns.map(([h, fn]) => (
                  <Td key={h} align="right">
                    <DataValue className="text-[12.5px]">{fn(stats)}</DataValue>
                  </Td>
                ))}
                <Td align="right">
                  <DataValue dim className="text-[12.5px]">{stats.n_runs}</DataValue>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </Surface>
  );
}
