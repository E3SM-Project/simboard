import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig(({ mode }) => {
  // -------------------------------------------------------------------
  // Environment classification
  // -------------------------------------------------------------------
  const isLocalDev = mode === 'development';

  // -------------------------------------------------------------------
  // Load env file ONLY for local bare-metal dev
  // -------------------------------------------------------------------
  if (isLocalDev) {
    const envFile = path.resolve(__dirname, '../.envs/local/frontend.env');

    if (!fs.existsSync(envFile)) {
      throw new Error(
        `Environment file '${envFile}' does not exist. ` +
          'Create it for local dev or run in CI/production.',
      );
    }

    dotenv.config({ path: envFile });
  }

  // -------------------------------------------------------------------
  // Filter ONLY variables that start with VITE_
  // -------------------------------------------------------------------
  const viteEnv: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('VITE_') && value !== undefined) {
      viteEnv[key] = value;
    }
  }

  // -------------------------------------------------------------------
  // Certificate path setup (local dev only)
  // -------------------------------------------------------------------
  const keyPath = viteEnv.VITE_SSL_KEY ?? '../certs/local.key';
  const certPath = viteEnv.VITE_SSL_CERT ?? '../certs/local.crt';

  const resolveIfExists = (p: string) => {
    const full = path.resolve(__dirname, p);
    return fs.existsSync(full) ? full : null;
  };

  const finalKey = resolveIfExists(keyPath);
  const finalCert = resolveIfExists(certPath);

  // -------------------------------------------------------------------
  // Local-only safety check
  // -------------------------------------------------------------------
  if (isLocalDev && (!finalKey || !finalCert)) {
    throw new Error('❌ Local SSL certificates missing for Vite dev server.');
  }

  // -------------------------------------------------------------------
  // Final Vite config
  // -------------------------------------------------------------------
  return {
    plugins: [react(), tsconfigPaths()],

    // Expose ONLY VITE_* variables
    define: {
      ...Object.fromEntries(
        Object.entries(viteEnv).map(([key, value]) => [
          `import.meta.env.${key}`,
          JSON.stringify(value),
        ]),
      ),
    },

    server: {
      host: '127.0.0.1',
      port: 5173,
      https:
        isLocalDev && finalKey && finalCert
          ? {
              key: fs.readFileSync(finalKey),
              cert: fs.readFileSync(finalCert),
            }
          : undefined,
    },
  };
});
