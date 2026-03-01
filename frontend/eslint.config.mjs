import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  // TanStack Table's useReactTable returns functions that React Compiler
  // cannot auto-memoize. The compiler already skips these components
  // automatically; this rule is informational only.
  {
    files: ["src/components/**/*.tsx"],
    rules: {
      "react-hooks/incompatible-library": "off",
    },
  },
]);

export default eslintConfig;
