/**
 * Embedding Abstraction Layer
 * OpenAI-compatible API for various embedding providers
 */
export interface EmbeddingConfig {
    provider: "openai-compatible";
    apiKey: string;
    model: string;
    baseURL?: string;
    dimensions?: number;
    taskQuery?: string;
    taskPassage?: string;
    normalized?: boolean;
}
export declare function getVectorDimensions(model: string, overrideDims?: number): number;
export declare class Embedder {
    private client;
    readonly dimensions: number;
    private readonly _cache;
    private readonly _model;
    private readonly _taskQuery?;
    private readonly _taskPassage?;
    private readonly _normalized?;
    private readonly _requestDimensions?;
    constructor(config: EmbeddingConfig);
    embed(text: string): Promise<number[]>;
    embedQuery(text: string): Promise<number[]>;
    embedPassage(text: string): Promise<number[]>;
    private buildPayload;
    private embedSingle;
    embedBatch(texts: string[]): Promise<number[][]>;
    get model(): string;
    test(): Promise<{
        success: boolean;
        error?: string;
        dimensions?: number;
    }>;
    get cacheStats(): {
        size: number;
        hits: number;
        misses: number;
        hitRate: string;
    };
}
export declare function createEmbedder(config: EmbeddingConfig): Embedder;
