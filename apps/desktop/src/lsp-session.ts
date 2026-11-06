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
        // Simulate server reply; no stdio process.
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
          diagnostics: bad
            ? [{ message: "mock: expected expression", severity: 1 }]
            : [],
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

export type { DiagnosticEvent, LspClient };
