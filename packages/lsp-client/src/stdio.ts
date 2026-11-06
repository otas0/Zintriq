import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { LspTransport } from "./types.js";

export function createStdioTransport(command: string, args: string[] = []): LspTransport {
  const child: ChildProcessWithoutNullStreams = spawn(command, args, { stdio: "pipe" });
  let buffer = Buffer.alloc(0);
  let handler: ((payload: string) => void) | undefined;

  const tryRead = () => {
    while (true) {
      const headerEnd = buffer.indexOf("\r\n\r\n");
      if (headerEnd < 0) return;
      const header = buffer.subarray(0, headerEnd).toString("utf8");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match?.[1]) {
        throw new Error("LSP stream missing Content-Length");
      }
      const length = Number(match[1]);
      const start = headerEnd + 4;
      if (buffer.length < start + length) return;
      const body = buffer.subarray(start, start + length).toString("utf8");
      buffer = buffer.subarray(start + length);
      handler?.(body);
    }
  };

  child.stdout.on("data", (chunk: Buffer) => {
    buffer = Buffer.concat([buffer, chunk]);
    tryRead();
  });
  child.on("error", (err) => {
    throw err;
  });

  return {
    send(payload) {
      const packet = `Content-Length: ${Buffer.byteLength(payload)}\r\n\r\n${payload}`;
      child.stdin.write(packet);
    },
    onMessage(next) {
      handler = next;
    },
    close() {
      handler = undefined;
      child.kill();
    },
  };
}
