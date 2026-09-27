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
    // Next, depo kökündeki lockfile yüzünden kökü yanlış çıkarınca frontend/frontend/.next yazabiliyor.
    "**/.next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Dışarıdan alınan Claude Code skill'leri ve üretilen dosyalar.
    ".claude/**",
    "lib/api/schema.d.ts",
    "public/maplibre/**",
    "playwright-report/**",
    "test-results/**",
  ]),
]);

export default eslintConfig;
