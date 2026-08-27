"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CampaignCreate } from "@alloylab/api-client";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function CampaignsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const { data } = await api.GET("/campaigns");
      return data ?? [];
    },
    refetchInterval: 5000,
  });

  const create = useMutation({
    mutationFn: async (body: CampaignCreate) => {
      const { data, error } = await api.POST("/campaigns", { body });
      if (error) throw error;
      return data!;
    },
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      router.push(`/campaigns/${campaign.id}`);
    },
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Discovery Campaigns</h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-sm border border-[var(--accent)] px-3 py-1.5 text-sm text-[var(--accent)] hover:bg-[var(--accent)]/10"
        >
          {showForm ? "Cancel" : "New campaign"}
        </button>
      </div>

      {showForm && (
        <CampaignForm
          onSubmit={(body) => create.mutate(body)}
          pending={create.isPending}
          error={create.error ? String((create.error as any)?.detail ?? create.error) : null}
        />
      )}

      <div className="panel">
        <table className="w-full text-sm">
          <thead>
            <tr className="mono border-b border-[var(--border)] text-left text-[11px] text-[var(--text-dim)]">
              <th className="px-4 py-2.5">campaign</th>
              <th className="px-4 py-2.5">strategy</th>
              <th className="px-4 py-2.5">status</th>
              <th className="px-4 py-2.5">budget</th>
              <th className="px-4 py-2.5">objective</th>
            </tr>
          </thead>
          <tbody>
            {(campaigns.data ?? []).map((c) => (
              <tr
                key={c.id}
                className="cursor-pointer border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--panel-2)]"
                onClick={() => router.push(`/campaigns/${c.id}`)}
              >
                <td className="px-4 py-2.5">
                  <Link href={`/campaigns/${c.id}`} className="font-medium text-[var(--text)]">
                    {c.name}
                  </Link>
                </td>
                <td className="mono px-4 py-2.5 text-[12px]">{c.strategy}</td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={c.status} />
                </td>
                <td className="mono px-4 py-2.5 text-[12px]">
                  {c.simulations_used} / {c.simulation_budget}
                </td>
                <td className="max-w-md truncate px-4 py-2.5 text-[12px] text-[var(--text-dim)]">
                  {c.objective}
                </td>
              </tr>
            ))}
            {campaigns.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-[var(--text-dim)]">
                  No campaigns yet. Create one to launch the autonomous scientist.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CampaignForm({
  onSubmit,
  pending,
  error,
}: {
  onSubmit: (body: CampaignCreate) => void;
  pending: boolean;
  error: string | null;
}) {
  const [form, setForm] = useState({
    name: "Stiffest stable Ni–Al intermetallic",
    problem_type: "property_v3",
    strategy: "uncertainty",
    simulation_budget: 15,
    lattice_size: 24,
    temperature_min: 1.5,
    temperature_max: 3.5,
    failure_rate: 0.15,
    dft_engine: "emt",
    property_engine: "hidden",
    temperature_threshold: 1200,
    target_uncertainty: "" as string,
    phase_t_min: 100,
    phase_t_max: 1200,
  });
  const isPhase = form.problem_type === "phase_v2";
  const isDft = form.problem_type === "dft_v3";
  const isProperty = form.problem_type === "property_v3";
  const isAlloy =
    form.problem_type === "alloy_v1" || form.problem_type === "fcc_v2" || isDft || isProperty;

  const field = "flex flex-col gap-1 text-[12px] text-[var(--text-dim)]";
  const input =
    "rounded-sm border border-[var(--border)] bg-[var(--panel-2)] px-2 py-1.5 text-sm text-[var(--text)] mono";

  return (
    <form
      className="panel grid grid-cols-2 gap-4 p-4 md:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          name: form.name,
          problem_type: form.problem_type as CampaignCreate["problem_type"],
          objective: "",
          strategy: form.strategy as CampaignCreate["strategy"],
          dft_engine: form.dft_engine as CampaignCreate["dft_engine"],
          property_engine: form.property_engine as CampaignCreate["property_engine"],
          temperature_threshold: Number(form.temperature_threshold),
          simulation_budget: Number(form.simulation_budget),
          lattice_size: Number(form.lattice_size),
          temperature_min: Number(
            form.problem_type === "phase_v2" ? form.phase_t_min : form.temperature_min,
          ),
          temperature_max: Number(
            form.problem_type === "phase_v2" ? form.phase_t_max : form.temperature_max,
          ),
          failure_rate: Number(form.failure_rate),
          target_uncertainty:
            form.target_uncertainty === "" ? null : Number(form.target_uncertainty),
        });
      }}
    >
      <label className={`${field} col-span-2`}>
        name
        <input
          className={input}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
      </label>
      <label className={field}>
        problem
        <select
          className={input}
          value={form.problem_type}
          onChange={(e) => setForm({ ...form, problem_type: e.target.value })}
        >
          <option value="property_v3">Stiff &amp; stable Ni–Al search (M8)</option>
          <option value="dft_v3">Real DFT / EMT, Ni–Al (M6)</option>
          <option value="phase_v2">Ni–Al phase diagram, MC (M5)</option>
          <option value="fcc_v2">FCC Ni–Al, icet (V2)</option>
          <option value="alloy_v1">binary alloy (V1)</option>
          <option value="ising_v0">Ising critical region (V0)</option>
        </select>
      </label>
      <label className={field}>
        strategy
        <select
          className={input}
          value={form.strategy}
          onChange={(e) => setForm({ ...form, strategy: e.target.value })}
        >
          <option value="agent">agent (LLM scientist)</option>
          <option value="uncertainty">uncertainty sampling</option>
          <option value="grid">
            {isPhase ? "slice round-robin + grid" : isAlloy ? "composition coverage" : "grid coverage"}
          </option>
          <option value="random">random</option>
        </select>
      </label>
      <label className={field}>
        {isAlloy ? "oracle budget" : "MC budget"}
        <input
          className={input}
          type="number"
          min={4}
          max={200}
          value={form.simulation_budget}
          onChange={(e) => setForm({ ...form, simulation_budget: Number(e.target.value) })}
        />
      </label>
      {!isAlloy && !isPhase && (
        <>
          <label className={field}>
            lattice size L
            <input
              className={input}
              type="number"
              min={8}
              max={64}
              step={2}
              value={form.lattice_size}
              onChange={(e) => setForm({ ...form, lattice_size: Number(e.target.value) })}
            />
          </label>
          <label className={field}>
            T min
            <input
              className={input}
              type="number"
              step={0.1}
              value={form.temperature_min}
              onChange={(e) => setForm({ ...form, temperature_min: Number(e.target.value) })}
            />
          </label>
          <label className={field}>
            T max
            <input
              className={input}
              type="number"
              step={0.1}
              value={form.temperature_max}
              onChange={(e) => setForm({ ...form, temperature_max: Number(e.target.value) })}
            />
          </label>
        </>
      )}
      {isProperty && (
        <>
          <label className={field}>
            property engine
            <select className={input} value={form.property_engine} onChange={(e) => setForm({ ...form, property_engine: e.target.value })}>
              <option value="hidden">hidden oracle (benchmarkable)</option>
              <option value="emt">EMT classical potential (real)</option>
            </select>
          </label>
          <label className={field}>
            stability threshold T (K)
            <input className={input} type="number" step={50} value={form.temperature_threshold} onChange={(e) => setForm({ ...form, temperature_threshold: Number(e.target.value) })} />
          </label>
        </>
      )}
      {isDft && (
        <label className={field}>
          energy engine
          <select
            className={input}
            value={form.dft_engine}
            onChange={(e) => setForm({ ...form, dft_engine: e.target.value })}
          >
            <option value="emt">EMT classical potential (fast)</option>
            <option value="espresso">Quantum ESPRESSO (real DFT, slow)</option>
          </select>
        </label>
      )}
      {isPhase && (
        <>
          <label className={field}>
            T min (K)
            <input
              className={input}
              type="number"
              step={50}
              value={form.phase_t_min}
              onChange={(e) => setForm({ ...form, phase_t_min: Number(e.target.value) })}
            />
          </label>
          <label className={field}>
            T max (K)
            <input
              className={input}
              type="number"
              step={50}
              value={form.phase_t_max}
              onChange={(e) => setForm({ ...form, phase_t_max: Number(e.target.value) })}
            />
          </label>
        </>
      )}
      <label className={field}>
        injected failure rate
        <input
          className={input}
          type="number"
          min={0}
          max={0.9}
          step={0.05}
          value={form.failure_rate}
          onChange={(e) => setForm({ ...form, failure_rate: Number(e.target.value) })}
        />
      </label>
      <label className={field}>
        {isPhase
          ? "target boundary uncertainty, K (optional)"
          : isAlloy
            ? "target stable-phase uncertainty (optional)"
            : "target Tc uncertainty (optional)"}
        <input
          className={input}
          type="number"
          step={0.01}
          placeholder="e.g. 0.05"
          value={form.target_uncertainty}
          onChange={(e) => setForm({ ...form, target_uncertainty: e.target.value })}
        />
      </label>
      <div className="col-span-2 flex items-end gap-3 md:col-span-4">
        <button
          type="submit"
          disabled={pending}
          className="rounded-sm bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-black disabled:opacity-50"
        >
          {pending ? "Creating…" : "Create campaign"}
        </button>
        {error && <span className="text-sm text-[var(--bad)]">{error}</span>}
      </div>
    </form>
  );
}
