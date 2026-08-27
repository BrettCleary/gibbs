"use client";

import { useState } from "react";
import type { CampaignCreate } from "@alloylab/api-client";
import {
  Button,
  Divider,
  ErrorNote,
  Field,
  Input,
  Select,
  Surface,
  TechnicalLabel,
} from "@/components/ui/primitives";
import { PROBLEMS, type ProblemType } from "@/lib/problems";

export function CampaignForm({
  onSubmit,
  onCancel,
  pending,
  error,
}: {
  onSubmit: (body: CampaignCreate) => void;
  onCancel: () => void;
  pending: boolean;
  error: string | null;
}) {
  const [form, setForm] = useState({
    name: "Stiffest stable Ni–Al intermetallic",
    problem_type: "property_v3" as ProblemType,
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
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const isPhase = form.problem_type === "phase_v2";
  const isDft = form.problem_type === "dft_v3";
  const isProperty = form.problem_type === "property_v3";
  const isIsing = form.problem_type === "ising_v0";
  const isAlloy = !isPhase && !isIsing;
  const info = PROBLEMS[form.problem_type];

  return (
    <Surface className="animate-fade-up">
      <form
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
            temperature_min: Number(isPhase ? form.phase_t_min : form.temperature_min),
            temperature_max: Number(isPhase ? form.phase_t_max : form.temperature_max),
            failure_rate: Number(form.failure_rate),
            target_uncertainty:
              form.target_uncertainty === "" ? null : Number(form.target_uncertainty),
          });
        }}
      >
        <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          {/* Left: what & how */}
          <div className="flex flex-col gap-4">
            <TechnicalLabel>Objective</TechnicalLabel>
            <Field label="campaign name">
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} required />
            </Field>
            <Field label="problem" hint={info.long}>
              <Select
                value={form.problem_type}
                onChange={(e) => set("problem_type", e.target.value as ProblemType)}
              >
                <option value="property_v3">Stiff &amp; stable Ni–Al search (M8)</option>
                <option value="dft_v3">Real DFT / EMT, Ni–Al (M6)</option>
                <option value="phase_v2">Ni–Al phase diagram, MC (M5)</option>
                <option value="fcc_v2">FCC Ni–Al, icet (V2)</option>
                <option value="alloy_v1">Binary alloy (V1)</option>
                <option value="ising_v0">Ising critical region (V0)</option>
              </Select>
            </Field>
            <Field label="strategy">
              <Select value={form.strategy} onChange={(e) => set("strategy", e.target.value)}>
                <option value="agent">agent — LLM scientist</option>
                <option value="uncertainty">uncertainty sampling</option>
                <option value="grid">
                  {isPhase ? "slice round-robin + grid" : isAlloy ? "composition coverage" : "grid coverage"}
                </option>
                <option value="random">random</option>
              </Select>
            </Field>
          </div>

          {/* Right: numbers */}
          <div className="flex flex-col gap-4">
            <TechnicalLabel>Parameters</TechnicalLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
              <Field label={info.budgetLabel}>
                <Input
                  type="number"
                  min={4}
                  max={200}
                  value={form.simulation_budget}
                  onChange={(e) => set("simulation_budget", Number(e.target.value))}
                />
              </Field>
              <Field label="injected failure rate">
                <Input
                  type="number"
                  min={0}
                  max={0.9}
                  step={0.05}
                  value={form.failure_rate}
                  onChange={(e) => set("failure_rate", Number(e.target.value))}
                />
              </Field>
              <Field
                label={
                  isPhase
                    ? "boundary uncertainty target, K"
                    : isAlloy
                      ? "stable-phase uncertainty target"
                      : "Tc uncertainty target"
                }
                hint="optional stopping rule"
              >
                <Input
                  type="number"
                  step={0.01}
                  placeholder="e.g. 0.05"
                  value={form.target_uncertainty}
                  onChange={(e) => set("target_uncertainty", e.target.value)}
                />
              </Field>

              {isIsing && (
                <>
                  <Field label="lattice size L">
                    <Input
                      type="number"
                      min={8}
                      max={64}
                      step={2}
                      value={form.lattice_size}
                      onChange={(e) => set("lattice_size", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T min">
                    <Input
                      type="number"
                      step={0.1}
                      value={form.temperature_min}
                      onChange={(e) => set("temperature_min", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T max">
                    <Input
                      type="number"
                      step={0.1}
                      value={form.temperature_max}
                      onChange={(e) => set("temperature_max", Number(e.target.value))}
                    />
                  </Field>
                </>
              )}

              {isProperty && (
                <>
                  <Field label="property engine">
                    <Select
                      value={form.property_engine}
                      onChange={(e) => set("property_engine", e.target.value)}
                    >
                      <option value="hidden">hidden oracle (benchmarkable)</option>
                      <option value="emt">EMT classical potential (real)</option>
                    </Select>
                  </Field>
                  <Field label="stability threshold T (K)">
                    <Input
                      type="number"
                      step={50}
                      value={form.temperature_threshold}
                      onChange={(e) => set("temperature_threshold", Number(e.target.value))}
                    />
                  </Field>
                </>
              )}

              {isDft && (
                <Field label="energy engine" className="col-span-2">
                  <Select value={form.dft_engine} onChange={(e) => set("dft_engine", e.target.value)}>
                    <option value="emt">EMT classical potential (fast)</option>
                    <option value="espresso">Quantum ESPRESSO (real DFT, slow)</option>
                  </Select>
                </Field>
              )}

              {isPhase && (
                <>
                  <Field label="T min (K)">
                    <Input
                      type="number"
                      step={50}
                      value={form.phase_t_min}
                      onChange={(e) => set("phase_t_min", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T max (K)">
                    <Input
                      type="number"
                      step={50}
                      value={form.phase_t_max}
                      onChange={(e) => set("phase_t_max", Number(e.target.value))}
                    />
                  </Field>
                </>
              )}
            </div>
          </div>
        </div>

        <Divider />
        <div className="flex flex-wrap items-center gap-3 px-5 py-3">
          <Button type="submit" variant="primary" loading={pending}>
            {pending ? "Creating" : "Create campaign"}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <ErrorNote className="ml-auto">{error}</ErrorNote>
        </div>
      </form>
    </Surface>
  );
}
