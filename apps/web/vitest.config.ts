import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname) } },
  test: { include: ["**/*.test.{ts,tsx}"], exclude: ["node_modules", ".next"] },
});
