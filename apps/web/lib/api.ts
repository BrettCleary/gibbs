import { createApiClient } from "@alloylab/api-client";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createApiClient(API_URL);
