#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const scriptDir = path.dirname(new URL(import.meta.url).pathname);
const pluginRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(pluginRoot, "../..");
const codexConfig = path.join(os.homedir(), ".codex", "config.toml");
const codexAgentsDir = path.join(os.homedir(), ".codex", "agents");

function tomlString(value) {
  return JSON.stringify(String(value));
}

let config = fs.existsSync(codexConfig) ? fs.readFileSync(codexConfig, "utf8") : "";
const block = `

[marketplaces.codex-multi-agent]
source_type = "local"
source = ${tomlString(repoRoot)}

[plugins."codex-multi-agent@codex-multi-agent"]
enabled = true
`;

if (!config.includes("[marketplaces.codex-multi-agent]")) {
  fs.mkdirSync(path.dirname(codexConfig), { recursive: true });
  fs.writeFileSync(codexConfig, config.trimEnd() + block + "\n");
  console.log(`Installed Codex Multi-Agent into ${codexConfig}`);
} else {
  console.log("Codex Multi-Agent marketplace already exists in config.toml; leaving existing config unchanged.");
}

fs.mkdirSync(codexAgentsDir, { recursive: true });
for (const name of ["supervisor.toml", "recovery-agent.toml"]) {
  const src = path.join(pluginRoot, "agents", name);
  const dest = path.join(codexAgentsDir, name);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest);
    console.log(`Synced agent ${name} -> ${dest}`);
  }
}
