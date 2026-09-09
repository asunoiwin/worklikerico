/**
 * Hybrid Retrieval System
 * Combines vector search + BM25 full-text search with RRF fusion
 */
import type { MemoryStore, MemorySearchResult } from "./store.js";
import type { Embedder } from "./embedder.js";
export interface RetrievalConfig {
    mode: "hybrid" | "vector";
    vectorWeight: number;
    bm25Weight: number;
    minScore: number;
    rerank: "cross-encoder" | "lightweight" | "none";
    candidatePoolSize: number;
    recencyHalfLifeDays: number;
    recencyWeight: number;
    filterNoise: boolean;
    rerankApiKey?: string;
    rerankModel?: string;
    rerankEndpoint?: string;
    lengthNormAnchor: number;
    hardMinScore: number;
    timeDecayHalfLifeDays: number;
}
export interface RetrievalContext {
    query: string;
    limit: number;
    scopeFilter?: string[];
    category?: string;
}
export interface RetrievalResult extends MemorySearchResult {
    sources: {
        vector?: {
            score: number;
            rank: number;
        };
        bm25?: {
            score: number;
            rank: number;
        };
        fused?: {
            score: number;
        };
        reranked?: {
            score: number;
        };
    };
}
export declare const DEFAULT_RETRIEVAL_CONFIG: RetrievalConfig;
export declare class MemoryRetriever {
    private store;
    private embedder;
    private config;
    constructor(store: MemoryStore, embedder: Embedder, config?: RetrievalConfig);
    retrieve(context: RetrievalContext): Promise<RetrievalResult[]>;
    private vectorOnlyRetrieval;
    private hybridRetrieval;
    private postProcess;
    private applyRecencyBoost;
    private applyImportanceWeight;
    private applyTimeDecay;
    private applyLengthNorm;
    private applyMMR;
    updateConfig(newConfig: Partial<RetrievalConfig>): void;
    getConfig(): RetrievalConfig;
}
export declare function createRetriever(store: MemoryStore, embedder: Embedder, config?: Partial<RetrievalConfig>): MemoryRetriever;
