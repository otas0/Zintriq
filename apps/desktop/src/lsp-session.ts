type DiagnosticEvent = {
  uri: string;
  diagnostics: { message: string; severity?: number }[];
};

type LspClient = {
  initialize(): Promise<unknown>;
  didOpen(uri: string, text: string): void;
  onDiagnostics(handler: (event: DiagnosticEvent) => void): () => void;
  dispose(): void;
};

type Handler = (payload: string) => void;

type TauriBridge = {
  core?: {
    invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
  };
  event?: {
    listen?: (event: string, handler: (event: { payload: string }) => void) => Promise<() => void>;
  };
};

function tauriBridge(): TauriBridge | undefined {
  return (window as unknown as { __TAURI__?: TauriBridge }).__TAURI__;
}

function toFileUri(pathOrUri: string): string {
  if (pathOrUri.startsWith("file:")) return pathOrUri;
  const normalized = pathOrUri.replace(/\\/g, "/");
  return normalized.startsWith("/") ? `file://${normalized}` : `file:///${normalized}`;
}

/** Browser-safe mock LSP. Does not import Node transports or spawn clangd/pylsp. */
export function connectMockLsp(rootUri: string, languageId: string): Promise<{ client: LspClient }> {
  let handler: Handler | undefined;
  let disposed = false;
  const diagnosticHandlers = new Set<(event: DiagnosticEvent) => void>();
  let nextId = 1;
  const pending = new Map<number, { resolve: (value: unknown) => void; reject: (err: Error) => void }>();

  function send(obj: Record<string, unknown>) {
    const payload = JSON.stringify({ jsonrpc: "2.0", ...obj });
    queueMicrotask(() => onPayload(payload));
  }

  function onPayload(payload: string) {
    if (disposed) return;
    const message = JSON.parse(payload) as {
      id?: number;
      method?: string;
      params?: unknown;
      result?: unknown;
      error?: { message: string };
    };
    if (message.id != null && message.method == null) {
      const wait = pending.get(Number(message.id));
      if (!wait) return;
      pending.delete(Number(message.id));
      if (message.error) wait.reject(new Error(message.error.message));
      else wait.resolve(message.result);
      return;
    }
    if (message.method === "textDocument/publishDiagnostics") {
      const params = message.params as DiagnosticEvent;
      for (const fn of diagnosticHandlers) fn(params);
    }
  }

  const client: LspClient = {
    initialize() {
      const id = nextId++;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        queueMicrotask(() => {
          handler?.(`{"jsonrpc":"2.0","id":${id},"result":{"capabilities":{"textDocumentSync":1}}}`);
        });
        void rootUri;
        void languageId;
      }).then((result) => {
        send({ method: "initialized", params: {} });
        return result;
      });
    },
    didOpen(uri, text) {
      const bad = /return\s*}/.test(text) || text.includes("BROKEN");
      queueMicrotask(() => {
        const event: DiagnosticEvent = {
          uri,
          diagnostics: bad ? [{ message: "mock: expected expression", severity: 1 }] : [],
        };
        for (const fn of diagnosticHandlers) fn(event);
      });
    },
    onDiagnostics(fn) {
      diagnosticHandlers.add(fn);
      return () => {
        diagnosticHandlers.delete(fn);
      };
    },
    dispose() {
      disposed = true;
      diagnosticHandlers.clear();
      pending.clear();
      handler = undefined;
    },
  };

  handler = onPayload;
  return client.initialize().then(() => ({ client }));
}

export type ClangdSession = {
  available: boolean;
  path?: string;
  message: string;
  client?: LspClient;
  compileCommandsDir?: string;
};

export type ClangdConnectOptions = {
  rootUri: string;
  languageId: string;
  /** Absolute filesystem path for workspace / compile_commands lookup. */
  workspaceRoot?: string;
};

/**
 * Explicit clangd sidecar over Tauri stdio. Spawns clangd, frames JSON-RPC,
 * and never auto-connects on edit.
 */
export async function connectClangdSidecar(options: ClangdConnectOptions): Promise<ClangdSession> {
  const { rootUri, languageId, workspaceRoot } = options;
  const bridge = tauriBridge();
  if (!bridge?.core?.invoke || !bridge.event?.listen) {
    return {
      available: false,
      message: "clangd sidecar 仅在 Tauri 桌面壳可用；浏览器请继续用 mock。",
    };
  }

  const invoke = bridge.core.invoke;
  const listen = bridge.event.listen;
  const fileRoot = toFileUri(workspaceRoot ?? rootUri);

  try {
    const started = (await invoke("start_clangd", {
      workspaceRoot: workspaceRoot ?? null,
    })) as { path: string; compileCommandsDir?: string | null };
    const path = started.path;
    let disposed = false;
    const diagnosticHandlers = new Set<(event: DiagnosticEvent) => void>();
    let nextId = 1;
    const pending = new Map<number, { resolve: (value: unknown) => void; reject: (err: Error) => void }>();

    const unlisten = await listen("lsp-message", (event) => {
      if (disposed) return;
      const message = JSON.parse(event.payload) as {
        id?: number;
        method?: string;
        params?: unknown;
        result?: unknown;
        error?: { message: string };
      };
      if (message.id != null && message.method == null) {
        const wait = pending.get(Number(message.id));
        if (!wait) return;
        pending.delete(Number(message.id));
        if (message.error) wait.reject(new Error(message.error.message));
        else wait.resolve(message.result);
        return;
      }
      if (message.method === "textDocument/publishDiagnostics") {
        const params = message.params as DiagnosticEvent;
        for (const fn of diagnosticHandlers) fn(params);
      }
    });

    function sendRaw(obj: Record<string, unknown>) {
      void invoke("lsp_send", { payload: JSON.stringify({ jsonrpc: "2.0", ...obj }) });
    }

    const client: LspClient = {
      initialize() {
        const id = nextId++;
        return new Promise((resolve, reject) => {
          pending.set(id, { resolve, reject });
          sendRaw({
            id,
            method: "initialize",
            params: {
              processId: null,
              rootUri: fileRoot,
              capabilities: {
                workspace: { workspaceFolders: true },
              },
              initializationOptions: started.compileCommandsDir
                ? { compilationDatabasePath: started.compileCommandsDir }
                : {},
              workspaceFolders: [
                {
                  uri: fileRoot,
                  name: (workspaceRoot ?? rootUri).split(/[/\\]/).filter(Boolean).pop() ?? "workspace",
                },
              ],
            },
          });
        }).then((result) => {
          sendRaw({ method: "initialized", params: {} });
          sendRaw({
            method: "workspace/didChangeWorkspaceFolders",
            params: {
              event: {
                added: [{ uri: fileRoot, name: "workspace" }],
                removed: [],
              },
            },
          });
          return result;
        });
      },
      didOpen(uri, text) {
        sendRaw({
          method: "textDocument/didOpen",
          params: {
            textDocument: { uri, languageId, version: 1, text },
          },
        });
      },
      onDiagnostics(fn) {
        diagnosticHandlers.add(fn);
        return () => {
          diagnosticHandlers.delete(fn);
        };
      },
      dispose() {
        disposed = true;
        diagnosticHandlers.clear();
        pending.clear();
        unlisten();
        void invoke("stop_clangd");
      },
    };

    await client.initialize();
    const ccNote = started.compileCommandsDir
      ? ` compile_commands: ${started.compileCommandsDir}`
      : "（未找到 compile_commands.json，clangd 将用启发式）";
    return {
      available: true,
      path,
      message: `已连接 clangd stdio sidecar：${path}。workspaceFolders 已声明。${ccNote} 仅显式连接；编辑不自动请求。`,
      client,
      ...(started.compileCommandsDir ? { compileCommandsDir: started.compileCommandsDir } : {}),
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { available: false, message: `clangd sidecar 不可用：${message}` };
  }
}

/** @deprecated use connectClangdSidecar */
export async function probeClangdSidecar(): Promise<{ available: boolean; path?: string; message: string }> {
  const session = await connectClangdSidecar({ rootUri: "file:///", languageId: "cpp" });
  session.client?.dispose();
  return session.path
    ? { available: session.available, path: session.path, message: session.message }
    : { available: session.available, message: session.message };
}

export type { DiagnosticEvent, LspClient };
