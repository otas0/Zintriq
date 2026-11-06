export const EXTENSION_TIMEOUT = "EXTENSION_TIMEOUT";
export const EXTENSION_OOM = "EXTENSION_OOM";
export const CAPABILITY_DENIED = "CAPABILITY_DENIED";

export class CapabilityDeniedError extends Error {
  readonly code = CAPABILITY_DENIED;
  readonly extensionId: string;
  readonly capability: string;

  constructor(extensionId: string, capability: string) {
    super(`capability denied: ${capability}`);
    this.name = "CapabilityDeniedError";
    this.extensionId = extensionId;
    this.capability = capability;
  }
}
