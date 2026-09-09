/**
 * Habit Tracker Module
 * Turns repeated memory recall patterns into lightweight instincts.
 * Supports memory promotion tiers: retain -> reinforce -> promote
 * Generates instinct-rollup.md for persistent behavior priors.
 */
export interface MemoryRecallStats {
    memoryId: string;
    memoryText: string;
    category: string;
    recallCount: number;
    firstRecallAt: string;
    lastRecallAt: string;
    recentRecallDays: number[];
    recentTimestamps?: string[];
}
export interface HabitCandidate {
    memoryId: string;
    memoryText: string;
    category: string;
    recallCount: number;
    lastRecallAt: string;
    recentRecallVelocity: number;
    promotionTier: 'retain' | 'reinforce' | 'promote';
    reason: string;
}
export declare function recordRecall(memoryId: string, memoryText: string, category: string, timestamp?: string): void;
export declare function recordRecallBatch(results: Array<{
    id: string;
    text: string;
    category: string;
}>): void;
export declare function generateHabitCandidates(): HabitCandidate[];
export declare function buildInstinctContext(maxCandidates?: number): string;
export declare function refreshHabitArtifacts(): void;
export declare function getHabitSummary(): {
    total: number;
    promote: number;
    reinforce: number;
    retain: number;
};
export declare function removeFromHabits(memoryId: string): void;
