export class HalRegistryError extends Error {
  readonly code: string;
  readonly details?: unknown;

  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.name = "HalRegistryError";
    this.code = code;
    this.details = details;
  }
}
