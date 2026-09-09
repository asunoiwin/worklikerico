/**
 * Embedding Abstraction Layer
 * OpenAI-compatible API for various embedding providers
 */
import OpenAI from "openai";
import { createHash } from "node:crypto";
class EmbeddingCache {
    cache = new Map();
    maxSize;
    ttlMs;
    hits = 0;
    misses = 0;
    constructor(maxSize = 256, ttlMinutes = 30) {
        this.maxSize = maxSize;
        this.ttlMs = ttlMinutes * 60_000;
    }
    key(text, task) {
        return createHash("sha256").update(`${task || ""}:${text}`).digest("hex").slice(0, 24);
    }
    get(text, task) {
        const k = this.key(text, task);
        const entry = this.cache.get(k);
        if (!entry) {
            this.misses++;
            return undefined;
        }
        if (Date.now() - entry.createdAt > this.ttlMs) {
            this.cache.delete(k);
            this.misses++;
            return undefined;
        }
        this.cache.delete(k);
        this.cache.set(k, entry);
        this.hits++;
        return entry.vector;
    }
    set(text, task, vector) {
        const k = this.key(text, task);
        if (this.cache.size >= this.maxSize) {
            const firstKey = this.cache.keys().next().value;
            if (firstKey !== undefined)
                this.cache.delete(firstKey);
        }
        this.cache.set(k, { vector, createdAt: Date.now() });
    }
    get size() { return this.cache.size; }
    get stats() {
        const total = this.hits + this.misses;
        return {
            size: this.cache.size,
            hits: this.hits,
            misses: this.misses,
            hitRate: total > 0 ? `${((this.hits / total) * 100).toFixed(1)}%` : "N/A",
        };
    }
}
const EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-004": 768,
    "BAAI/bge-m3": 1024,
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "jina-embeddings-v5-text-small": 1024,
    "jina-embeddings-v5-text-nano": 768,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
};
export function getVectorDimensions(model, overrideDims) {
    if (overrideDims && overrideDims > 0)
        return overrideDims;
    const dims = EMBEDDING_DIMENSIONS[model];
    if (!dims) {
        throw new Error(`Unsupported embedding model: ${model}. Set EMBEDDING_DIMENSIONS or configure dimensions.`);
    }
    return dims;
}
// ============================================================================
// Embedder Class
// ============================================================================
export class Embedder {
    client;
    dimensions;
    _cache;
    _model;
    _taskQuery;
    _taskPassage;
    _normalized;
    _requestDimensions;
    constructor(config) {
        this._model = config.model;
        this._taskQuery = config.taskQuery;
        this._taskPassage = config.taskPassage;
        this._normalized = config.normalized;
        this._requestDimensions = config.dimensions;
        this.client = new OpenAI({
            apiKey: config.apiKey,
            ...(config.baseURL ? { baseURL: config.baseURL } : {}),
        });
        this.dimensions = getVectorDimensions(config.model, config.dimensions);
        this._cache = new EmbeddingCache(256, 30);
    }
    async embed(text) {
        return this.embedPassage(text);
    }
    async embedQuery(text) {
        return this.embedSingle(text, this._taskQuery);
    }
    async embedPassage(text) {
        return this.embedSingle(text, this._taskPassage);
    }
    buildPayload(input, task) {
        const payload = { model: this._model, input };
        if (task)
            payload.task = task;
        if (this._normalized !== undefined)
            payload.normalized = this._normalized;
        if (this._requestDimensions && this._requestDimensions > 0) {
            payload.dimensions = this._requestDimensions;
        }
        return payload;
    }
    async embedSingle(text, task) {
        if (!text || text.trim().length === 0)
            throw new Error("Cannot embed empty text");
        const cached = this._cache.get(text, task);
        if (cached)
            return cached;
        const response = await this.client.embeddings.create(this.buildPayload(text, task));
        const embedding = response.data[0]?.embedding;
        if (!embedding)
            throw new Error("No embedding returned from provider");
        if (embedding.length !== this.dimensions) {
            throw new Error(`Dimension mismatch: expected ${this.dimensions}, got ${embedding.length}`);
        }
        this._cache.set(text, task, embedding);
        return embedding;
    }
    async embedBatch(texts) {
        if (!texts || texts.length === 0)
            return [];
        const response = await this.client.embeddings.create(this.buildPayload(texts.filter(t => t.trim()), this._taskPassage));
        return response.data.map(item => item.embedding);
    }
    get model() { return this._model; }
    async test() {
        try {
            const v = await this.embedPassage("test");
            return { success: true, dimensions: v.length };
        }
        catch (error) {
            return { success: false, error: error instanceof Error ? error.message : String(error) };
        }
    }
    get cacheStats() { return this._cache.stats; }
}
export function createEmbedder(config) {
    return new Embedder(config);
}
//# sourceMappingURL=embedder.js.map