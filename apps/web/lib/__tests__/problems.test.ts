import { describe, expect, it } from "vitest";
import { PROBLEMS, isAlloyLike, problemInfo } from "@/lib/problems";

describe("problemInfo", () => {
  it("returns the matching problem", () => {
    expect(problemInfo("phase_v2")).toBe(PROBLEMS.phase_v2);
  });
  it("falls back to ising for unknown or missing types", () => {
    expect(problemInfo(undefined)).toBe(PROBLEMS.ising_v0);
    expect(problemInfo("nope")).toBe(PROBLEMS.ising_v0);
  });
});

describe("isAlloyLike", () => {
  it("is true for alloy-family problems only", () => {
    expect(isAlloyLike("alloy_v1")).toBe(true);
    expect(isAlloyLike("property_v3")).toBe(true);
    expect(isAlloyLike("ising_v0")).toBe(false);
    expect(isAlloyLike(undefined)).toBe(false);
  });
});
