import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { verifyCreatedXMind } from '../create_xmind.mjs';


const scriptsDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const createScript = join(scriptsDir, 'create_xmind.mjs');
const readScript = join(scriptsDir, 'read_xmind.mjs');

function run(script, args = [], input) {
    return spawnSync(process.execPath, [script, ...args], {
        input,
        encoding: 'utf-8',
    });
}

function request(path) {
    return {
        path,
        sheets: [{
            title: 'Synthetic',
            rootTopic: {
                title: 'Root',
                children: [{ title: 'Input' }, { title: 'Output' }],
            },
            relationships: [{
                sourceTitle: 'Input',
                targetTitle: 'Output',
                title: 'trace',
            }],
        }],
    };
}

test('file input creates, verifies, and reads the written XMind', () => {
    const dir = mkdtempSync(join(tmpdir(), 'xmind-cli-'));
    const output = join(dir, 'file-input.xmind');
    const createInput = join(dir, 'create.json');
    const readInput = join(dir, 'read.json');
    writeFileSync(createInput, JSON.stringify(request(output)));
    writeFileSync(readInput, JSON.stringify({ action: 'read', path: output }));

    const created = run(createScript, ['--input', createInput]);
    assert.equal(created.status, 0, created.stderr);
    assert.match(created.stdout, /^Created /m);
    const evidence = JSON.parse(created.stdout.match(/^Verified: (.+)$/m)[1]);
    assert.deepEqual(
        {
            format: evidence.format,
            sheetCount: evidence.sheetCount,
            topicCount: evidence.topicCount,
            relationshipCount: evidence.relationshipCount,
        },
        { format: 'zen', sheetCount: 1, topicCount: 3, relationshipCount: 1 },
    );

    const read = run(readScript, ['--input', readInput]);
    assert.equal(read.status, 0, read.stderr);
    const parsed = JSON.parse(read.stdout);
    assert.equal(parsed[0].title, 'Root');
    assert.equal(parsed[0].relationships[0].title, 'trace');
});

test('stdin remains compatible for create and read', () => {
    const dir = mkdtempSync(join(tmpdir(), 'xmind-stdin-'));
    const output = join(dir, 'stdin.xmind');
    const legacyRequest = { ...request(output), format: 'legacy' };
    const created = run(createScript, [], JSON.stringify(legacyRequest));
    assert.equal(created.status, 0, created.stderr);
    assert.match(created.stdout, /^Verified: /m);
    assert.equal(
        JSON.parse(created.stdout.match(/^Verified: (.+)$/m)[1]).format,
        'legacy',
    );

    const read = run(readScript, [], JSON.stringify({ action: 'read', path: output }));
    assert.equal(read.status, 0, read.stderr);
    assert.equal(JSON.parse(read.stdout)[0].title, 'Root');
});

test('bad create input and corrupt XMind fail without success output', () => {
    const dir = mkdtempSync(join(tmpdir(), 'xmind-failure-'));
    const badCreate = join(dir, 'bad-create.json');
    const corrupt = join(dir, 'corrupt.xmind');
    const badRead = join(dir, 'bad-read.json');
    writeFileSync(badCreate, '{"path":');
    writeFileSync(corrupt, 'not an xmind archive');
    writeFileSync(badRead, JSON.stringify({ action: 'read', path: corrupt }));

    const create = run(createScript, ['--input', badCreate]);
    assert.notEqual(create.status, 0);
    assert.doesNotMatch(create.stdout, /^(Created|Verified):?/m);

    const read = run(readScript, ['--input', badRead]);
    assert.notEqual(read.status, 0);
    assert.equal(read.stdout, '');
    assert.match(read.stderr, /^Error: Invalid ZIP:/m);
    assert.throws(
        () => verifyCreatedXMind(corrupt, request(corrupt), 'zen'),
        /Invalid ZIP:/,
    );
});
