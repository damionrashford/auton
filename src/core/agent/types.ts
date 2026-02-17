export type ToolHandler = (args: Record<string, unknown>) => Promise<string> | string;
export type ToolExecutor = Record<string, ToolHandler>;
