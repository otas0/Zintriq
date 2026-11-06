import { z } from "zod";

export const McuFamilySchema = z.enum(["esp32", "stm32", "rp2040"]);
export type McuFamily = z.infer<typeof McuFamilySchema>;

export const ToolchainSchema = z
  .object({
    compiler: z.string().min(1),
    flags: z.array(z.string()).default([]),
  })
  .strict();
export type Toolchain = z.infer<typeof ToolchainSchema>;

export const PeripheralSchema = z
  .object({
    name: z.string().min(1),
    kind: z.string().min(1),
    pins: z.array(z.string().min(1)).default([]),
  })
  .strict();
export type Peripheral = z.infer<typeof PeripheralSchema>;

export const BoardConfigSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    mcuFamily: McuFamilySchema,
    toolchain: ToolchainSchema,
    pins: z.record(z.string().min(1), z.string().min(1)),
    peripherals: z.array(PeripheralSchema).default([]),
  })
  .strict();
export type BoardConfig = z.infer<typeof BoardConfigSchema>;
