import nextConfig from "eslint-config-next";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextConfig,
  ...nextTs,
  { ignores: [".next/**", "node_modules/**", "supabase/**"] },
  {
    rules: {
      // Pre-existing pattern in the dashboards; downgrade until they are refactored.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
