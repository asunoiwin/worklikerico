/**
 * Capture Journal Module
 * Pending capture queue with dedup and replay
 */
export interface CaptureJournalEntry {
    id: string;
    dedupeKey: string;
    content: string;
    category?: string;
    importance?: number;
    createdAt: string;
    lastAttemptAt?: string;
    status: 'pending' | 'captured' | 'dropped';
    attempts: number;
    lastResult?: string;
    context?: Record<string, unknown>;
}
export declare class CaptureJournal {
    private readonly filePath;
    private readonly statusPath;
    private replayRunning;
    constructor(baseDir?: string);
    private createDedupeKey;
    append(params: {
        content: string;
        category?: string;
        importance?: number;
        context?: Record<string, unknown>;
    }): CaptureJournalEntry;
    update(entryId: string, updates: Partial<CaptureJournalEntry>): CaptureJournalEntry | null;
    listPending(limit?: number): CaptureJournalEntry[];
    stats(): {
        total: number;
        pending: number;
        captured: number;
        dropped: number;
        oldestPending: string | null;
        replayRunning: boolean;
    };
    beginReplay(): boolean;
    endReplay(): void;
    prune(options?: {
        keepCaptured?: number;
        keepDropped?: number;
    }): void;
    private read;
    private write;
}
export default CaptureJournal;
