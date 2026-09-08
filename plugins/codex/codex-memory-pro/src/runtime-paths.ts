import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';

function expandUserPath(value: string): string {
  const trimmed = value.trim();
  if (trimmed === '~') return homedir();
  if (trimmed.startsWith('~/')) return join(homedir(), trimmed.slice(2));
  return isAbsolute(trimmed) ? trimmed : resolve(trimmed);
}

export function getMemoryProHome(): string {
  if (process.env.MEMORY_PRO_HOME) return expandUserPath(process.env.MEMORY_PRO_HOME);
  if (process.env.MEMORY_DB_PATH) return dirname(expandUserPath(process.env.MEMORY_DB_PATH));
  return join(homedir(), '.codex', 'memory-pro');
}

export function getMemoryDbPath(): string {
  return expandUserPath(
    process.env.MEMORY_DB_PATH || join(getMemoryProHome(), 'lancedb')
  );
}

export function memoryProPath(...segments: string[]): string {
  return join(getMemoryProHome(), ...segments);
}
