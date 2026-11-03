import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createServer } from 'vite';

const chrome = [
  process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].find((candidate) => candidate && existsSync(candidate));

test(
  'case details layout and admin visibility in browser',
  {
    skip: chrome ? false : 'Chrome unavailable; set CHROME_BIN to run browser coverage',
    timeout: 120_000,
  },
  async () => {
    const profile = await mkdtemp(path.join(tmpdir(), 'simboard-layout-'));
    const server = await createServer({
      mode: 'test',
      cacheDir: path.join(profile, 'vite-cache'),
      optimizeDeps: { entries: ['tests/fixtures/caseDetailsLayout.tsx'] },
      appType: 'custom',
      server: { host: '127.0.0.1', port: 0, watch: null },
      plugins: [
        {
          name: 'case-layout-fixture',
          configureServer(vite) {
            vite.middlewares.use('/__case-layout', async (_request, response, next) => {
              try {
                const html = await vite.transformIndexHtml(
                  '/__case-layout',
                  '<div id="root"></div><script type="module" src="/tests/fixtures/caseDetailsLayout.tsx"></script>',
                );
                response.setHeader('Content-Type', 'text/html');
                response.end(html);
              } catch (error) {
                next(error);
              }
            });
          },
        },
      ],
    });

    try {
      await server.listen();
      const address = server.httpServer.address();
      const output = await new Promise((resolve, reject) => {
        const child = spawn(chrome, [
          '--headless',
          '--enable-logging=stderr',
          '--disable-gpu',
          '--no-first-run',
          '--no-default-browser-check',
          `--user-data-dir=${profile}`,
          '--dump-dom',
          '--virtual-time-budget=30000',
          `http://127.0.0.1:${address.port}/__case-layout`,
        ]);
        let stdout = '';
        let stderr = '';
        const timer = setTimeout(() => child.kill(), 90_000);
        child.stdout.on('data', (chunk) => {
          stdout += chunk;
        });
        child.stderr.on('data', (chunk) => {
          stderr += chunk;
        });
        child.on('error', reject);
        child.on('close', (code) => {
          clearTimeout(timer);
          if (code !== 0) reject(new Error(`Chrome exited ${code}: ${stderr}`));
          else resolve(stdout + stderr);
        });
      });

      assert.equal(output.match(/<output id="test-result">([\s\S]*?)<\/output>/)?.[1], 'passed');
    } finally {
      await server.close();
      await rm(profile, { recursive: true, force: true, maxRetries: 3 });
    }
  },
);
