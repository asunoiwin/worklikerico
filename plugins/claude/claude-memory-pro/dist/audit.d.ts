/**
 * Audit Module - Memory health check and repair
 */
import type { MemoryStore } from './store.js';
export interface AuditResult {
    timestamp: number;
    stats: {
        total_memories: number;
        issues: number;
        noiseDeleted: number;
        duplicatesRemoved: number;
    };
}
export declare class AuditEngine {
    private store;
    private auditPromise;
    constructor(store: MemoryStore);
    runAudit(): Promise<AuditResult>;
}
export default AuditEngine;
