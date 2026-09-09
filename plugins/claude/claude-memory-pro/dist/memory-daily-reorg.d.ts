/**
 * Claude Memory Pro - Daily Reorganization Module
 *
 * 空闲时段自动整理（默认凌晨 4 点）：
 * 1. 重建 Atlas 和 KG
 * 2. 按 entityKey 分组检测碰撞
 * 3. 矛盾检测（KG contradicts 边 + 文本相似度）
 * 4. 标记过期记忆（> maxAgeDays）
 *
 * 移植自 OpenClaw memory-daily-reorg，去掉外部 LLM 依赖，
 * 改用内置 KG 矛盾检测。
 */
interface MemoryEntry {
    id: string;
    text: string;
    category: string;
    scope: string;
    importance: number;
    timestamp: number;
    metadata?: string;
    recallCount?: number;
}
export interface ReorgResult {
    atlasRebuilt: boolean;
    kgRebuilt: boolean;
    atlasEntries: number;
    entityGroups: number;
    contradictions: number;
    superseded: number;
    expiredMarked: number;
    duration: number;
}
export declare function detectSimpleContradiction(newer: string, older: string): boolean;
interface StoreForReorg {
    listAll(scopeFilter?: string[], category?: string): Promise<MemoryEntry[]>;
    updateEntrySupersedes(id: string, supersedesId: string): Promise<void>;
    updateEntryExpired(id: string): Promise<void>;
}
export declare function runDailyReorganization(store: StoreForReorg, atlasBuildFn?: (store: any) => Promise<any>, kgBuildFn?: () => Promise<void>): Promise<ReorgResult>;
export {};
