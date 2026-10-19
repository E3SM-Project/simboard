import assert from 'node:assert/strict';
import test from 'node:test';

import {
  filterSourceDirectoryPaths,
  preferredCaseDirectoryPaths,
} from '../src/features/catalog/sourceDirectoryUtils.ts';

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

test('executions sharing one staging directory produce one preferred path', () => {
  assert.deepEqual(
    preferredCaseDirectoryPaths([
      { ...directory('staging', '/staging/case'), id: 'execution-1' },
      { ...directory('staging', '/staging/case'), id: 'execution-2' },
    ]),
    ['/staging/case'],
  );
});

test('executions sharing one archive directory produce one preferred path despite staging paths', () => {
  assert.deepEqual(
    preferredCaseDirectoryPaths([
      directory('staging', '/staging/execution-1'),
      directory('staging', '/staging/execution-2'),
      { ...directory('archive', '/archive/case'), id: 'execution-1' },
      { ...directory('archive', '/archive/case'), id: 'execution-2' },
    ]),
    ['/archive/case'],
  );
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

test('directory filtering matches full paths without changing values or order', () => {
  const paths = ['/Archive/Day-1/Case', '/archive/day-2/case', '/archive/day-3/other'];
  assert.deepEqual(filterSourceDirectoryPaths(paths, '  DAY-1/case  '), [paths[0]]);
  assert.deepEqual(filterSourceDirectoryPaths(paths, 'CASE'), paths.slice(0, 2));
  assert.deepEqual(paths, ['/Archive/Day-1/Case', '/archive/day-2/case', '/archive/day-3/other']);
});

test('empty filters show all paths and unmatched filters show none', () => {
  const paths = ['/archive/a', '/archive/b'];
  assert.deepEqual(filterSourceDirectoryPaths(paths, ''), paths);
  assert.deepEqual(filterSourceDirectoryPaths(paths, '   '), paths);
  assert.deepEqual(filterSourceDirectoryPaths(paths, 'missing'), []);
  assert.deepEqual(filterSourceDirectoryPaths([], 'archive'), []);
});
