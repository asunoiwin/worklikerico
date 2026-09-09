/**
 * Memory Atlas - Knowledge Graph Module
 * Builds a cluster-based knowledge map from stored memories.
 * Generates anchors, clusters, and edges for memory navigation.
 */
import type { MemoryStore } from './store.js';
export type AtlasAnchor = {
    id: string;
    category: string;
    source: string;
    importance: number;
    timestamp: number;
    preview: string;
    tokens: string[];
    quality: number;
    clusterKey: string;
};
export type AtlasCluster = {
    key: string;
    label: string;
    count: number;
    categories: Record<string, number>;
    sources: Record<string, number>;
    anchorIds: string[];
    topTokens: string[];
    lastSeen: number;
};
export type AtlasEdge = {
    from: string;
    to: string;
    weight: number;
    reason: string;
};
export declare function getMemoryAtlasStatus(): Record<string, unknown> | null;
export declare function getAtlasHintsForQuery(query: string, atlas?: Record<string, unknown> | null): {
    clusterKeys: string[];
    anchorIds: string[];
    summary: string[];
};
export declare function refreshMemoryAtlas(store: MemoryStore): Promise<Record<string, unknown>>;
