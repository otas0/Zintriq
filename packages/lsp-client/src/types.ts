export type LspPosition = { line: number; character: number };

export type LspRange = { start: LspPosition; end: LspPosition };

export type LspDiagnostic = {
  range: LspRange;
  message: string;
  severity?: number;
  source?: string;
};

export type JsonRpcMessage = {
  jsonrpc?: "2.0";
  id?: number | string;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: { code: number; message: string };
};

export type DiagnosticEvent = {
  uri: string;
  diagnostics: LspDiagnostic[];
};

export type LspTransport = {
  send(payload: string): void;
  onMessage(handler: (payload: string) => void): void;
  close(): void;
};

export type LspServerConfig = {
  command: string;
  args?: string[];
};

export type LspClientConfig = {
  rootUri: string;
  languageId: string;
  transport?: LspTransport;
  server?: LspServerConfig;
};

export type DapClientConfig = {
  command?: string;
  args?: string[];
};

export type DapClient = {
  readonly status: "unimplemented";
};
