/**
 * LanceDB Storage Layer
 */
export interface MemoryEntry {
    id: string;
    text: string;
    vector: number[];
    category: "preference" | "fact" | "decision" | "entity" | "other" | "task" | "lesson";
    scope: string;
    importance: number;
    timestamp: number;
    metadata?: string;
    recallCount?: number;
    lastRecallAt?: number;
}
export interface MemorySearchResult {
    entry: MemoryEntry;
    score: number;
}
export interface StoreConfig {
    dbPath: string;
    vectorDim: number;
}
export type VectorIssue = "empty" | "badDim" | "zero";
export declare function getVectorIssue(vector: unknown, vectorDim: number, minL2Norm?: number): VectorIssue | null;
export declare function validateVector(vector: unknown, vectorDim: number): asserts vector is number[];
export declare class MemoryStore {
    private db;
    private table;
    private config;
    private _hasFts;
    constructor(config: StoreConfig);
    get hasFtsSupport(): boolean;
    init(): Promise<void>;
    /**
     * 陈旧句柄自愈：本进程与 codex-memory-pro 共用同一 LanceDB（MEMORY_DB_PATH 相同），
     * 对方进程 optimize 回收旧版本后，本进程缓存的 table 句柄会指向已删除的数据文件，
     * 读写报 "Not found: ...lance"。此时重开表句柄重试一次即可恢复。
     */
    private isStaleHandleError;
    private withLiveTable;
    store(entry: Omit<MemoryEntry, "id" | "timestamp">): Promise<MemoryEntry>;
    vectorSearch(queryVector: number[], limit: number, minScore: number, scopeFilter?: string[]): Promise<MemorySearchResult[]>;
    bm25Search(query: string, limit: number, scopeFilter?: string[]): Promise<MemorySearchResult[]>;
    getByIds(ids: string[]): Promise<MemoryEntry[]>;
    delete(id: string, scopeFilter?: string[]): Promise<boolean>;
    update(id: string, updates: Partial<Pick<MemoryEntry, "text" | "vector" | "importance" | "category" | "metadata">>, scopeFilter?: string[]): Promise<MemoryEntry | null>;
    /**
     * LanceDB 表版本号：每次写(add/update/delete，含召回计数)都由引擎原子单调自增，跨进程可靠。
     * 用作图谱新鲜度信号——单调原子、绝不回退/掩盖。代价：召回计数也会变更版本→召回后下次
     * ensureFresh 会重建图谱(已接受的性能取舍，非正确性问题；彻底消除自管计数器的竞态/掩盖)。
     */
    version(): Promise<number>;
    /**
     * 压缩存储：合并数据碎片 + 重建索引，并回收早于 (now - retainMs) 的旧版本。
     * 治理"内容仅数 MB 却被索引/版本历史撑到上百 MB"的膨胀。LanceDB 永远保留当前版本，
     * 清旧版本不丢现存记忆；retainMs 留一点安全窗口，避免并发写入产生的版本被提前回收。
     */
    optimize(retainMs?: number): Promise<{
        ok: boolean;
        error?: string;
    }>;
    count(scopeFilter?: string[]): Promise<number>;
    scan(scopeFilter?: string[], limit?: number, offset?: number): Promise<MemoryEntry[]>;
    incrementRecallBatch(ids: string[]): Promise<void>;
    list(scopeFilter?: string[], category?: string, limit?: number, offset?: number): Promise<MemoryEntry[]>;
    getRecallCandidates(limit?: number): Promise<MemoryEntry[]>;
    /** 分页捞全量（绕过 list 单页 500 上限），用于 KG/atlas/cleaner 等需完整视图的场景。按时间倒序。 */
    listAll(scopeFilter?: string[], category?: string): Promise<MemoryEntry[]>;
    updateEntrySupersedes(id: string, supersedesId: string): Promise<void>;
    updateEntryExpired(id: string): Promise<void>;
    stats(scopeFilter?: string[]): Promise<{
        totalCount: number;
        scopeCounts: Record<string, number>;
        categoryCounts: Record<string, number>;
    }>;
}
