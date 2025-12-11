import react from '@vitejs/plugin-react';
import fs from "fs";
import { defineConfig } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

const key = process.env.VITE_SSL_KEY || "../certs/dev.key";
const cert = process.env.VITE_SSL_CERT || "../certs/dev.crt";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    https: {
      key: fs.readFileSync(key),
      cert: fs.readFileSync(cert),
    },
  },
});
