import react from '@vitejs/plugin-react';
import fs from "fs";
import path from "path";
import { defineConfig, loadEnv } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

// ---------------------------------------------------------------------
// Determine application environment (APP_ENV) mapped to .envs/<env>
// Defaults to "dev" (replacing old "local")
// ---------------------------------------------------------------------
const appEnv = process.env.APP_ENV ?? "dev";

// ---------------------------------------------------------------------
// Load environment variables from .envs/<env>/frontend.env
// IMPORTANT: We DO NOT pass `appEnv` as the Vite mode, because
// Vite modes can ONLY be: development, production, test
// ---------------------------------------------------------------------
const envDir = path.resolve(__dirname, `.envs/${appEnv}`);
// rawEnv forced to "development" for local dev server
const rawEnv = loadEnv("development", envDir, "");

// ---------------------------------------------------------------------
// Filter ONLY variables that start with VITE_
// ---------------------------------------------------------------------
const viteEnv: Record<string, string> = {};
for (const key in rawEnv) {
  if (key.startsWith("VITE_")) {
    viteEnv[key] = rawEnv[key];
  }
}

// ---------------------------------------------------------------------
// Certificate path setup
// ---------------------------------------------------------------------
const keyPath = viteEnv.VITE_SSL_KEY ?? "../certs/dev.key";
const certPath = viteEnv.VITE_SSL_CERT ?? "../certs/dev.crt";

// Resolve relative files based on THIS directory, not CWD
const resolveIfExists = (p: string) => {
  const full = path.resolve(__dirname, p);

  return fs.existsSync(full) ? full : null;
};

const finalKey = resolveIfExists(keyPath);
const finalCert = resolveIfExists(certPath);

// ---------------------------------------------------------------------
// Optional safety checks
// ---------------------------------------------------------------------

// Warn if HTTPS cannot be enabled locally
if (!finalKey || !finalCert) {
  console.warn("⚠️  HTTPS disabled: missing dev.key or dev.crt");
}

// In CI or prod-like environments, fail if certs are missing
if (process.env.CI && (!finalKey || !finalCert)) {
  throw new Error("❌ SSL certificates missing in CI environment.");
}

// ---------------------------------------------------------------------
// Final Vite config
// ---------------------------------------------------------------------
export default defineConfig({
  plugins: [react(), tsconfigPaths()],

  // Expose ONLY VITE_* variables
  define: {
    ...Object.fromEntries(
      Object.entries(viteEnv).map(([key, value]) => [
        `import.meta.env.${key}`,
        JSON.stringify(value),
      ])
    ),
  },

  server: {
    host: "127.0.0.1",
    port: 5173,

    https:
      finalKey && finalCert
        ? {
            key: fs.readFileSync(finalKey),
            cert: fs.readFileSync(finalCert),
          }
        : undefined,
  },
});
