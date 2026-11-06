import { describe, expect, it } from "vitest";
import { createLspClient, decodeJsonRpc, type LspTransport } from "./index.js";

class MockTransport implements LspTransport {
  sent: string[] = [];
  private handler: ((payload: string) => void) | undefined;
  closed = false;

  send(payload: string) {
    this.sent.push(payload);
    const message = decodeJsonRpc(payload);
    if (message.method === "textDocument/didOpen") {
      this.push("file:///work/main.cpp", "first", 1);
    }
    if (message.method === "textDocument/didChange") {
      this.push("file:///work/main.cpp", "updated", 2);
    }
  }

  onMessage(handler: (payload: string) => void) {
    this.handler = handler;
  }

  close() {
    this.closed = true;
  }

  receive(payload: string) {
    this.handler?.(payload);
  }

  push(uri: string, message: string, severity: number) {
    this.receive(
      JSON.stringify({
        jsonrpc: "2.0",
        method: "textDocument/publishDiagnostics",
        params: {
          uri,
          diagnostics: [
            {
              range: { start: { line: 0, character: 0 }, end: { line: 0, character: 1 } },
              severity,
              message,
            },
          ],
        },
      }),
    );
  }
}

describe("createLspClient", () => {
  it("completes the initialize handshake", async () => {
    const transport = new MockTransport();
    const client = createLspClient({
      rootUri: "file:///work",
      languageId: "cpp",
      transport,
    });
    const pending = client.initialize();
    const init = decodeJsonRpc(transport.sent[0] ?? "");
    expect(init.method).toBe("initialize");
    expect(init.jsonrpc).toBe("2.0");
    transport.receive(JSON.stringify({ jsonrpc: "2.0", id: init.id, result: { capabilities: {} } }));
    await expect(pending).resolves.toEqual({ capabilities: {} });
    expect(decodeJsonRpc(transport.sent[1] ?? "").method).toBe("initialized");
  });

  it("delivers diagnostics after didOpen", () => {
    const transport = new MockTransport();
    const client = createLspClient({
      rootUri: "file:///work",
      languageId: "cpp",
      transport,
    });
    const seen: string[] = [];
    client.onDiagnostics((event) => {
      seen.push(`${event.uri}:${event.diagnostics[0]?.message ?? ""}`);
    });
    client.didOpen("file:///work/main.cpp", "int main(){return 0;}\n");
    expect(seen).toEqual(["file:///work/main.cpp:first"]);
  });

  it("updates diagnostics after didChange", () => {
    const transport = new MockTransport();
    const client = createLspClient({
      rootUri: "file:///work",
      languageId: "cpp",
      transport,
    });
    const messages: string[] = [];
    client.onDiagnostics((event) => {
      const diag = event.diagnostics[0];
      if (diag) messages.push(`${diag.severity}:${diag.message}`);
    });
    client.didOpen("file:///work/main.cpp", "int main(){return 0;}\n");
    client.didChange("file:///work/main.cpp", "int main(){return 1;}\n", 2);
    expect(messages).toEqual(["1:first", "2:updated"]);
  });

  it("drops listeners on dispose", () => {
    const transport = new MockTransport();
    const client = createLspClient({
      rootUri: "file:///work",
      languageId: "cpp",
      transport,
    });
    let calls = 0;
    client.onDiagnostics(() => {
      calls += 1;
    });
    client.dispose();
    expect(transport.closed).toBe(true);
    transport.push("file:///work/main.cpp", "late", 1);
    expect(calls).toBe(0);
    expect(() => client.didOpen("file:///work/main.cpp", "int main(){return 0;}\n")).toThrow(/disposed/);
  });
});
