import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { spawn } from "node:child_process";
import type { BoardConfig, BuildRequest } from "@zintriq/protocol";
import { afterEach, describe, expect, it, vi } from "vitest";
import { compileCheck } from "./compile.js";
import { BUILD_TIMEOUT, COMPILER_NOT_FOUND } from "./errors.js";

vi.mock("node:child_process", () => ({
  spawn: vi.fn(),
}));

const spawnMock = vi.mocked(spawn);

const board: BoardConfig = {
  id: "esp32",
  name: "ESP32",
  mcuFamily: "esp32",
  toolchain: { compiler: "g++", flags: ["-std=c++17", "-fsyntax-only"] },
  pins: { LED: "GPIO2" },
  peripherals: [],
};

const request: BuildRequest = {
  boardId: "esp32",
  entryFile: "src/main.cpp",
  files: [{ path: "src/main.cpp", content: "int main(){return 0;}\n" }],
};

type FakeChild = EventEmitter & {
  stdout: EventEmitter;
  stderr: EventEmitter;
  kill: ReturnType<typeof vi.fn>;
};

function fakeChild(): FakeChild {
  const stdout = new EventEmitter();
  const stderr = new EventEmitter();
  const child = new EventEmitter() as FakeChild;
  child.stdout = stdout;
  child.stderr = stderr;
  const markEncoding = (stream: EventEmitter) => {
    (stream as EventEmitter & { setEncoding: (encoding: string) => void }).setEncoding = () => {};
  };
  markEncoding(stdout);
  markEncoding(stderr);
  child.kill = vi.fn(() => {
    setImmediate(() => child.emit("close", null));
    return true;
  });
  return child;
}

afterEach(() => {
  spawnMock.mockReset();
});

describe("compileCheck", () => {
  it("writes sources and returns success when g++ exits 0", async () => {
    spawnMock.mockImplementation((command, args, options) => {
      const cwd = (options as { cwd: string }).cwd;
      const text = readFileSync(join(cwd, "src/main.cpp"), "utf8");
      expect(text).toContain("int main");
      expect(command).toBe("g++");
      expect(args).toEqual(["-std=c++17", "-fsyntax-only", "src/main.cpp"]);
      const child = fakeChild();
      setImmediate(() => child.emit("close", 0));
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board);
    expect(result.status).toBe("success");
    expect(result.diagnostics).toEqual([]);
    expect(result.durationMs).toBeGreaterThanOrEqual(0);
    expect(spawnMock).toHaveBeenCalledOnce();
  });

  it("parses g++ diagnostics when the compiler exits non-zero", async () => {
    spawnMock.mockImplementation(() => {
      const child = fakeChild();
      setImmediate(() => {
        child.stderr.emit("data", "src/main.cpp:3:12: error: expected ';' before '}' token\n");
        child.emit("close", 1);
      });
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board);
    expect(result.status).toBe("failed");
    expect(result.diagnostics).toEqual([
      {
        file: "src/main.cpp",
        line: 3,
        column: 12,
        severity: "error",
        message: "expected ';' before '}' token",
      },
    ]);
  });

  it("kills the compiler and returns BUILD_TIMEOUT", async () => {
    let child: FakeChild | undefined;
    spawnMock.mockImplementation(() => {
      child = fakeChild();
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board, { timeoutMs: 30 });
    expect(child?.kill).toHaveBeenCalledWith("SIGKILL");
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toContain(BUILD_TIMEOUT);
    expect(result.diagnostics[0]?.severity).toBe("error");
  });

  it("returns COMPILER_NOT_FOUND when the compiler cannot be executed", async () => {
    spawnMock.mockImplementation(() => {
      const child = fakeChild();
      setImmediate(() => {
        const err = Object.assign(new Error("spawn g++ ENOENT"), { code: "ENOENT" });
        child.emit("error", err);
      });
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board);
    expect(result.status).toBe("failed");
    expect(result.diagnostics[0]?.message).toContain(COMPILER_NOT_FOUND);
    expect(result.diagnostics[0]?.message).toMatch(/Install g\+\+ or gcc/);
  });

  it("rejects absolute paths and parent traversal before spawning", async () => {
    await expect(
      compileCheck({ ...request, entryFile: "../main.cpp", files: [{ path: "../main.cpp", content: "" }] }, board),
    ).rejects.toThrow(/escapes workspace/);
    await expect(
      compileCheck(
        { ...request, entryFile: "/tmp/main.cpp", files: [{ path: "/tmp/main.cpp", content: "" }] },
        board,
      ),
    ).rejects.toThrow(/unsafe path/);
    expect(spawnMock).not.toHaveBeenCalled();
  });

  it("keeps unparsed stderr as one diagnostic and rawOutput", async () => {
    spawnMock.mockImplementation(() => {
      const child = fakeChild();
      setImmediate(() => {
        child.stderr.emit("data", "internal compiler explosion\n");
        child.emit("close", 2);
      });
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board);
    expect(result.status).toBe("failed");
    expect(result.diagnostics).toEqual([
      {
        file: "src/main.cpp",
        line: 1,
        column: 1,
        severity: "error",
        message: "internal compiler explosion",
      },
    ]);
    expect(result.rawOutput).toContain("internal compiler explosion");
  });

  it("logs cleanup failures without replacing the compile result", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    spawnMock.mockImplementation(() => {
      const child = fakeChild();
      setImmediate(() => child.emit("close", 0));
      return child as unknown as ReturnType<typeof spawn>;
    });

    const result = await compileCheck(request, board, {
      removeDir: async () => {
        throw new Error("device busy");
      },
    });
    expect(result.status).toBe("success");
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("build temp cleanup failed"));
    errorSpy.mockRestore();
  });
});
