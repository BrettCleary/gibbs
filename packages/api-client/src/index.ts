import createClient from "openapi-fetch";
import type { paths, components } from "./schema";

export type { paths, components };

export type Campaign = components["schemas"]["CampaignRead"];
export type CampaignCreate = components["schemas"]["CampaignCreate"];
export type Calculation = components["schemas"]["CalculationRead"];
export type SurrogateModel = components["schemas"]["SurrogateModelRead"];
export type AgentEvent = components["schemas"]["AgentEventRead"];
export type SurrogateView = components["schemas"]["CampaignSurrogateView"];
export type BenchmarkRun = components["schemas"]["BenchmarkRead"];
export type BenchmarkCreate = components["schemas"]["BenchmarkCreate"];
export type StructureRead = components["schemas"]["StructureRead"];
export type HullView = components["schemas"]["AlloyHullView"];
export type HullPoint = components["schemas"]["HullPoint"];
export type PhaseDiagramView = components["schemas"]["PhaseDiagramView"];
export type PhaseSliceView = components["schemas"]["PhaseSliceView"];

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;
