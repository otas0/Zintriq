import Fastify from "fastify";
import { buildApp } from "./server.js";

const port = Number(process.env.PORT ?? 4317);
const host = "127.0.0.1";

try {
  const app = await buildApp();
  await app.listen({ port, host });
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  const fatal = Fastify({ logger: { level: process.env.LOG_LEVEL ?? "info" } });
  fatal.log.error({ err: message }, "core-service failed to start");
  await fatal.close();
  process.exit(1);
}
