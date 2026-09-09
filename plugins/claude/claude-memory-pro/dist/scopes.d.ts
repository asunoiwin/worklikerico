/**
 * Multi-Scope Access Control System
 */
export interface ScopeDefinition {
    description: string;
    metadata?: Record<string, unknown>;
}
export interface ScopeConfig {
    default: string;
    definitions: Record<string, ScopeDefinition>;
    agentAccess: Record<string, string[]>;
}
export interface ScopeManager {
    getAccessibleScopes(agentId?: string): string[];
    getDefaultScope(agentId?: string): string;
    isAccessible(scope: string, agentId?: string): boolean;
    validateScope(scope: string): boolean;
    getAllScopes(): string[];
    getScopeDefinition(scope: string): ScopeDefinition | undefined;
}
export declare const DEFAULT_SCOPE_CONFIG: ScopeConfig;
export declare class MemoryScopeManager implements ScopeManager {
    private config;
    constructor(config?: Partial<ScopeConfig>);
    private isBuiltInScope;
    getAccessibleScopes(agentId?: string): string[];
    getDefaultScope(agentId?: string): string;
    isAccessible(scope: string, agentId?: string): boolean;
    validateScope(scope: string): boolean;
    getAllScopes(): string[];
    getScopeDefinition(scope: string): ScopeDefinition | undefined;
    addScopeDefinition(scope: string, definition: ScopeDefinition): void;
    removeScopeDefinition(scope: string): boolean;
    setAgentAccess(agentId: string, scopes: string[]): void;
    removeAgentAccess(agentId: string): boolean;
    exportConfig(): ScopeConfig;
    getStats(): {
        totalScopes: number;
        agentsWithCustomAccess: number;
        scopesByType: Record<string, number>;
    };
}
export declare function createScopeManager(config?: Partial<ScopeConfig>): MemoryScopeManager;
export declare function parseScopeId(scope: string): {
    type: string;
    id: string;
} | null;
