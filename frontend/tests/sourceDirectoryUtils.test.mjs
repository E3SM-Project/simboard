import assert from 'node:assert/strict';
import test from 'node:test';

import { preferredCaseDirectoryPaths } from '../src/features/catalog/sourceDirectoryUtils.ts';

const directory = (kind, path) => ({ id: `${kind}:${path}`, kind, path });

test('missing and empty mappings have no displayed paths', () => {
  assert.deepEqual(preferredCaseDirectoryPaths(), []);
  assert.deepEqual(preferredCaseDirectoryPaths([]), []);
});

test('a single staging path is displayed', () => {
  assert.deepEqual(preferredCaseDirectoryPaths([directory('staging', '/staging/case')]), [
    '/staging/case',
  ]);
});

test('all staging paths are sorted and deduplicated without archive mappings', () => {
  const mappings = [
    directory('staging', '/staging/b'),
    directory('staging', '/staging/a'),
    directory('staging', '/staging/b'),
  ];
  assert.deepEqual(preferredCaseDirectoryPaths(mappings), ['/staging/a', '/staging/b']);
  assert.equal(mappings[0].path, '/staging/b');
});

test('all archive paths take precedence over staging regardless of input order', () => {
  const mappings = [
    directory('staging', '/staging/case'),
    directory('archive', '/archive/day-2/case'),
    directory('archive', '/archive/day-1/case'),
    directory('archive', '/archive/day-2/case'),
  ];
  const expected = ['/archive/day-1/case', '/archive/day-2/case'];
  assert.deepEqual(preferredCaseDirectoryPaths(mappings), expected);
  assert.deepEqual(preferredCaseDirectoryPaths(mappings.toReversed()), expected);
});

test('a single archive hides staging paths', () => {
  assert.deepEqual(
    preferredCaseDirectoryPaths([
      directory('staging', '/staging/case'),
      directory('archive', '/archive/case'),
    ]),
    ['/archive/case'],
  );
});
