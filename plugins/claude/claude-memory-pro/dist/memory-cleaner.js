/**
 * Memory Cleaner Module
 * Contextual summarization + stored memory cleanup
 */
const NOISE_PATTERNS = [
    /^Relevant memory:/i,
    /^Current time:/i,
    /^Read HEARTBEAT\.md/i,
    /\[Internal task completion event\]/i,
    /<<<BEGIN_UNTRUSTED_CHILD_RESULT>>>/i,
    /This context is runtime-generated/i,
    /会话即将重置前的关键信息/,
    /\bheartbeat\b/i,
    /\bcron:\b/i,
];
function normalizeWhitespace(value) {
    return String(value || '').replace(/\r/g, '\n').replace(/\t/g, ' ').replace(/[ ]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
}
function extractUrls(text) {
    return [...new Set([...String(text || '').matchAll(/https?:\/\/[^\s)>\]]+/g)].map(m => m[0]))].slice(0, 5);
}
function extractFilePaths(text) {
    return [...new Set([...String(text || '').matchAll(/(?:\/Users\/[^\s"'`]+|~\/[^\s"'`]+)/g)].map(m => m[0]))].slice(0, 5);
}
function compactLine(text, maxChars = 180) {
    const compact = normalizeWhitespace(text);
    if (compact.length <= maxChars)
        return compact;
    return `${compact.slice(0, Math.max(0, maxChars - 1))}…`;
}
function isNoiseLine(line) {
    const normalized = normalizeWhitespace(line);
    if (!normalized)
        return true;
    return NOISE_PATTERNS.some(p => p.test(normalized));
}
function extractConstraints(lines) {
    return lines.filter(line => /(必须|禁止|不要|只要|只需|应当|需要|默认|优先|避免|must|never|avoid|prefer|only)/i.test(line)).slice(0, 3);
}
export function summarizeContextualMemory(primary, options = {}) {
    const maxChars = Math.max(180, Math.min(900, options.maxChars ?? 520));
    const primaryNormalized = normalizeWhitespace(primary);
    const recent = Array.isArray(options.recentContext) ? options.recentContext : [];
    const candidateLines = [
        ...recent.map(item => compactLine(item, 180)),
        compactLine(primaryNormalized, 240),
    ].map(line => normalizeWhitespace(line)).filter(line => line && !isNoiseLine(line));
    const dedupedLines = [...new Set(candidateLines)];
    const focus = dedupedLines[dedupedLines.length - 1] || primaryNormalized;
    const contextLines = dedupedLines.filter(line => line !== focus).slice(-3);
    const constraints = extractConstraints(dedupedLines);
    const urls = extractUrls(`${recent.join('\n')}\n${primaryNormalized}`);
    const filePaths = extractFilePaths(`${recent.join('\n')}\n${primaryNormalized}`);
    const parts = [];
    if (focus)
        parts.push(`Focus: ${compactLine(focus, 220)}`);
    if (contextLines.length > 0)
        parts.push(`Context: ${contextLines.map(l => compactLine(l, 140)).join(' | ')}`);
    if (constraints.length > 0)
        parts.push(`Constraints: ${constraints.map(l => compactLine(l, 120)).join(' | ')}`);
    if (urls.length > 0)
        parts.push(`URLs: ${urls.join(', ')}`);
    if (filePaths.length > 0)
        parts.push(`Files: ${filePaths.join(', ')}`);
    const summary = normalizeWhitespace(parts.join('\n'));
    if (summary.length <= maxChars)
        return summary;
    return `${summary.slice(0, Math.max(0, maxChars - 1))}…`;
}
export function isMemoryNoise(text, source) {
    const normalized = normalizeWhitespace(text);
    if (!normalized)
        return true;
    return NOISE_PATTERNS.some(p => p.test(normalized));
}
function buildDedupeKey(entry) {
    // 用全文（仅去重完全相同的内容）；原来只比前220字符会误删"开头雷同的不同长文"
    return normalizeWhitespace(entry.text).toLowerCase();
}
function parseMetadata(raw) {
    try {
        return raw ? JSON.parse(raw) : {};
    }
    catch {
        return {};
    }
}
export async function cleanupStoredMemories(store, embedder, options = {}) {
    // 删噪/去重便宜，全量扫（否则老记忆里的噪音和重复永远清不到）；压缩烧 embedding，用 limit 封顶
    const compressBudget = Math.max(20, Math.min(500, options.limit ?? 200));
    const entries = await store.listAll();
    const now = Date.now();
    const maxAgeMs = Math.max(1, options.maxAgeDays ?? 90) * 24 * 60 * 60 * 1000;
    const seen = new Map();
    let deleted = 0, cleaned = 0, deduped = 0;
    for (const entry of entries) {
        const metadata = parseMetadata(entry.metadata);
        const source = String(metadata.source || '');
        if (isMemoryNoise(entry.text, source)) {
            if (await store.delete(entry.id).catch(() => false))
                deleted++;
            continue;
        }
        const dedupeKey = `${source}|${entry.category}|${buildDedupeKey(entry)}`;
        const existing = seen.get(dedupeKey);
        if (existing) {
            const keepExisting = (existing.timestamp || 0) >= (entry.timestamp || 0);
            const target = keepExisting ? entry : existing;
            if (await store.delete(target.id).catch(() => false)) {
                deduped++;
                if (!keepExisting)
                    seen.set(dedupeKey, entry);
            }
            continue;
        }
        seen.set(dedupeKey, entry);
        if (now - (entry.timestamp || 0) > maxAgeMs)
            continue;
        if (cleaned >= compressBudget)
            continue;
        const summary = summarizeContextualMemory(entry.text, { maxChars: 420 });
        const normalizedOriginal = normalizeWhitespace(entry.text);
        if (summary && summary !== normalizedOriginal) {
            const vector = await embedder.embedPassage(summary.slice(0, 500));
            const nextMetadata = { ...metadata, cleanedAt: new Date().toISOString(), cleanedBy: 'memory-cleaner' };
            const updated = await store.update(entry.id, { text: summary, vector, metadata: JSON.stringify(nextMetadata) }).catch(() => null);
            if (updated)
                cleaned++;
        }
    }
    return { scanned: entries.length, deleted, cleaned, deduped };
}
//# sourceMappingURL=memory-cleaner.js.map