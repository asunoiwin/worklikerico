/**
 * Adaptive Retrieval
 * Determines whether a query needs memory retrieval.
 * Skips retrieval for greetings, commands, simple instructions.
 */
export declare function shouldSkipRetrieval(query: string): boolean;
