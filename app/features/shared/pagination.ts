export type PageResult<T> = { total: number; limit: number; offset: number; items: T[]; trace_level?: string };
