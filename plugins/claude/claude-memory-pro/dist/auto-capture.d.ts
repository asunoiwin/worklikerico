/**
 * Auto Capture Module v2
 *
 * 两级捕获策略：
 * 1. 关键词快速匹配（零延迟，不调用 LLM）
 * 2. LLM 智能分析（用 SiliconFlow 上的轻量模型，~200 token/次）
 *
 * LLM 分析只在关键词未命中时触发，避免无意义开销。
 */
import type { MemoryStore } from './store.js';
import type { Embedder } from './embedder.js';
export interface CaptureConfig {
    enabled: boolean;
    llmEnabled: boolean;
    patterns: {
        task: string[];
        rule: string[];
        decision: string[];
        correction: string[];
        preference: string[];
        context: string[];
    };
    importance: {
        task: number;
        rule: number;
        decision: number;
        correction: number;
        preference: number;
        context: number;
    };
}
export interface CaptureContext {
    sessionId?: string;
    taskId?: string;
    source?: string;
    actorRole?: string;
    scope?: string;
    metadata?: Record<string, unknown>;
    recentContext?: string[];
}
export interface LLMJsonRequest {
    apiKey: string;
    baseURL: string;
    model: string;
    systemPrompt: string;
    userPrompt: string;
    maxTokens?: number;
    timeoutMs?: number;
}
export interface CaptureRedirect {
    kind: 'redirect';
    redirect: 'task_create' | 'lesson_capture';
    hint: string;
}
export interface CaptureStored {
    kind: 'stored';
    type: string;
    importance: number;
    llmUsed: boolean;
}
export type CaptureResult = CaptureStored | CaptureRedirect;
export declare function llmJsonAnalyze<T = Record<string, unknown>>({ apiKey, baseURL, model, systemPrompt, userPrompt, maxTokens, timeoutMs, }: LLMJsonRequest): Promise<T | null>;
export declare class AutoCaptureEngine {
    private store;
    private embedder;
    private config;
    private context;
    private llmApiKey;
    private llmBaseURL;
    private llmModel;
    constructor(store: MemoryStore, embedder: Embedder, config?: Partial<CaptureConfig>);
    capture(content: string, category?: string, importance?: number, overrides?: CaptureContext): Promise<CaptureResult | null>;
    analyze(content: string): {
        type: string;
        importance: number;
    } | null;
    setContext(context: CaptureContext): void;
    get isLLMEnabled(): boolean;
    get captureModel(): string;
}
export default AutoCaptureEngine;
