import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url))
});

const nextVitals = {
  extends: ["next/core-web-vitals"]
};

const config = [
  {
    ignores: [".next/**", "node_modules/**"]
  },
  ...compat.config(nextVitals)
];

export default config;
