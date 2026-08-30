"use client";

import { useCallback, useState } from "react";
import type { CampaignCreate } from "@gibbs/api-client";
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
import { ElementSelect } from "@/components/ElementSelect";
import { useCopilotFormBridge } from "@/components/copilot/CopilotProvider";

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
    name: "Stiffest stable intermetallic",
    element_a: "Ni",
    element_b: "Al",
    problem_type: "property_v3" as ProblemType,
    strategy: "uncertainty",
    simulation_budget: 15,
    lattice_size: 24,
    temperature_min: 1.5,
    temperature_max: 3.5,
    dft_engine: "emt",
    property_engine: "emt",
    temperature_threshold: 1200,
    target_uncertainty: "" as string,
    phase_t_min: 100,
    phase_t_max: 1200,
  });
  // Fields the copilot last changed, with its rationale — cleared per field on edit.
  const [proposed, setProposed] = useState<Record<string, string>>({});
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setProposed((p) => {
      if (!(k in p)) return p;
      const next = { ...p };
      delete next[k];
      return next;
    });
  };
  const mark = useCallback(
    (key: string) =>
      proposed[key] != null
        ? { className: "copilot-proposed", title: proposed[key], "data-proposed": "" }
        : {},
    [proposed],
  );

  // The copilot's hands: it reads the current form and applies patches here;
  // changed fields are highlighted until the scientist edits them.
  useCopilotFormBridge({
    getForm: () => ({ ...form }),
    applyPatch: (patch, rationale) => {
      setForm((f) => {
        const next = { ...f } as Record<string, unknown>;
        for (const [k, v] of Object.entries(patch)) {
          if (!(k in f)) continue;
          const current = (f as Record<string, unknown>)[k];
          next[k] =
            k === "target_uncertainty"
              ? v == null
                ? ""
                : String(v)
              : typeof current === "number"
                ? Number(v)
                : v;
        }
        return next as typeof f;
      });
      setProposed((p) => ({
        ...p,
        ...Object.fromEntries(Object.keys(patch).map((k) => [k, rationale])),
      }));
    },
  });

  const isPhase = form.problem_type === "phase_v2";
  const isDft = form.problem_type === "dft_v3";
  const isProperty = form.problem_type === "property_v3";
  const isIsing = form.problem_type === "ising_v0";
  const isAlloy = !isPhase && !isIsing;
  const hasElements = form.problem_type !== "ising_v0" && form.problem_type !== "alloy_v1";
  const elementEngine = isDft ? form.dft_engine : isProperty ? form.property_engine : "emt";
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
            elements: hasElements ? [form.element_a.trim(), form.element_b.trim()] : null,
            dft_engine: form.dft_engine as CampaignCreate["dft_engine"],
            property_engine: form.property_engine as CampaignCreate["property_engine"],
            temperature_threshold: Number(form.temperature_threshold),
            simulation_budget: Number(form.simulation_budget),
            lattice_size: Number(form.lattice_size),
            temperature_min: Number(isPhase ? form.phase_t_min : form.temperature_min),
            temperature_max: Number(isPhase ? form.phase_t_max : form.temperature_max),
            target_uncertainty:
              form.target_uncertainty === "" ? null : Number(form.target_uncertainty),
          });
        }}
      >
        <div className="grid grid-cols-1 gap-6 p-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          {/* Left: what & how */}
          <div className="flex flex-col gap-4">
            <TechnicalLabel>Objective</TechnicalLabel>
            <Field label="campaign name" {...mark("name")}>
              <Input value={form.name} onChange={(e) => set("name", e.target.value)} required />
            </Field>
            <Field label="problem" hint={info.long} {...mark("problem_type")}>
              <Select
                value={form.problem_type}
                onChange={(e) => set("problem_type", e.target.value as ProblemType)}
              >
                <option value="property_v3">Stiff &amp; stable intermetallic search</option>
                <option value="dft_v3">Formation-energy hull (EMT / DFT)</option>
                <option value="ising_v0">Ising critical region (Monte Carlo)</option>
              </Select>
            </Field>
            {hasElements && (
              <Field
                {...mark(proposed.element_a != null ? "element_a" : "element_b")}
                label="element pair A – B"
                hint={
                  elementEngine === "emt"
                    ? "EMT supports Al, Cu, Ag, Au, Ni, Pd, Pt. x is the fraction of B."
                    : elementEngine === "espresso"
                      ? "elements with a pseudopotential on disk. x is the fraction of B."
                      : "A sets the parent FCC lattice constant. x is the fraction of B."
                }
              >
                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                  <ElementSelect
                    value={form.element_a}
                    onChange={(v) => set("element_a", v)}
                    engine={elementEngine}
                    exclude={form.element_b}
                    placeholder="A"
                  />
                  <span className="text-text-muted">–</span>
                  <ElementSelect
                    value={form.element_b}
                    onChange={(v) => set("element_b", v)}
                    engine={elementEngine}
                    exclude={form.element_a}
                    placeholder="B"
                  />
                </div>
              </Field>
            )}
            <Field label="strategy" {...mark("strategy")}>
              <Select value={form.strategy} onChange={(e) => set("strategy", e.target.value)}>
                <option value="agent">agent — LLM scientist</option>
                <option value="uncertainty">uncertainty sampling</option>
                <option value="grid">
                  {isPhase
                    ? "slice round-robin + grid"
                    : isAlloy
                      ? "composition coverage"
                      : "grid coverage"}
                </option>
                <option value="random">random</option>
              </Select>
            </Field>
          </div>

          {/* Right: numbers */}
          <div className="flex flex-col gap-4">
            <TechnicalLabel>Parameters</TechnicalLabel>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
              <Field label={info.budgetLabel} {...mark("simulation_budget")}>
                <Input
                  type="number"
                  min={4}
                  max={200}
                  value={form.simulation_budget}
                  onChange={(e) => set("simulation_budget", Number(e.target.value))}
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
                {...mark("target_uncertainty")}
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
                  <Field label="lattice size L" {...mark("lattice_size")}>
                    <Input
                      type="number"
                      min={8}
                      max={64}
                      step={2}
                      value={form.lattice_size}
                      onChange={(e) => set("lattice_size", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T min" {...mark("temperature_min")}>
                    <Input
                      type="number"
                      step={0.1}
                      value={form.temperature_min}
                      onChange={(e) => set("temperature_min", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T max" {...mark("temperature_max")}>
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
                  <Field label="property engine" {...mark("property_engine")}>
                    <Select
                      value={form.property_engine}
                      onChange={(e) => set("property_engine", e.target.value)}
                    >
                      <option value="emt">EMT classical potential (fast)</option>
                      <option value="espresso">Quantum ESPRESSO (real DFT, slow)</option>
                    </Select>
                  </Field>
                  <Field label="stability threshold T (K)" {...mark("temperature_threshold")}>
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
                <Field label="energy engine" className="col-span-2" {...mark("dft_engine")}>
                  <Select
                    value={form.dft_engine}
                    onChange={(e) => set("dft_engine", e.target.value)}
                  >
                    <option value="emt">EMT classical potential (fast)</option>
                    <option value="espresso">Quantum ESPRESSO (real DFT, slow)</option>
                  </Select>
                </Field>
              )}

              {isPhase && (
                <>
                  <Field label="T min (K)" {...mark("phase_t_min")}>
                    <Input
                      type="number"
                      step={50}
                      value={form.phase_t_min}
                      onChange={(e) => set("phase_t_min", Number(e.target.value))}
                    />
                  </Field>
                  <Field label="T max (K)" {...mark("phase_t_max")}>
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
