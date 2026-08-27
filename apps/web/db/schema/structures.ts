import { doublePrecision, index, integer, jsonb, varchar } from "drizzle-orm/pg-core";
import { createdAt, id } from "./_helpers";
import { science } from "./schemas";
import { campaigns } from "./campaigns";

/** A candidate atomic configuration: 2D lattice tile (V1) or 3D crystal (icet/DFT). */
export const structures = science
  .table(
    "structures",
    {
      id: id(),
      campaignId: varchar("campaign_id", { length: 32 })
        .notNull()
        .references(() => campaigns.id),
      label: varchar("label", { length: 50 }).notNull(),
      chemicalFormula: varchar("chemical_formula", { length: 100 }).notNull().default(""),
      /** x_B — fraction of the second species. */
      composition: doublePrecision("composition").notNull(),
      nSites: integer("n_sites").notNull(),
      /** 2D tile problems: rows of ±1 occupations. */
      occupations: jsonb("occupations").$type<number[][]>().notNull().default([]),
      shape: jsonb("shape").$type<number[]>().notNull().default([]),
      /** Cluster-expansion design row (correlation features or icet cluster vector). */
      features: jsonb("features").$type<number[]>().notNull().default([]),
      /** 3D problems: lattice vectors, cartesian positions, atomic numbers. */
      lattice: jsonb("lattice").$type<number[][]>(),
      positions: jsonb("positions").$type<number[][]>(),
      atomicNumbers: jsonb("atomic_numbers").$type<number[]>(),
      extra: jsonb("extra").$type<Record<string, unknown>>(),
      createdAt: createdAt(),
    },
    (t) => [
      index("ix_structures_campaign_id").on(t.campaignId),
      index("ix_structures_label").on(t.label),
    ],
  )
  .enableRLS();

export type Structure = typeof structures.$inferSelect;
export type NewStructure = typeof structures.$inferInsert;
