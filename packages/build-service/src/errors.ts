export const BUILD_TIMEOUT = "BUILD_TIMEOUT";
export const COMPILER_NOT_FOUND = "COMPILER_NOT_FOUND";

export class BuildServiceError extends Error {
  readonly code: string;
  readonly details?: unknown;

  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.name = "BuildServiceError";
    this.code = code;
    this.details = details;
  }
}
