import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { URL } from 'node:url';

const nginxConf = readFileSync(new URL('../nginx.conf', import.meta.url), 'utf8');

const imgSources = () => {
  const csp = nginxConf.match(/Content-Security-Policy "([^"]+)"/)?.[1] ?? '';
  const directive = csp.split(';').find((part) => part.trim().startsWith('img-src'));
  return directive?.trim().split(/\s+/).slice(1) ?? [];
};

test('CSP allows diagnostics plot images from the published archives', () => {
  const sources = imgSources();

  assert.ok(sources.includes("'self'"));
  assert.ok(sources.includes('https://web.lcrc.anl.gov'));
  assert.ok(sources.includes('https://portal.nersc.gov'));
});
