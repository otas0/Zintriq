import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor as MonacoEditor } from "monaco-editor";
import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchJson,
  formatApiError,
  type Board,
  type BuildResponse,
  type Diagnostic,
  type ExtensionInfo,
  type ExtensionRunResponse,
  type HealthResponse,
} from "./api.js";
import {
  canUseDirectoryPicker,
  createProjectFile,
  openProjectFolder,
  saveProjectFile,
  type ProjectFile,
  type ProjectRoot,
} from "./fs.js";
import { connectMockLsp, type LspClient } from "./lsp-session.js";
import { badgeLabel } from "./model.js";

const STARTER = "int main(){return 0;}\n";
const HEALTH_BANNER = "core-service 未启动，请运行 pnpm --filter core-service dev";

function compilerBanner(message: string): string {
  if (message.includes("BUILD_TIMEOUT")) {
    return "构建超时（BUILD_TIMEOUT）：本地编译器超过时限，请缩短源码或提高 timeoutMs。";
  }
  if (message.includes("COMPILER_NOT_FOUND")) {
    return "未找到编译器（COMPILER_NOT_FOUND）：请安装 g++ 或 gcc，并确保在 PATH 中。";
  }
  return message;
}

export function App() {
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);
  const decorationsRef = useRef<MonacoEditor.IEditorDecorationsCollection | null>(null);
  const pendingJump = useRef<Diagnostic | null>(null);
  const lspRef = useRef<LspClient | null>(null);

  const [root, setRoot] = useState<ProjectRoot>({ name: "memory" });
  const [files, setFiles] = useState<ProjectFile[]>([{ path: "main.cpp", content: STARTER, dirty: false }]);
  const [activePath, setActivePath] = useState("main.cpp");
  const [boards, setBoards] = useState<Board[]>([]);
  const [boardId, setBoardId] = useState("");
  const [status, setStatus] = useState<"idle" | "success" | "failed">("idle");
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [rawOutput, setRawOutput] = useState("");
  const [expandFirst, setExpandFirst] = useState(false);
  const [healthError, setHealthError] = useState("");
  const [boardError, setBoardError] = useState("");
  const [requestError, setRequestError] = useState("");
  const [busy, setBusy] = useState(false);
  const [extensions, setExtensions] = useState<ExtensionInfo[]>([]);
  const [extensionError, setExtensionError] = useState("");
  const [extensionOutput, setExtensionOutput] = useState("");
  const [runningId, setRunningId] = useState("");
  const [lspStatus, setLspStatus] = useState<"off" | "mock" | "error">("off");
  const [lspNote, setLspNote] = useState("");
  const [lspDiags, setLspDiags] = useState<string[]>([]);

  const active = files.find((file) => file.path === activePath) ?? files[0];

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await fetchJson<HealthResponse>("/health");
      } catch (err) {
        if (!cancelled) {
          setHealthError(HEALTH_BANNER);
          setRequestError(formatApiError(err));
        }
        return;
      }
      if (cancelled) return;
      setHealthError("");
      try {
        const boardData = await fetchJson<Board[]>("/boards");
        if (cancelled) return;
        setBoards(boardData);
        setBoardId(boardData[0]?.id ?? "");
        setBoardError("");
      } catch (err) {
        if (!cancelled) setBoardError(formatApiError(err));
      }
      try {
        const extensionData = await fetchJson<ExtensionInfo[]>("/extensions");
        if (!cancelled) {
          setExtensions(extensionData);
          setExtensionError("");
        }
      } catch (err) {
        if (!cancelled) setExtensionError(formatApiError(err));
      }
    })();
    return () => {
      cancelled = true;
      lspRef.current?.dispose();
      lspRef.current = null;
    };
  }, []);

  useEffect(() => {
    const diag = pendingJump.current;
    if (!diag || diag.file !== activePath) return;
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    pendingJump.current = null;
    editor.setPosition({ lineNumber: diag.line, column: diag.column });
    editor.revealPositionInCenter({ lineNumber: diag.line, column: diag.column });
    editor.focus();
    decorationsRef.current?.clear();
    decorationsRef.current = editor.createDecorationsCollection([
      {
        range: new monaco.Range(diag.line, diag.column, diag.line, diag.column + 1),
        options: { isWholeLine: true, className: "diag-highlight" },
      },
    ]);
  }, [activePath, files]);

  function updateActive(content: string) {
    setFiles((current) =>
      current.map((file) =>
        file.path === activePath ? { ...file, content, dirty: true } : file,
      ),
    );
  }

  async function onOpenFolder() {
    try {
      const opened = await openProjectFolder();
      setRoot(opened.root);
      setFiles(opened.files);
      setActivePath(opened.files[0]?.path ?? "main.cpp");
      setRequestError("");
    } catch (err) {
      setRequestError(formatApiError(err));
    }
  }

  async function onNewFile() {
    const name = window.prompt("新文件相对路径", "src/main.cpp");
    if (!name) return;
    try {
      const created = await createProjectFile(root, name, STARTER);
      setFiles((current) => [...current.filter((file) => file.path !== created.path), created]);
      setActivePath(created.path);
    } catch (err) {
      setRequestError(formatApiError(err));
    }
  }

  async function onSave() {
    if (!active) return;
    try {
      const saved = await saveProjectFile(active);
      setFiles((current) => current.map((file) => (file.path === saved.path ? saved : file)));
    } catch (err) {
      setRequestError(formatApiError(err));
    }
  }

  async function checkBuild() {
    if (!active || healthError) return;
    setBusy(true);
    setRequestError("");
    try {
      const result = await fetchJson<BuildResponse>("/build", {
        method: "POST",
        body: JSON.stringify({
          boardId,
          entryFile: active.path,
          files: files.map((file) => ({ path: file.path, content: file.content })),
        }),
      });
      setStatus(result.status);
      setDurationMs(result.durationMs);
      setDiagnostics(result.diagnostics);
      setRawOutput(result.rawOutput ?? "");
      setExpandFirst(result.status === "failed" && result.diagnostics.length > 0);
      const first = result.diagnostics[0];
      if (result.status === "failed" && first) {
        jump(first);
      }
      const timeoutOrMissing = result.diagnostics.find(
        (diag) => diag.message.includes("BUILD_TIMEOUT") || diag.message.includes("COMPILER_NOT_FOUND"),
      );
      if (timeoutOrMissing) {
        setRequestError(compilerBanner(timeoutOrMissing.message));
      }
    } catch (err) {
      setStatus("failed");
      setDurationMs(null);
      setDiagnostics([]);
      setRawOutput("");
      setExpandFirst(false);
      setRequestError(compilerBanner(formatApiError(err)));
    } finally {
      setBusy(false);
    }
  }

  function jump(diag: Diagnostic) {
    const target = files.find((item) => item.path === diag.file);
    if (target && target.path !== activePath) {
      pendingJump.current = diag;
      setActivePath(target.path);
      return;
    }
    pendingJump.current = diag;
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    pendingJump.current = null;
    editor.setPosition({ lineNumber: diag.line, column: diag.column });
    editor.revealPositionInCenter({ lineNumber: diag.line, column: diag.column });
    editor.focus();
    decorationsRef.current?.clear();
    decorationsRef.current = editor.createDecorationsCollection([
      {
        range: new monaco.Range(diag.line, diag.column, diag.line, diag.column + 1),
        options: { isWholeLine: true, className: "diag-highlight" },
      },
    ]);
  }

  async function runGuest(id: string) {
    setRunningId(id);
    setExtensionOutput("");
    try {
      const result = await fetchJson<ExtensionRunResponse>(`/extensions/${id}/run`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setExtensionOutput(JSON.stringify(result.output ?? result));
    } catch (err) {
      if (err instanceof ApiError && err.code === "CAPABILITY_DENIED") {
        setExtensionOutput("扩展未声明该能力");
      } else {
        setExtensionOutput(formatApiError(err));
      }
    } finally {
      setRunningId("");
    }
  }

  async function connectLsp() {
    try {
      lspRef.current?.dispose();
      const session = await connectMockLsp(`file:///${root.name}`, "cpp");
      const client = session.client;
      lspRef.current = client;
      setLspDiags([]);
      client.onDiagnostics((event) => {
        setLspDiags(event.diagnostics.map((diag) => `${event.uri}: ${diag.message}`));
      });
      if (active) {
        client.didOpen(`file:///${active.path}`, active.content);
      }
      setLspStatus("mock");
      setLspNote("已连接 mock LSP。本机 clangd/pylsp 仅通过 packages/lsp-client 探测，CI 与桌面默认不启动真实进程。");
    } catch (err) {
      setLspStatus("error");
      setLspNote(formatApiError(err));
    }
  }

  function isRawDiagnostic(diag: Diagnostic): boolean {
    return rawOutput.length > 0 && diag.message === rawOutput.trim();
  }

  return (
    <div className="app">
      <header className="toolbar">
        <span data-testid="core-status">{healthError ? "offline" : "ok"}</span>
        <span data-testid="project-root">{root.name}</span>
        <button type="button" onClick={() => void onOpenFolder()} disabled={!canUseDirectoryPicker()}>
          打开文件夹
        </button>
        <button type="button" onClick={() => void onNewFile()}>
          新建文件
        </button>
        <button type="button" onClick={() => void onSave()} disabled={!active}>
          保存{active?.dirty ? " *" : ""}
        </button>
        <label>
          开发板{" "}
          <select
            aria-label="开发板"
            value={boardId}
            onChange={(event) => setBoardId(event.target.value)}
            disabled={Boolean(healthError) || boards.length === 0}
          >
            {boards.map((board) => (
              <option key={board.id} value={board.id}>
                {board.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => void checkBuild()} disabled={busy || Boolean(healthError) || !boardId}>
          {busy ? "检查中" : "构建检查"}
        </button>
        <button type="button" onClick={() => void connectLsp()}>
          连接语言服务
        </button>
        <span className={`badge ${status}`} data-testid="build-badge">
          {badgeLabel(status)}
        </span>
        {durationMs !== null ? <span data-testid="build-duration">{durationMs} ms</span> : null}
        <span data-testid="lsp-status">{lspStatus}</span>
      </header>
      {healthError ? (
        <div className="banner" role="alert">
          {healthError}
        </div>
      ) : null}
      {boardError ? (
        <div className="banner" role="alert">
          {boardError}
        </div>
      ) : null}
      {requestError ? (
        <div className="banner" role="alert">
          {requestError}
        </div>
      ) : null}
      {lspNote ? (
        <div className="banner" role="status">
          {lspNote}
        </div>
      ) : null}
      <div className="body">
        <aside className="tree">
          <h2>文件</h2>
          {files.map((file) => (
            <button
              key={file.path}
              type="button"
              className={file.path === activePath ? "active" : ""}
              onClick={() => setActivePath(file.path)}
            >
              {file.path}
              {file.dirty ? " *" : ""}
            </button>
          ))}
        </aside>
        <main className="editor">
          <Editor
            height="100%"
            language="cpp"
            theme="vs-dark"
            path={active?.path ?? "main.cpp"}
            value={active?.content ?? ""}
            onChange={(value) => updateActive(value ?? "")}
            onMount={(editor, monaco) => {
              editorRef.current = editor;
              monacoRef.current = monaco;
            }}
            options={{
              minimap: { enabled: false },
              quickSuggestions: false,
              suggestOnTriggerCharacters: false,
              wordBasedSuggestions: "off",
              parameterHints: { enabled: false },
              inlineSuggest: { enabled: false },
              snippetSuggestions: "none",
              hover: { enabled: false },
            }}
          />
        </main>
        <aside className="side">
          <h2>诊断</h2>
          {diagnostics.length === 0 ? <p>尚无诊断</p> : null}
          {diagnostics.map((diag, index) =>
            isRawDiagnostic(diag) ? (
              <details key={`${diag.file}:${diag.line}:${index}`} className="raw" open={expandFirst && index === 0}>
                <summary>
                  {diag.file}:{diag.line}:{diag.column} {diag.severity} raw
                </summary>
                <pre>{diag.message}</pre>
              </details>
            ) : (
              <button
                key={`${diag.file}:${diag.line}:${diag.column}:${index}`}
                type="button"
                className="diag"
                data-testid={index === 0 ? "first-diagnostic" : undefined}
                onClick={() => jump(diag)}
              >
                {diag.severity} {diag.file}:{diag.line}:{diag.column} {diag.message}
              </button>
            ),
          )}
          {rawOutput && !diagnostics.some((diag) => isRawDiagnostic(diag)) ? (
            <details className="raw" open={expandFirst}>
              <summary>raw</summary>
              <pre>{rawOutput}</pre>
            </details>
          ) : null}
          {lspDiags.length > 0 ? (
            <div>
              <h2>LSP</h2>
              {lspDiags.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          ) : null}
          <h2>扩展</h2>
          {extensionError ? <p className="err">{extensionError}</p> : null}
          {extensions.map((ext) => (
            <div key={ext.id} data-testid="extension-card">
              <p>{ext.id}</p>
              <p>{ext.name}</p>
              <p>{ext.capabilities.length > 0 ? ext.capabilities.join(", ") : "无"}</p>
              <button type="button" disabled={runningId === ext.id} onClick={() => void runGuest(ext.id)}>
                运行 {ext.name}
              </button>
            </div>
          ))}
          {extensionOutput ? (
            <p data-testid="extension-output" className="err">
              {extensionOutput}
            </p>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
