import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import process from 'node:process';
import test from 'node:test';
import { clearTimeout, setTimeout } from 'node:timers';
import { URL } from 'node:url';

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
            vite.middlewares.use('/__case-layout', async (request, response, next) => {
              try {
                const url = new URL(request.url, 'http://localhost');
                const width = Number(url.searchParams.get('width'));
                const html =
                  url.pathname === '/fixture'
                    ? await vite.transformIndexHtml(
                        '/__case-layout',
                        '<div id="root"></div><script type="module" src="/tests/fixtures/caseDetailsLayout.tsx"></script>',
                      )
                    : `<!doctype html><iframe width="${width}" height="1000" style="border:0" src="/__case-layout/fixture?width=${width}"></iframe>`;
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
      for (const width of [1280, 390]) {
        const output = await new Promise((resolve, reject) => {
          const child = spawn(chrome, [
            '--headless',
            '--enable-logging=stderr',
            '--disable-gpu',
            `--window-size=${width},1000`,
            '--no-first-run',
            '--no-default-browser-check',
            `--user-data-dir=${profile}`,
            '--dump-dom',
            '--virtual-time-budget=30000',
            `http://127.0.0.1:${address.port}/__case-layout?width=${width}`,
          ]);
          let stdout = '';
          let stderr = '';
          let timedOut = false;
          const timer = setTimeout(() => {
            timedOut = true;
            child.kill();
          }, 90_000);
          child.stdout.on('data', (chunk) => {
            stdout += chunk;
          });
          child.stderr.on('data', (chunk) => {
            stderr += chunk;
          });
          child.on('error', (error) => {
            clearTimeout(timer);
            reject(error);
          });
          child.on('close', (code) => {
            clearTimeout(timer);
            if (timedOut) reject(new Error(`Chrome timed out after 90 seconds: ${stderr}`));
            else if (code !== 0) reject(new Error(`Chrome exited ${code}: ${stderr}`));
            else resolve({ stdout, stderr });
          });
        });

        assert.equal(
          output.stdout.match(/<output id="test-result">([\s\S]*?)<\/output>/)?.[1],
          'passed',
          `Viewport ${width}: ${output.stderr}`,
        );
      }
    } finally {
      await server.close();
      await rm(profile, { recursive: true, force: true, maxRetries: 3 });
    }
  },
);
