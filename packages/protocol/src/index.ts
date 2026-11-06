export const PROTOCOL_VERSION = 1 as const;

export {
  BoardConfigSchema,
  McuFamilySchema,
  PeripheralSchema,
  ToolchainSchema,
  type BoardConfig,
  type McuFamily,
  type Peripheral,
  type Toolchain,
} from "./board.js";

export {
  BuildFileSchema,
  BuildRequestSchema,
  BuildResultSchema,
  DiagnosticSchema,
  DiagnosticSeveritySchema,
  type BuildFile,
  type BuildRequest,
  type BuildResult,
  type Diagnostic,
  type DiagnosticSeverity,
} from "./build.js";

export {
  ExtensionCapabilitySchema,
  ExtensionManifestSchema,
  ExtensionRunRequestSchema,
  ExtensionRunResultSchema,
  type ExtensionCapability,
  type ExtensionManifest,
  type ExtensionRunRequest,
  type ExtensionRunResult,
} from "./extension.js";

export { ValidationError, validateOrThrow } from "./validate.js";
