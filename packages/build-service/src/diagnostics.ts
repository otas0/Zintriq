import type { Diagnostic, DiagnosticSeverity } from "@zintriq/protocol";

const LINE =
  /^(.*?):(\d+):(?:(\d+):)?\s*(fatal error|error|warning|note):\s*(.+)$/;

function severityOf(kind: string): DiagnosticSeverity {
  if (kind === "warning") return "warning";
  if (kind === "note") return "note";
  return "error";
}

export function parseCompilerDiagnostics(output: string, fallbackFile: string): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  for (const rawLine of output.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const match = LINE.exec(line);
    if (!match) continue;
    const file = match[1] || fallbackFile;
    const lineNo = Number(match[2]);
    const column = match[3] ? Number(match[3]) : 1;
    const kind = match[4] ?? "error";
    const message = (match[5] ?? "").trim();
    if (!file || !Number.isInteger(lineNo) || lineNo < 1 || !message) continue;
    diagnostics.push({
      file,
      line: lineNo,
      column: Number.isInteger(column) && column > 0 ? column : 1,
      severity: severityOf(kind),
      message,
    });
  }
  return diagnostics;
}
