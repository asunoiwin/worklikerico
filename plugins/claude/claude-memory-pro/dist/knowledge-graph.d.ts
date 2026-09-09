/**
 * Knowledge Graph Module
 *
 * Multi-dimensional knowledge graph as memory index.
 *
 * Design:
 * - KG nodes: memoryId + summary + entityKey + categories (NO full content)
 * - KG edges: causal / temporal / subject / contradicts
 * - Category is retained as a node/index property, but build does not create category edges.
 * - Source of truth: LanceDB (full content)
 * - KG lives in memory; built from LanceDB on server start
 * - Incremental updates on new memory store
 *
 * Recall flow:
 *   recall(query) → KG.query() → candidate memoryIds → LanceDB.getByIds() → full entries
 */
import type { MemoryStore, MemoryEntry } from './store.js';
export type RelationType = 'causal' | 'temporal' | 'subject' | 'category' | 'contradicts';
export interface KGNode {
    id: string;
    summary: string;
    entityKey: string | null;
    categories: string[];
    importance: number;
    createdAt: number;
    updatedAt: number;
    superseded: boolean;
}
export interface KGEdge {
    source: string;
    target: string;
    relation: RelationType;
    weight: number;
}
export type RouteDimension = 'entity' | 'category' | 'temporal' | 'causal' | 'text' | 'neighbor';
export interface KGQueryResult {
    id: string;
    summary: string;
    entityKey: string | null;
    importance: number;
    score: number;
    reason: string;
    dimensions: RouteDimension[];
    superseded: boolean;
}
export interface KnowledgeGraphData {
    nodes: Map<string, KGNode>;
    byEntityKey: Map<string, string[]>;
    byCategory: Map<string, string[]>;
    edges: KGEdge[];
    builtAt: string | null;
}
export declare function parseMemoryMetadata(entry: Pick<MemoryEntry, 'metadata'>): Record<string, any>;
export type MetadataStance = 'affirm' | 'negate' | 'neutral';
export declare function isFactKeyCategory(category: string): boolean;
export declare function normalizeFactKey(value: unknown): string | null;
export declare function generateFactKeyForMemory(entry: Pick<MemoryEntry, 'text' | 'category' | 'scope' | 'metadata'>): string | null;
export declare function metadataWithFactKey(entry: Pick<MemoryEntry, 'text' | 'category' | 'scope' | 'metadata'>): Record<string, any>;
export declare class KnowledgeGraphManager {
    private kg;
    private store;
    private supersededCache;
    private builtVersion;
    constructor(store: MemoryStore);
    /**
     * 召回前调用：表版本变了（含其它进程的写）就重建。表版本原子单调，绝不回退/掩盖结构写。
     * 召回计数也会变更版本→召回后会重建一次（已接受的性能取舍，换取正确性与零竞态）。
     */
    ensureFresh(): Promise<void>;
    build(): Promise<void>;
    addNode(entry: MemoryEntry): Promise<void>;
    /**
     * 多维路由查询。
     * KG 是多维索引，从 entity/category/temporal/causal/text 多个维度
     * 对同一条记忆做索引，返回候选 ID 及命中维度。
     * 向量数据库负责后续精排。
     */
    query(rawQuery: string, options?: {
        limit?: number;
        includeSuperseded?: boolean;
    }): KGQueryResult[];
    getContradictions(memoryIds: string[]): Array<{
        a: string;
        b: string;
        weight: number;
    }>;
    getStats(): {
        totalNodes: number;
        totalEdges: number;
        supersededNodes: number;
        entityKeys: number;
        categories: number;
        builtAt: string | null;
        edgesByRelation: {
            causal: number;
            temporal: number;
            subject: number;
            category: number;
            contradicts: number;
        };
    };
    getDebugSnapshot(limit?: number): {
        generatedAt: string;
        stats: {
            totalNodes: number;
            totalEdges: number;
            supersededNodes: number;
            entityKeys: number;
            categories: number;
            builtAt: string | null;
            edgesByRelation: {
                causal: number;
                temporal: number;
                subject: number;
                category: number;
                contradicts: number;
            };
        };
        nodes: KGNode[];
        edges: KGEdge[];
        byEntityKey: {
            [k: string]: string[];
        };
        byCategory: {
            [k: string]: string[];
        };
    };
    writeDebugSnapshot(filePath?: string): string;
}
export declare function setKG(kg: KnowledgeGraphManager): void;
export declare function getKG(): KnowledgeGraphManager | null;
