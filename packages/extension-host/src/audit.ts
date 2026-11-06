import pino from "pino";

export type AuditEntry = {
  timestamp: string;
  extensionId: string;
  capability: string;
  action: "denied";
};

const entries: AuditEntry[] = [];

const logger = pino({ level: process.env.LOG_LEVEL ?? "info" });

export function recordAudit(entry: AuditEntry): void {
  entries.push(entry);
  logger.info(entry, "extension capability denied");
}

export function getAuditLog(): readonly AuditEntry[] {
  return entries;
}

export function clearAuditLog(): void {
  entries.length = 0;
}
