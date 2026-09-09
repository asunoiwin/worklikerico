/**
 * Memory Cleaner Module
 * Contextual summarization + stored memory cleanup
 */
import type { Embedder } from './embedder.js';
import type { MemoryStore } from './store.js';
export declare function summarizeContextualMemory(primary: string, options?: {
    recentContext?: string[];
    maxChars?: number;
}): string;
export declare function isMemoryNoise(text: string, source?: string): boolean;
export declare function cleanupStoredMemories(store: MemoryStore, embedder: Embedder, options?: {
    limit?: number;
    maxAgeDays?: number;
}): Promise<{
    scanned: number;
    deleted: number;
    cleaned: number;
    deduped: number;
}>;
