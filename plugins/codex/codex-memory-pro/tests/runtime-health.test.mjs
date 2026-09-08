import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { MemoryRetriever } from "../dist/retriever.js";
import { llmJsonAnalyze } from "../dist/auto-capture.js";

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return true;
    await wait(25);
  }
  return false;
}

test("MCP stdio 关闭后进程退出，不被 Dream timer 挂住", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-eof-test-"));
  const child = spawn(process.execPath, ["dist/mcp-server.js"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      HOME: sandbox,
      MEMORY_PRO_HOME: join(sandbox, ".codex", "memory-pro"),
      MEMORY_DB_PATH: join(sandbox, "lancedb"),
      EMBEDDING_API_KEY: "",
      CAPTURE_API_KEY: "",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  let stderr = "";
  child.stderr.on("data", chunk => { stderr += String(chunk); });

  try {
    assert.equal(await waitFor(() => stderr.includes("MCP Server")), true, stderr);
    child.stdin.end();
    assert.equal(await waitFor(() => child.exitCode !== null, 1500), true, "stdin EOF 后进程仍存活");
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    await waitFor(() => child.exitCode !== null, 1500);
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("Codex 旁路产物遵循 MEMORY_PRO_HOME，不写入 .claude", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-path-test-"));
  const probe = `
    import { existsSync } from "node:fs";
    import { join } from "node:path";
    const { refreshMemoryAtlas } = await import("./dist/memory-atlas.js");
    await refreshMemoryAtlas({ listAll: async () => [], version: async () => 1 });
    const configured = existsSync(join(process.env.MEMORY_PRO_HOME, "memory-atlas.json"));
    const legacy = existsSync(join(process.env.HOME, ".claude", "memory-pro", "memory-atlas.json"));
    process.stdout.write(JSON.stringify({ configured, legacy }));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", probe], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      HOME: sandbox,
      MEMORY_PRO_HOME: join(sandbox, ".codex", "memory-pro"),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  child.stdout.on("data", chunk => { stdout += String(chunk); });
  child.stderr.on("data", chunk => { stderr += String(chunk); });
  try {
    assert.equal(await waitFor(() => child.exitCode !== null), true, stderr);
    assert.equal(child.exitCode, 0, stderr);
    assert.deepEqual(JSON.parse(stdout), { configured: true, legacy: false });
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("仅配置 MEMORY_DB_PATH 时旁路产物写到数据库同级目录", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-db-path-test-"));
  const dbPath = join(sandbox, "custom-home", "lancedb");
  const probe = `
    import { existsSync } from "node:fs";
    import { dirname, join } from "node:path";
    const { refreshMemoryAtlas } = await import("./dist/memory-atlas.js");
    await refreshMemoryAtlas({ listAll: async () => [], version: async () => 1 });
    process.stdout.write(JSON.stringify({
      configured: existsSync(join(dirname(process.env.MEMORY_DB_PATH), "memory-atlas.json")),
      legacy: existsSync(join(process.env.HOME, ".claude", "memory-pro", "memory-atlas.json")),
    }));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", probe], {
    cwd: process.cwd(),
    env: { ...process.env, HOME: sandbox, MEMORY_PRO_HOME: "", MEMORY_DB_PATH: dbPath },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", chunk => { stdout += String(chunk); });
  child.stderr.on("data", chunk => { stderr += String(chunk); });
  try {
    assert.equal(await waitFor(() => child.exitCode !== null), true, stderr);
    assert.equal(child.exitCode, 0, stderr);
    assert.deepEqual(JSON.parse(stdout), { configured: true, legacy: false });
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("Atlas 按 LanceDB version 自动刷新", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-atlas-version-test-"));
  const probe = `
    const { refreshMemoryAtlas, ensureMemoryAtlasFresh } = await import("./dist/memory-atlas.js");
    let version = 1;
    let entries = [];
    const store = { version: async () => version, listAll: async () => entries };
    await refreshMemoryAtlas(store);
    version = 2;
    entries = [{
      id: "fresh-1", text: "Atlas 自动刷新有效记忆", vector: [1], importance: 0.9,
      category: "fact", scope: "test", timestamp: Date.now(), metadata: "{}",
      recallCount: 0, lastRecallAt: 0,
    }];
    const atlas = await ensureMemoryAtlasFresh(store);
    process.stdout.write(JSON.stringify({ storeVersion: atlas.storeVersion, totalIndexed: atlas.totalIndexed }));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", probe], {
    cwd: process.cwd(),
    env: { ...process.env, HOME: sandbox, MEMORY_PRO_HOME: join(sandbox, "memory-pro") },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", chunk => { stdout += String(chunk); });
  child.stderr.on("data", chunk => { stderr += String(chunk); });
  try {
    assert.equal(await waitFor(() => child.exitCode !== null), true, stderr);
    assert.equal(child.exitCode, 0, stderr);
    assert.deepEqual(JSON.parse(stdout), { storeVersion: 2, totalIndexed: 1 });
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("Dream 周期文件锁阻止多个 MCP 进程同时维护", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-dream-lock-test-"));
  const probe = `
    const { withDreamCycleLock } = await import("./dist/dream-manager.js");
    const first = withDreamCycleLock(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
      return "ran";
    });
    const second = withDreamCycleLock(async () => "duplicate");
    process.stdout.write(JSON.stringify(await Promise.all([first, second])));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", probe], {
    cwd: process.cwd(),
    env: { ...process.env, HOME: sandbox, MEMORY_PRO_HOME: join(sandbox, "memory-pro") },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", chunk => { stdout += String(chunk); });
  child.stderr.on("data", chunk => { stderr += String(chunk); });
  try {
    assert.equal(await waitFor(() => child.exitCode !== null), true, stderr);
    assert.equal(child.exitCode, 0, stderr);
    assert.deepEqual(JSON.parse(stdout), ["ran", null]);
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("Dream 无到期阶段时启动恢复不重复改写状态文件", async () => {
  const sandbox = mkdtempSync(join(tmpdir(), "memory-pro-dream-recovery-test-"));
  const probe = `
    import { mkdirSync, statSync, writeFileSync } from "node:fs";
    import { join } from "node:path";
    mkdirSync(process.env.MEMORY_PRO_HOME, { recursive: true });
    const stateFile = join(process.env.MEMORY_PRO_HOME, "dream-last-run.json");
    const now = new Date().toISOString();
    writeFileSync(stateFile, JSON.stringify({ light: now, deep: now, rem: now, maintenance: now }));
    const before = statSync(stateFile).mtimeMs;
    await new Promise(resolve => setTimeout(resolve, 30));
    const { recoverMissedPhases } = await import("./dist/dream-manager.js");
    await recoverMissedPhases({ getRecallCandidates: async () => [] });
    const after = statSync(stateFile).mtimeMs;
    process.stdout.write(JSON.stringify({ unchanged: before === after }));
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", probe], {
    cwd: process.cwd(),
    env: { ...process.env, HOME: sandbox, MEMORY_PRO_HOME: join(sandbox, "memory-pro") },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", chunk => { stdout += String(chunk); });
  child.stderr.on("data", chunk => { stderr += String(chunk); });
  try {
    assert.equal(await waitFor(() => child.exitCode !== null), true, stderr);
    assert.equal(child.exitCode, 0, stderr);
    assert.deepEqual(JSON.parse(stdout), { unchanged: true });
  } finally {
    if (child.exitCode === null) child.kill("SIGTERM");
    rmSync(sandbox, { recursive: true, force: true });
  }
});

test("query embedding 失败时使用本地 BM25 结果", async () => {
  const entry = {
    id: "memory-1",
    text: "记忆插件路径修复",
    vector: [1, 0],
    importance: 0.8,
    category: "fact",
    scope: "test",
    timestamp: Date.now(),
    metadata: "{}",
    recallCount: 0,
    lastRecallAt: 0,
  };
  const store = {
    hasFtsSupport: true,
    bm25Search: async () => [{ entry, score: 0.9 }],
    vectorSearch: async () => { throw new Error("vector search should not run"); },
  };
  const embedder = {
    embedQuery: async () => { throw new Error("402 status code (no body)"); },
  };

  const retriever = new MemoryRetriever(store, embedder, { mode: "hybrid", minScore: 0.1 });
  const results = await retriever.retrieve({ query: "路径修复", limit: 5 });

  assert.equal(results.length, 1);
  assert.equal(results[0].entry.id, entry.id);
  assert.equal(Boolean(results[0].sources.bm25), true);
  assert.equal(Boolean(results[0].sources.vector), false);
});

test("捕获分类模型关闭深度思考，避免 JSON 输出预算被推理耗尽", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody;
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(String(init?.body || "{}"));
    return new Response(JSON.stringify({
      choices: [{ finish_reason: "stop", message: { content: '{"ok":true}' } }],
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const result = await llmJsonAnalyze({
      apiKey: "test-key",
      baseURL: "https://example.invalid/v1",
      model: "glm-4.5-flash",
      systemPrompt: "只输出 JSON",
      userPrompt: "输出 ok",
      maxTokens: 64,
    });
    assert.deepEqual(requestBody.thinking, { type: "disabled" });
    assert.deepEqual(result, { ok: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
