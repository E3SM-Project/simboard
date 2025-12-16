import react from '@vitejs/plugin-react';
import fs from "fs";
import path from "path";
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

// ---------------------------------------------
// Certificate path setup
// ---------------------------------------------
const keyPath = process.env.VITE_SSL_KEY ?? "../certs/dev.key";
const certPath = process.env.VITE_SSL_CERT ?? "../certs/dev.crt";

// Resolve relative paths based on the location of this config file,
// not the working directory (important for Docker/PNPM/WSL setups)
const resolveIfExists = (p: string) => {
  const full = path.resolve(__dirname, p);
  return fs.existsSync(full) ? full : null;
};

const finalKey = resolveIfExists(keyPath);
const finalCert = resolveIfExists(certPath);

// ---------------------------------------------
// Optional safety checks
// ---------------------------------------------

// Warn in local development if HTTPS will not be enabled
if (!finalKey || !finalCert) {
  console.warn("⚠️  HTTPS disabled: missing dev.key or dev.crt");
}

// In CI/staging/prod you may require HTTPS and fail fast
if (process.env.CI && (!finalKey || !finalCert)) {
  throw new Error("❌ SSL certificates missing in CI environment.");
}

// ---------------------------------------------
// Final Vite config
// ---------------------------------------------
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  server: {
    host: "127.0.0.1",
    port: 5173,

    // Enable HTTPS only if certs are available.
    // Otherwise Vite defaults to HTTP.
    https:
      finalKey && finalCert
        ? {
            key: fs.readFileSync(finalKey),
            cert: fs.readFileSync(finalCert),
          }
        : undefined,
  },
});
