#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const scriptDir = path.dirname(new URL(import.meta.url).pathname);
const pluginRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(pluginRoot, "../..");
const codexConfig = path.join(os.homedir(), ".codex", "config.toml");
const claudeMcp = path.join(os.homedir(), ".claude", ".mcp.json");

function readClaudeEnv() {
  try {
    const parsed = JSON.parse(fs.readFileSync(claudeMcp, "utf8"));
    return parsed.mcpServers?.["claude-memory-pro"]?.env ?? {};
  } catch {
    return {};
  }
}

function tomlString(value) {
  return JSON.stringify(String(value));
}

const claudeEnv = readClaudeEnv();
const env = {
  EMBEDDING_API_KEY: process.env.EMBEDDING_API_KEY || claudeEnv.EMBEDDING_API_KEY || "",
  EMBEDDING_BASE_URL: process.env.EMBEDDING_BASE_URL || claudeEnv.EMBEDDING_BASE_URL || "https://api.siliconflow.cn/v1",
  EMBEDDING_MODEL: process.env.EMBEDDING_MODEL || claudeEnv.EMBEDDING_MODEL || "BAAI/bge-m3",
  MEMORY_DB_PATH: process.env.MEMORY_DB_PATH || path.join(os.homedir(), ".codex", "memory-pro", "lancedb"),
};

if (!env.EMBEDDING_API_KEY) {
  console.error("Missing EMBEDDING_API_KEY. Set it in the environment or configure ~/.claude/.mcp.json first.");
  process.exit(1);
}

const install = spawnSync("npm", ["install", "--legacy-peer-deps"], { cwd: pluginRoot, stdio: "inherit" });
if (install.status !== 0) process.exit(install.status ?? 1);

const build = spawnSync("npm", ["run", "build"], { cwd: pluginRoot, stdio: "inherit" });
if (build.status !== 0) process.exit(build.status ?? 1);

let config = fs.existsSync(codexConfig) ? fs.readFileSync(codexConfig, "utf8") : "";
const block = `

[marketplaces.codex-memory-pro]
source_type = "local"
source = ${tomlString(repoRoot)}

[plugins."codex-memory-pro@codex-memory-pro"]
enabled = true

[mcp_servers.codex-memory-pro]
type = "stdio"
command = "node"
args = [${tomlString(path.join(pluginRoot, "dist", "mcp-server.js"))}]

[mcp_servers.codex-memory-pro.env]
EMBEDDING_API_KEY = ${tomlString(env.EMBEDDING_API_KEY)}
EMBEDDING_BASE_URL = ${tomlString(env.EMBEDDING_BASE_URL)}
EMBEDDING_MODEL = ${tomlString(env.EMBEDDING_MODEL)}
MEMORY_DB_PATH = ${tomlString(env.MEMORY_DB_PATH)}
`;

if (!config.includes("[marketplaces.codex-memory-pro]")) {
  fs.mkdirSync(path.dirname(codexConfig), { recursive: true });
  fs.writeFileSync(codexConfig, config.trimEnd() + block + "\n");
  console.log(`Installed Codex Memory Pro into ${codexConfig}`);
} else {
  console.log("Codex Memory Pro marketplace already exists in config.toml; leaving existing config unchanged.");
}
