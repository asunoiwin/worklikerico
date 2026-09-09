/**
 * Noise Filter - filters out low-quality memories
 */
export declare function isNoise(text: string): boolean;
export declare function filterNoise<T>(items: T[], getText: (item: T) => string): T[];
