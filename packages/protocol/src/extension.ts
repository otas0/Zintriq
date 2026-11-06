import { z } from "zod";

export const ExtensionCapabilitySchema = z.enum([
  "fs.read",
  "fs.write",
  "net",
  "serial",
  "process",
]);
export type ExtensionCapability = z.infer<typeof ExtensionCapabilitySchema>;

export const ExtensionManifestSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    version: z.string().min(1),
    capabilities: z.array(ExtensionCapabilitySchema).default([]),
    entryWasm: z.string().min(1),
  })
  .strict();
export type ExtensionManifest = z.infer<typeof ExtensionManifestSchema>;

export const ExtensionRunRequestSchema = z
  .object({
    input: z.unknown().optional(),
    timeoutMs: z.number().int().positive().default(5_000),
    memoryLimitMb: z.number().int().positive().default(32),
  })
  .strict();
export type ExtensionRunRequest = z.infer<typeof ExtensionRunRequestSchema>;

export const ExtensionRunResultSchema = z
  .object({
    ok: z.boolean(),
    output: z.unknown().optional(),
    error: z
      .object({
        code: z.string().min(1),
        message: z.string().min(1),
        details: z.unknown().optional(),
      })
      .strict()
      .optional(),
    durationMs: z.number().nonnegative(),
  })
  .strict();
export type ExtensionRunResult = z.infer<typeof ExtensionRunResultSchema>;
