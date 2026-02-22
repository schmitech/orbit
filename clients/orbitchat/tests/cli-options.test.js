/**
 * Regression tests for CLI option handling.
 *
 * Verifies --help/--version behavior for the direct CLI and
 * orbitchat.sh passthrough compatibility mode.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BIN = path.join(ROOT, 'bin', 'orbitchat.js');
const DAEMON = path.join(ROOT, 'orbitchat.sh');
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));

function runNode(args) {
  return spawnSync(process.execPath, args, {
    cwd: ROOT,
    encoding: 'utf8',
    env: { ...process.env },
  });
}

function runDaemon(args) {
  return spawnSync(DAEMON, args, {
    cwd: ROOT,
    encoding: 'utf8',
    env: { ...process.env },
  });
}

describe('CLI options', () => {
  it('prints version and exits 0 for direct CLI', () => {
    const result = runNode([BIN, '--version']);
    assert.equal(result.status, 0);
    assert.equal(result.stdout.trim(), pkg.version);
  });

  it('prints help and exits 0 for direct CLI', () => {
    const result = runNode([BIN, '--help']);
    assert.equal(result.status, 0);
    assert.match(result.stdout, /orbitchat \[options\]/);
    assert.match(result.stdout, /--version, -v/);
  });

  it('passes through to bin/orbitchat.js for --version', () => {
    const result = runDaemon(['bin/orbitchat.js', '--version']);
    assert.equal(result.status, 0);
    assert.equal(result.stdout.trim(), pkg.version);
  });

  it('passes through to bin/orbitchat.js for --help', () => {
    const result = runDaemon(['bin/orbitchat.js', '--help']);
    assert.equal(result.status, 0);
    assert.match(result.stdout, /orbitchat \[options\]/);
    assert.match(result.stdout, /--help, -h/);
  });
});
