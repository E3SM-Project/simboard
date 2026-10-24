import assert from 'node:assert/strict';
import test from 'node:test';

import { repositoryBrowserUrl } from '../src/lib/catalog/repository.ts';

test('HTTP(S) sources derive valid browser links', () => {
  assert.equal(
    repositoryBrowserUrl('https://github.com/owner/repo.git'),
    'https://github.com/owner/repo.git',
  );
  assert.equal(repositoryBrowserUrl('http://example.com'), 'http://example.com/');
});

test('recognized GitHub SSH sources derive HTTPS links', () => {
  for (const source of ['git@github.com:owner/repo.git', 'ssh://git@github.com/owner/repo.git']) {
    assert.equal(repositoryBrowserUrl(source), 'https://github.com/owner/repo.git');
  }
});

test('local paths, unsupported remotes, and unsafe values are not links', () => {
  for (const source of [
    null,
    undefined,
    '',
    '/global/homes/user/E3SM',
    '../E3SM',
    'E3SM',
    'file:///local/repo',
    'git://github.com/owner/repo',
    'git@gitlab.com:owner/repo',
    'ssh://git@github.com:2222/owner/repo',
    'git@github.com:owner/../repo',
    'git@github.com:owner/repo?query',
    'git@github.com:owner/repo#fragment',
    'javascript:alert(1)',
    'https://',
    'https://user:secret@github.com/owner/repo',
    ' https://example.com',
    'https://example.com\n',
    'https://example.com\\evil',
  ]) {
    assert.equal(repositoryBrowserUrl(source), null, String(source));
  }
});
