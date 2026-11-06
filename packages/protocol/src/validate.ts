import type { z, ZodTypeAny } from "zod";

export class ValidationError extends Error {
  readonly issues: unknown;

  constructor(message: string, issues: unknown) {
    super(message);
    this.name = "ValidationError";
    this.issues = issues;
  }
}

export function validateOrThrow<S extends ZodTypeAny>(
  schema: S,
  value: unknown,
  label = "value",
): z.output<S> {
  const parsed = schema.safeParse(value);
  if (!parsed.success) {
    throw new ValidationError(`${label} failed validation`, parsed.error.flatten());
  }
  return parsed.data;
}
