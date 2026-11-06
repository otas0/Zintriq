import { z } from "zod";

export const BuildFileSchema = z
  .object({
    path: z.string().min(1),
    content: z.string(),
  })
  .strict();
export type BuildFile = z.infer<typeof BuildFileSchema>;

export const BuildRequestSchema = z
  .object({
    boardId: z.string().min(1),
    files: z.array(BuildFileSchema).min(1),
    entryFile: z.string().min(1),
  })
  .strict();
export type BuildRequest = z.infer<typeof BuildRequestSchema>;

export const DiagnosticSeveritySchema = z.enum(["error", "warning", "note", "info"]);
export type DiagnosticSeverity = z.infer<typeof DiagnosticSeveritySchema>;

export const DiagnosticSchema = z
  .object({
    file: z.string().min(1),
    line: z.number().int().positive(),
    column: z.number().int().positive(),
    severity: DiagnosticSeveritySchema,
    message: z.string().min(1),
  })
  .strict();
export type Diagnostic = z.infer<typeof DiagnosticSchema>;

export const BuildResultSchema = z
  .object({
    status: z.enum(["success", "failed"]),
    diagnostics: z.array(DiagnosticSchema),
    durationMs: z.number().nonnegative(),
    rawOutput: z.string().optional(),
  })
  .strict();
export type BuildResult = z.infer<typeof BuildResultSchema>;
