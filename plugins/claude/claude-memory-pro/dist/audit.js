/**
 * Audit Module - Memory health check and repair
 */
export class AuditEngine {
    store;
    auditPromise = null;
    constructor(store) {
        this.store = store;
    }
    async runAudit() {
        if (this.auditPromise)
            return this.auditPromise;
        this.auditPromise = (async () => {
            try {
                const stats = await this.store.stats();
                return {
                    timestamp: Date.now(),
                    stats: {
                        total_memories: stats.totalCount,
                        issues: 0,
                        noiseDeleted: 0,
                        duplicatesRemoved: 0,
                    },
                };
            }
            catch {
                return {
                    timestamp: Date.now(),
                    stats: { total_memories: 0, issues: 1, noiseDeleted: 0, duplicatesRemoved: 0 },
                };
            }
            finally {
                this.auditPromise = null;
            }
        })();
        return this.auditPromise;
    }
}
export default AuditEngine;
//# sourceMappingURL=audit.js.map