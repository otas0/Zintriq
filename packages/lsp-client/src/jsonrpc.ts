import type { JsonRpcMessage } from "./types.js";

export function encodeJsonRpc(message: JsonRpcMessage): string {
  return JSON.stringify({ jsonrpc: "2.0", ...message });
}

export function decodeJsonRpc(payload: string): JsonRpcMessage {
  const value = JSON.parse(payload) as JsonRpcMessage;
  if (!value || typeof value !== "object" || value.jsonrpc !== "2.0") {
    throw new Error("invalid json-rpc message");
  }
  return value;
}
