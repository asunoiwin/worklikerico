/**
 * Claude Memory Pro - Dream Manager
 * 三阶段记忆晋升：light / deep / REM
 *
 * 基于召回频率、最近性、查询多样性的加权评分，
 * 将高频记忆晋升并写入 dream.md（Dream Trail 格式）。
 * Replay-safe 去重：trail state 防止重复晋升。
 *
 * 移植自 OpenClaw memory-enhanced dream-manager。
 */
import type { MemoryEntry, MemoryStore } from './store.js';
import type { Embedder } from './embedder.js';
export type DreamPhase = 'light' | 'deep' | 'rem';
export interface DreamThresholds {
    light: {
        minScore: number;
        minRecallCount: number;
        minUniqueQueries: number;
    };
    deep: {
        minScore: number;
        minRecallCount: number;
        minUniqueQueries: number;
    };
    rem: {
        minScore: number;
        minRecallCount: number;
        minUniqueQueries: number;
    };
}
export interface DreamConfig {
    mode: 'off' | 'light' | 'deep' | 'rem';
    thresholds: DreamThresholds;
    aging: {
        recencyHalfLifeDays: number;
        maxAgeDays: number;
    };
    dailyReorgHour: number;
}
export interface PromotionCandidate {
    memoryId: string;
    memoryText: string;
    category: string;
    recallCount: number;
    totalRelevance: number;
    uniqueQueries: string[];
    queryDiversity: number;
    avgRelevance: number;
    recencyScore: number;
    promotionScore: number;
    promotionTier: DreamPhase | 'none';
}
export interface PromotionDecision {
    memoryId: string;
    tier: DreamPhase | 'none';
    written: boolean;
    reason: 'promoted' | 'tier_none' | 'already_promoted_same_or_higher';
    existingPhase?: DreamPhase;
}
export declare const DEFAULT_CONFIG: DreamConfig;
export declare function getPromotionCandidates(entries: MemoryEntry[], config?: DreamConfig): PromotionCandidate[];
interface TrailState {
    promoted: Record<string, {
        phase: DreamPhase;
        promotedAt: string;
        promotionScore: number;
    }>;
}
export declare function applyPromotions(candidates: PromotionCandidate[], config?: DreamConfig): {
    written: number;
    skipped: number;
    phase: DreamPhase;
    decisions: PromotionDecision[];
};
export declare function promoteMemoriesFromStore(store: {
    getRecallCandidates: (limit?: number) => Promise<MemoryEntry[]>;
}, config?: DreamConfig): Promise<{
    candidates: PromotionCandidate[];
    written: number;
    skipped: number;
    phase: DreamPhase;
    decisions: PromotionDecision[];
    promotedToMemoryMd: number;
}>;
interface LastRunState {
    light: string | null;
    deep: string | null;
    rem: string | null;
    maintenance?: string | null;
}
export declare function loadLastRunState(): LastRunState;
export declare function saveLastRunState(state: LastRunState): void;
export declare function needsRecovery(lastRun: string | null, intervalMs: number): boolean;
export declare function recoverMissedPhases(store: {
    getRecallCandidates: (limit?: number) => Promise<MemoryEntry[]>;
}, config?: DreamConfig): Promise<{
    recovered: string[];
}>;
export interface MaintenanceReport {
    ranAt: string;
    cleanup?: {
        scanned: number;
        deleted: number;
        cleaned: number;
        deduped: number;
    };
    compact?: {
        ok: boolean;
        error?: string;
    };
}
/**
 * 执行一次 dream 维护：
 *  - 清理：删噪音 + 去重（复用 memory-cleaner，不重造）
 *  - 压缩：LanceDB optimize 合并碎片 + 回收旧版本（治"8M 内容撑成上百 M"的索引/版本膨胀）
 * 压缩排在清理之后：清理产生的删除会留下更多可回收的碎片/旧版本。
 * cleanup / compact 可分别关闭。
 */
export declare function runDreamMaintenance(store: MemoryStore, embedder: Embedder, opts?: {
    cleanup?: boolean;
    compact?: boolean;
    cleanupLimit?: number;
}): Promise<MaintenanceReport>;
/**
 * 到期才跑维护（默认每 24h），并更新 last-run 标记。崩溃安全：跑成才记标记。
 * 返回 null 表示未到期、本次跳过。
 */
export declare function maybeRunMaintenance(store: MemoryStore, embedder: Embedder, intervalMs?: number): Promise<MaintenanceReport | null>;
/**
 * 将 promote 级记忆同步到 Claude Code 原生 MEMORY.md 体系。
 * 写入 dream-promoted.md 主题文件，并在 MEMORY.md 索引中注册。
 */
export declare function syncPromotedToMemoryMd(candidates: PromotionCandidate[]): number;
export declare function readDreamTrail(): string;
export declare function getDreamStats(): {
    totalSections: number;
    totalPromoted: number;
    lastRunState: LastRunState;
    trailState: TrailState;
};
export {};
