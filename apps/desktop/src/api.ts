export const CORE_URL = import.meta.env.VITE_CORE_URL ?? "http://127.0.0.1:4317";

export type Board = {
  id: string;
  name: string;
  mcuFamily: string;
};

export type Diagnostic = {
  file: string;
  line: number;
  column: number;
  severity: string;
  message: string;
};

export type BuildResponse = {
  status: "success" | "failed";
  diagnostics: Diagnostic[];
  durationMs: number;
  rawOutput?: string;
};

export type HealthResponse = {
  status: "ok";
  version: string;
  uptimeMs: number;
};

export type ExtensionInfo = {
  id: string;
  name: string;
  capabilities: string[];
};

export type ExtensionsResponse = {
  extensions: ExtensionInfo[];
  extensionsDir: string;
};

export type AuditEntry = {
  timestamp: string;
  extensionId: string;
  capability: string;
  action: "denied";
};

export type AuditResponse = {
  entries: AuditEntry[];
  total: number;
  limit?: number;
  offset?: number;
  extensionsDir: string;
  extensionId?: string;
};

export type ExtensionRunResponse = {
  ok: boolean;
  output?: unknown;
  durationMs: number;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    if (details !== undefined) {
      this.details = details;
    }
  }
}

export function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    return `${err.status} ${err.code}: ${err.message}`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "unknown error";
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${CORE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "network error";
    throw new ApiError(0, "NETWORK_ERROR", message);
  }
  const data = (await res.json().catch(() => ({}))) as {
    code?: string;
    message?: string;
    details?: unknown;
  };
  if (!res.ok) {
    throw new ApiError(res.status, data.code ?? "HTTP_ERROR", data.message || `HTTP ${res.status}`, data.details);
  }
  return data as T;
}
