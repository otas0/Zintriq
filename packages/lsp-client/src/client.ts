import { decodeJsonRpc, encodeJsonRpc } from "./jsonrpc.js";
import { createStdioTransport } from "./stdio.js";
import type { DiagnosticEvent, JsonRpcMessage, LspClientConfig, LspTransport } from "./types.js";

type Pending = { resolve: (value: unknown) => void; reject: (err: Error) => void };

export type LspClient = {
  initialize(): Promise<unknown>;
  didOpen(uri: string, text: string, version?: number): void;
  didChange(uri: string, text: string, version: number): void;
  didClose(uri: string): void;
  onDiagnostics(handler: (event: DiagnosticEvent) => void): () => void;
  dispose(): void;
};

function openTransport(config: LspClientConfig): LspTransport {
  if (config.transport) return config.transport;
  if (config.server) return createStdioTransport(config.server.command, config.server.args ?? []);
  throw new Error("createLspClient requires transport or server");
}

export function createLspClient(config: LspClientConfig): LspClient {
  const transport = openTransport(config);
  let nextId = 1;
  const pending = new Map<number, Pending>();
  const diagnosticHandlers = new Set<(event: DiagnosticEvent) => void>();
  let disposed = false;

  transport.onMessage((payload) => {
    if (disposed) return;
    const message = decodeJsonRpc(payload);
    if (message.id != null && message.method == null) {
      const wait = pending.get(Number(message.id));
      if (!wait) return;
      pending.delete(Number(message.id));
      if (message.error) {
        wait.reject(new Error(message.error.message));
        return;
      }
      wait.resolve(message.result);
      return;
    }
    if (message.method === "textDocument/publishDiagnostics") {
      const params = message.params as DiagnosticEvent | undefined;
      const event: DiagnosticEvent = {
        uri: params?.uri ?? "",
        diagnostics: params?.diagnostics ?? [],
      };
      for (const handler of diagnosticHandlers) handler(event);
    }
  });

  function request(method: string, params: unknown): Promise<unknown> {
    if (disposed) return Promise.reject(new Error("LSP client is disposed"));
    const id = nextId++;
    const message: JsonRpcMessage = { id, method, params };
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      transport.send(encodeJsonRpc(message));
    });
  }

  function notify(method: string, params: unknown): void {
    if (disposed) throw new Error("LSP client is disposed");
    transport.send(encodeJsonRpc({ method, params }));
  }

  return {
    initialize() {
      return request("initialize", {
        processId: null,
        rootUri: config.rootUri,
        capabilities: {},
      }).then(async (result) => {
        notify("initialized", {});
        return result;
      });
    },
    didOpen(uri, text, version = 1) {
      notify("textDocument/didOpen", {
        textDocument: { uri, languageId: config.languageId, version, text },
      });
    },
    didChange(uri, text, version) {
      notify("textDocument/didChange", {
        textDocument: { uri, version },
        contentChanges: [{ text }],
      });
    },
    didClose(uri) {
      notify("textDocument/didClose", { textDocument: { uri } });
    },
    onDiagnostics(handler) {
      diagnosticHandlers.add(handler);
      return () => {
        diagnosticHandlers.delete(handler);
      };
    },
    dispose() {
      disposed = true;
      for (const [id, wait] of pending) {
        pending.delete(id);
        wait.reject(new Error("LSP client disposed"));
      }
      diagnosticHandlers.clear();
      transport.close();
    },
  };
}
