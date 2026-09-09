/**
 * Multi-Scope Access Control System
 */
export const DEFAULT_SCOPE_CONFIG = {
    default: "global",
    definitions: {
        global: { description: "Shared knowledge across all agents" },
    },
    agentAccess: {},
};
const SCOPE_PATTERNS = {
    GLOBAL: "global",
    AGENT: (agentId) => `agent:${agentId}`,
    CUSTOM: (name) => `custom:${name}`,
    PROJECT: (projectId) => `project:${projectId}`,
    USER: (userId) => `user:${userId}`,
};
export class MemoryScopeManager {
    config;
    constructor(config = {}) {
        this.config = {
            default: config.default || DEFAULT_SCOPE_CONFIG.default,
            definitions: { ...DEFAULT_SCOPE_CONFIG.definitions, ...config.definitions },
            agentAccess: { ...DEFAULT_SCOPE_CONFIG.agentAccess, ...config.agentAccess },
        };
        if (!this.config.definitions.global) {
            this.config.definitions.global = { description: "Shared knowledge across all agents" };
        }
    }
    isBuiltInScope(scope) {
        return scope === "global" || scope.startsWith("agent:") || scope.startsWith("custom:") || scope.startsWith("project:") || scope.startsWith("user:");
    }
    getAccessibleScopes(agentId) {
        if (!agentId)
            return this.getAllScopes();
        const explicitAccess = this.config.agentAccess[agentId];
        if (explicitAccess)
            return explicitAccess;
        const defaultScopes = ["global"];
        const agentScope = SCOPE_PATTERNS.AGENT(agentId);
        if (this.config.definitions[agentScope] || this.isBuiltInScope(agentScope)) {
            defaultScopes.push(agentScope);
        }
        return defaultScopes;
    }
    getDefaultScope(agentId) {
        if (!agentId)
            return this.config.default;
        const agentScope = SCOPE_PATTERNS.AGENT(agentId);
        const accessibleScopes = this.getAccessibleScopes(agentId);
        if (accessibleScopes.includes(agentScope))
            return agentScope;
        return this.config.default;
    }
    isAccessible(scope, agentId) {
        if (!agentId)
            return this.validateScope(scope);
        return this.getAccessibleScopes(agentId).includes(scope);
    }
    validateScope(scope) {
        if (!scope || typeof scope !== "string" || scope.trim().length === 0)
            return false;
        return this.config.definitions[scope.trim()] !== undefined || this.isBuiltInScope(scope.trim());
    }
    getAllScopes() {
        return Object.keys(this.config.definitions);
    }
    getScopeDefinition(scope) {
        return this.config.definitions[scope];
    }
    addScopeDefinition(scope, definition) {
        this.config.definitions[scope] = definition;
    }
    removeScopeDefinition(scope) {
        if (scope === "global")
            throw new Error("Cannot remove global scope");
        if (!this.config.definitions[scope])
            return false;
        delete this.config.definitions[scope];
        for (const [agentId, scopes] of Object.entries(this.config.agentAccess)) {
            const filtered = scopes.filter(s => s !== scope);
            if (filtered.length !== scopes.length)
                this.config.agentAccess[agentId] = filtered;
        }
        return true;
    }
    setAgentAccess(agentId, scopes) {
        this.config.agentAccess[agentId] = [...scopes];
    }
    removeAgentAccess(agentId) {
        if (!this.config.agentAccess[agentId])
            return false;
        delete this.config.agentAccess[agentId];
        return true;
    }
    exportConfig() {
        return JSON.parse(JSON.stringify(this.config));
    }
    getStats() {
        const scopes = this.getAllScopes();
        const scopesByType = { global: 0, agent: 0, custom: 0, project: 0, user: 0, other: 0 };
        for (const scope of scopes) {
            if (scope === "global")
                scopesByType.global++;
            else if (scope.startsWith("agent:"))
                scopesByType.agent++;
            else if (scope.startsWith("custom:"))
                scopesByType.custom++;
            else if (scope.startsWith("project:"))
                scopesByType.project++;
            else if (scope.startsWith("user:"))
                scopesByType.user++;
            else
                scopesByType.other++;
        }
        return { totalScopes: scopes.length, agentsWithCustomAccess: Object.keys(this.config.agentAccess).length, scopesByType };
    }
}
export function createScopeManager(config) {
    return new MemoryScopeManager(config);
}
export function parseScopeId(scope) {
    if (scope === "global")
        return { type: "global", id: "" };
    const colonIndex = scope.indexOf(":");
    if (colonIndex === -1)
        return null;
    return { type: scope.substring(0, colonIndex), id: scope.substring(colonIndex + 1) };
}
//# sourceMappingURL=scopes.js.map