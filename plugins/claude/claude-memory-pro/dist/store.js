/**
 * LanceDB Storage Layer
 */
import { randomUUID } from "node:crypto";
// ============================================================================
// LanceDB Dynamic Import
// ============================================================================
let lancedbImportPromise = null;
const loadLanceDB = async () => {
    if (!lancedbImportPromise) {
        lancedbImportPromise = import("@lancedb/lancedb");
    }
    return await lancedbImportPromise;
};
// ============================================================================
// Utility
// ============================================================================
function clampInt(value, min, max) {
    if (!Number.isFinite(value))
        return min;
    return Math.min(max, Math.max(min, Math.floor(value)));
}
function escapeSqlLiteral(value) {
    return value.replace(/'/g, "''");
}
const MIN_VECTOR_L2_NORM = 1e-6;
function toVectorArray(vector) {
    if (!vector)
        return null;
    if (Array.isArray(vector))
        return vector;
    if (typeof vector === "object" && Symbol.iterator in vector) {
        return Array.from(vector);
    }
    return null;
}
export function getVectorIssue(vector, vectorDim, minL2Norm = MIN_VECTOR_L2_NORM) {
    const values = toVectorArray(vector);
    if (!values || values.length === 0)
        return "empty";
    if (values.length !== vectorDim)
        return "badDim";
    let normSq = 0;
    for (const value of values) {
        if (typeof value !== "number" || !Number.isFinite(value))
            return "badDim";
        normSq += value * value;
    }
    return Math.sqrt(normSq) > minL2Norm ? null : "zero";
}
export function validateVector(vector, vectorDim) {
    const issue = getVectorIssue(vector, vectorDim);
    if (!issue)
        return;
    throw new Error(`Invalid memory vector (${issue}): expected ${vectorDim} dimensions and L2 norm > ${MIN_VECTOR_L2_NORM}`);
}
function rowToMemoryEntry(row) {
    return {
        id: row.id,
        text: row.text,
        vector: Array.from(row.vector || []),
        category: row.category,
        scope: row.scope,
        importance: row.importance,
        timestamp: row.timestamp,
        metadata: row.metadata,
        recallCount: row.recallCount || 0,
        lastRecallAt: row.lastRecallAt || 0,
    };
}
// ============================================================================
// MemoryStore
// ============================================================================
export class MemoryStore {
    db = null;
    table = null;
    config;
    _hasFts = false;
    constructor(config) {
        this.config = config;
    }
    get hasFtsSupport() { return this._hasFts; }
    async init() {
        const lancedb = await loadLanceDB();
        this.db = await lancedb.connect(this.config.dbPath);
        const tableNames = await this.db.tableNames();
        if (tableNames.includes("memories")) {
            this.table = await this.db.openTable("memories");
        }
        else {
            const emptyData = [{
                    id: "__init__",
                    text: "__init__",
                    vector: new Array(this.config.vectorDim).fill(0),
                    category: "other",
                    scope: "system",
                    importance: 0,
                    timestamp: 0,
                    metadata: "{}",
                    recallCount: 0,
                    lastRecallAt: 0,
                }];
            this.table = await this.db.createTable("memories", emptyData);
            await this.table.delete("id = '__init__'");
        }
        // Try to create FTS index
        try {
            await this.table.createIndex("text", { config: lancedb.Index.fts() });
            this._hasFts = true;
        }
        catch (err) {
            // Index already exists → FTS is available; other errors → FTS unavailable
            const msg = err instanceof Error ? err.message : String(err);
            this._hasFts = /already exists|already indexed/i.test(msg);
            if (!this._hasFts) {
                console.error(`[claude-memory-pro] FTS 索引创建失败，回退到纯向量模式: ${msg}`);
            }
        }
    }
    /**
     * 陈旧句柄自愈：本进程与 codex-memory-pro 共用同一 LanceDB（MEMORY_DB_PATH 相同），
     * 对方进程 optimize 回收旧版本后，本进程缓存的 table 句柄会指向已删除的数据文件，
     * 读写报 "Not found: ...lance"。此时重开表句柄重试一次即可恢复。
     */
    isStaleHandleError(err) {
        const msg = err instanceof Error ? err.message : String(err);
        return /Not found:.*\.lance|dataset.*(deleted|not found)|version.*(not found|no longer exists)/i.test(msg);
    }
    async withLiveTable(fn) {
        if (!this.table)
            throw new Error("Store not initialized");
        try {
            return await fn(this.table);
        }
        catch (err) {
            if (!this.isStaleHandleError(err) || !this.db)
                throw err;
            console.error(`[claude-memory-pro] 表句柄陈旧（另一进程已回收旧版本），重开句柄重试`);
            this.table = await this.db.openTable("memories");
            return await fn(this.table);
        }
    }
    async store(entry) {
        if (!this.table)
            throw new Error("Store not initialized");
        validateVector(entry.vector, this.config.vectorDim);
        const full = {
            ...entry,
            id: randomUUID(),
            timestamp: Date.now(),
            recallCount: 0,
            lastRecallAt: 0,
        };
        await this.withLiveTable(t => t.add([full]));
        return full;
    }
    async vectorSearch(queryVector, limit, minScore, scopeFilter) {
        if (!this.table)
            throw new Error("Store not initialized");
        const safeLimit = clampInt(limit, 1, 100);
        const results = await this.withLiveTable(t => {
            let query = t.search(queryVector).limit(safeLimit);
            if (scopeFilter && scopeFilter.length > 0) {
                const scopeConditions = scopeFilter.map(s => `scope = '${escapeSqlLiteral(s)}'`).join(" OR ");
                query = query.where(`(${scopeConditions})`);
            }
            return query.toArray();
        });
        return results
            .map((row) => ({
            entry: rowToMemoryEntry(row),
            score: Math.max(0, 1 - (row._distance || 0)),
        }))
            .filter((r) => r.score >= minScore);
    }
    async bm25Search(query, limit, scopeFilter) {
        if (!this.table || !this._hasFts)
            return [];
        const safeLimit = clampInt(limit, 1, 100);
        try {
            const results = await this.withLiveTable(t => {
                let search = t.search(query, "text").limit(safeLimit);
                if (scopeFilter && scopeFilter.length > 0) {
                    const scopeConditions = scopeFilter.map(s => `scope = '${escapeSqlLiteral(s)}'`).join(" OR ");
                    search = search.where(`(${scopeConditions})`);
                }
                return search.toArray();
            });
            return results.map((row) => ({
                entry: rowToMemoryEntry(row),
                score: row._score || 0.5,
            }));
        }
        catch {
            return [];
        }
    }
    async getByIds(ids) {
        if (!this.table || ids.length === 0)
            return [];
        const conditions = ids.map(id => `id = '${escapeSqlLiteral(id)}'`).join(" OR ");
        const results = await this.withLiveTable(t => t.search(new Array(this.config.vectorDim).fill(0))
            .where(`(${conditions})`)
            .limit(ids.length)
            .toArray());
        return results.map(rowToMemoryEntry);
    }
    async delete(id, scopeFilter) {
        if (!this.table)
            return false;
        try {
            let condition = `id = '${escapeSqlLiteral(id)}'`;
            if (scopeFilter && scopeFilter.length > 0) {
                const scopeConditions = scopeFilter.map(s => `scope = '${escapeSqlLiteral(s)}'`).join(" OR ");
                condition += ` AND (${scopeConditions})`;
            }
            // 真删到才算成功：删 0 行（id 不存在 / 域不匹配）返回 false，避免假"已删除"确认
            return await this.withLiveTable(async (t) => {
                const matched = await t.countRows(condition);
                if (matched === 0)
                    return false;
                await t.delete(condition);
                return true;
            });
        }
        catch {
            return false;
        }
    }
    async update(id, updates, scopeFilter) {
        if (!this.table)
            return null;
        if ("vector" in updates) {
            validateVector(updates.vector, this.config.vectorDim);
        }
        // LanceDB doesn't have native update, so we read-delete-insert
        const existing = await this.getByIds([id]);
        if (existing.length === 0)
            return null;
        const entry = existing[0];
        if (scopeFilter && scopeFilter.length > 0 && !scopeFilter.includes(entry.scope))
            return null;
        const updated = {
            ...entry,
            ...updates,
            id: entry.id,
            timestamp: entry.timestamp,
        };
        // 原子 upsert（按 id 合并）：避免"先删后加"中途失败丢记忆 / 并发回滚
        await this.withLiveTable(t => t.mergeInsert("id").whenMatchedUpdateAll().whenNotMatchedInsertAll().execute([updated]));
        return updated;
    }
    /**
     * LanceDB 表版本号：每次写(add/update/delete，含召回计数)都由引擎原子单调自增，跨进程可靠。
     * 用作图谱新鲜度信号——单调原子、绝不回退/掩盖。代价：召回计数也会变更版本→召回后下次
     * ensureFresh 会重建图谱(已接受的性能取舍，非正确性问题；彻底消除自管计数器的竞态/掩盖)。
     */
    async version() {
        if (!this.table)
            return 0;
        try {
            return await this.table.version();
        }
        catch {
            return 0;
        }
    }
    /**
     * 压缩存储：合并数据碎片 + 重建索引，并回收早于 (now - retainMs) 的旧版本。
     * 治理"内容仅数 MB 却被索引/版本历史撑到上百 MB"的膨胀。LanceDB 永远保留当前版本，
     * 清旧版本不丢现存记忆；retainMs 留一点安全窗口，避免并发写入产生的版本被提前回收。
     */
    async optimize(retainMs = 2 * 60 * 1000) {
        if (!this.table)
            return { ok: false, error: "Store not initialized" };
        try {
            const cleanupOlderThan = new Date(Date.now() - Math.max(0, retainMs));
            await this.withLiveTable(t => t.optimize({ cleanupOlderThan }));
            return { ok: true };
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            console.error(`[claude-memory-pro] optimize 失败: ${msg}`);
            return { ok: false, error: msg };
        }
    }
    async count(scopeFilter) {
        if (!this.table)
            return 0;
        if (!scopeFilter || scopeFilter.length === 0)
            return await this.withLiveTable(t => t.countRows());
        const scopeConditions = scopeFilter.map(s => `scope = '${escapeSqlLiteral(s)}'`).join(" OR ");
        return await this.withLiveTable(t => t.countRows(`(${scopeConditions})`));
    }
    async scan(scopeFilter, limit = 500, offset = 0) {
        if (!this.table)
            return [];
        const safeLimit = clampInt(limit, 1, 5000);
        const safeOffset = clampInt(offset, 0, Number.MAX_SAFE_INTEGER);
        const results = await this.withLiveTable(t => {
            let query = t.query().limit(safeLimit).offset(safeOffset);
            if (scopeFilter && scopeFilter.length > 0) {
                const scopeConditions = scopeFilter.map(s => `scope = '${escapeSqlLiteral(s)}'`).join(" OR ");
                query = query.where(`(${scopeConditions})`);
            }
            return query.toArray();
        });
        return results.map(rowToMemoryEntry);
    }
    async incrementRecallBatch(ids) {
        if (!this.table || ids.length === 0)
            return;
        const now = Date.now();
        const inList = ids.map(id => `'${escapeSqlLiteral(id)}'`).join(", ");
        try {
            // DB 端原子自增（valuesSql 在引擎内对每行算 recallCount+1），避免 read-modify-write 并发丢计数
            await this.withLiveTable(t => t.update({
                where: `id IN (${inList})`,
                valuesSql: { recallCount: "coalesce(recallCount, 0) + 1", lastRecallAt: String(now) },
            }));
        }
        catch (err) {
            console.error(`[claude-memory-pro] incrementRecallBatch 失败: ${err instanceof Error ? err.message : err}`);
        }
    }
    async list(scopeFilter, category, limit = 10, offset = 0) {
        // 基于 listAll 真分页（原零向量搜索是假分页，连"最新N条"都不可靠：先取任意窗口再排序）
        const safeLimit = clampInt(limit, 1, 500);
        const all = await this.listAll(scopeFilter, category);
        return all.slice(offset, offset + safeLimit);
    }
    async getRecallCandidates(limit = 200) {
        // 全量里按召回次数取 top，而非"最新N条里挑高频"（否则老的高频记忆永进不了候选）
        const entries = (await this.listAll()).filter(e => (e.recallCount ?? 0) > 0);
        entries.sort((a, b) => (b.recallCount || 0) - (a.recallCount || 0));
        return entries.slice(0, clampInt(limit, 1, 5000));
    }
    /** 分页捞全量（绕过 list 单页 500 上限），用于 KG/atlas/cleaner 等需完整视图的场景。按时间倒序。 */
    async listAll(scopeFilter, category) {
        const total = await this.count(scopeFilter);
        // scan 无保证顺序，offset 分页在多页时可能重叠/遗漏：能一次取全就一次取全；
        // 超过单次上限才分页，并按 id 去重兜底防重叠。
        let rows;
        if (total <= 5000) {
            rows = await this.scan(scopeFilter, Math.max(total, 1), 0);
        }
        else {
            const byId = new Map();
            for (let offset = 0; offset < total * 2 && byId.size < total; offset += 5000) {
                const batch = await this.scan(scopeFilter, 5000, offset);
                if (batch.length === 0)
                    break;
                for (const e of batch)
                    byId.set(e.id, e);
            }
            rows = [...byId.values()];
        }
        const filtered = category ? rows.filter(e => e.category === category) : rows;
        filtered.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
        return filtered;
    }
    async updateEntrySupersedes(id, supersedesId) {
        const entries = await this.getByIds([id]);
        if (entries.length === 0)
            return;
        const entry = entries[0];
        let meta = {};
        try {
            if (entry.metadata)
                meta = JSON.parse(entry.metadata);
        }
        catch { }
        meta.supersededBy = supersedesId;
        meta.supersededAt = new Date().toISOString();
        await this.update(id, { metadata: JSON.stringify(meta) });
    }
    async updateEntryExpired(id) {
        const entries = await this.getByIds([id]);
        if (entries.length === 0)
            return;
        const entry = entries[0];
        let meta = {};
        try {
            if (entry.metadata)
                meta = JSON.parse(entry.metadata);
        }
        catch { }
        meta.expired = true;
        meta.expiredAt = new Date().toISOString();
        await this.update(id, { metadata: JSON.stringify(meta) });
    }
    async stats(scopeFilter) {
        const [totalCount, entries] = await Promise.all([
            this.count(scopeFilter),
            this.listAll(scopeFilter),
        ]);
        const scopeCounts = {};
        const categoryCounts = {};
        for (const entry of entries) {
            scopeCounts[entry.scope] = (scopeCounts[entry.scope] || 0) + 1;
            categoryCounts[entry.category] = (categoryCounts[entry.category] || 0) + 1;
        }
        return { totalCount, scopeCounts, categoryCounts };
    }
}
//# sourceMappingURL=store.js.map