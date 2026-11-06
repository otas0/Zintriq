export type ProjectFile = {
  path: string;
  content: string;
  dirty: boolean;
  handle?: FileSystemFileHandle;
};

export type ProjectRoot = {
  name: string;
  dir?: FileSystemDirectoryHandle;
};

const TEXT_EXTS = new Set([".c", ".cc", ".cpp", ".h", ".hpp", ".py", ".md", ".txt", ".json", ".yaml", ".yml"]);

function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function canUseDirectoryPicker(): boolean {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
}

/** Firefox/Safari lack the directory picker; Tauri uses the native dialog plugin. */
export function folderOpenHint(): string {
  if (isTauriRuntime()) return "";
  if (canUseDirectoryPicker()) return "";
  return "当前浏览器不支持打开文件夹。请用 Chromium，或改用「导入文件」；Tauri 桌面版走系统目录对话框。";
}

async function readTextFile(handle: FileSystemFileHandle): Promise<string> {
  const file = await handle.getFile();
  return file.text();
}

async function walkDir(
  dir: FileSystemDirectoryHandle,
  prefix: string,
  out: ProjectFile[],
): Promise<void> {
  for await (const [name, handle] of dir.entries()) {
    if (name.startsWith(".")) continue;
    const rel = prefix ? `${prefix}/${name}` : name;
    if (handle.kind === "directory") {
      if (name === "node_modules" || name === "dist" || name === ".git") continue;
      await walkDir(handle as FileSystemDirectoryHandle, rel, out);
    } else {
      if (!TEXT_EXTS.has(extOf(name))) continue;
      const fileHandle = handle as FileSystemFileHandle;
      out.push({
        path: rel,
        content: await readTextFile(fileHandle),
        dirty: false,
        handle: fileHandle,
      });
    }
  }
}

async function openViaTauriDialog(): Promise<{ root: ProjectRoot; files: ProjectFile[] }> {
  const dialog = await import("@tauri-apps/plugin-dialog");
  const selected = await dialog.open({
    directory: true,
    multiple: false,
    title: "打开项目文件夹",
  });
  if (selected == null || Array.isArray(selected)) {
    throw new Error("已取消打开文件夹");
  }
  const dirPath = selected;
  const name = dirPath.split(/[/\\]/).filter(Boolean).pop() ?? "project";
  const { readDir, readTextFile: readPath } = await import("@tauri-apps/plugin-fs");
  const files: ProjectFile[] = [];

  async function walk(rel: string): Promise<void> {
    const entries = await readDir(rel ? `${dirPath}/${rel}` : dirPath);
    for (const entry of entries) {
      if (entry.name.startsWith(".")) continue;
      const childRel = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory) {
        if (entry.name === "node_modules" || entry.name === "dist" || entry.name === ".git") continue;
        await walk(childRel);
        continue;
      }
      if (!TEXT_EXTS.has(extOf(entry.name))) continue;
      const content = await readPath(`${dirPath}/${childRel}`);
      files.push({ path: childRel, content, dirty: false });
    }
  }

  await walk("");
  files.sort((a, b) => a.path.localeCompare(b.path));
  if (files.length === 0) {
    files.push({ path: "main.cpp", content: "int main(){return 0;}\n", dirty: true });
  }
  return { root: { name }, files };
}

export async function openProjectFolder(): Promise<{ root: ProjectRoot; files: ProjectFile[] }> {
  if (isTauriRuntime()) {
    return openViaTauriDialog();
  }
  const picker = window.showDirectoryPicker;
  if (!canUseDirectoryPicker() || typeof picker !== "function") {
    throw new Error(folderOpenHint() || "当前浏览器不支持打开文件夹");
  }
  const dir = await picker({ mode: "readwrite" });
  const files: ProjectFile[] = [];
  await walkDir(dir, "", files);
  files.sort((a, b) => a.path.localeCompare(b.path));
  if (files.length === 0) {
    const handle = await dir.getFileHandle("main.cpp", { create: true });
    const writable = await handle.createWritable();
    const content = "int main(){return 0;}\n";
    await writable.write(content);
    await writable.close();
    files.push({ path: "main.cpp", content, dirty: false, handle });
  }
  return { root: { name: dir.name, dir }, files };
}

/** Single-file / multi-file import for browsers without a directory picker. */
export async function importProjectFiles(fileList: FileList | File[]): Promise<{
  root: ProjectRoot;
  files: ProjectFile[];
}> {
  const list = Array.from(fileList);
  if (list.length === 0) {
    throw new Error("未选择文件");
  }
  const files: ProjectFile[] = [];
  for (const file of list) {
    const path = (file.webkitRelativePath || file.name).replace(/^\.?\/+/, "");
    if (!TEXT_EXTS.has(extOf(path))) continue;
    files.push({ path, content: await file.text(), dirty: false });
  }
  if (files.length === 0) {
    throw new Error("所选文件没有可编辑的文本源码");
  }
  files.sort((a, b) => a.path.localeCompare(b.path));
  const top = files[0]?.path.split("/")[0] ?? "import";
  const name = files.every((f) => f.path.startsWith(`${top}/`)) || files.some((f) => f.path.includes("/"))
    ? top
    : "import";
  return { root: { name }, files };
}

export async function createProjectFile(
  root: ProjectRoot,
  path: string,
  content = "",
): Promise<ProjectFile> {
  if (!root.dir) {
    return { path, content, dirty: true };
  }
  const parts = path.split("/").filter(Boolean);
  const fileName = parts.pop();
  if (!fileName) throw new Error("invalid path");
  let dir = root.dir;
  for (const part of parts) {
    dir = await dir.getDirectoryHandle(part, { create: true });
  }
  const handle = await dir.getFileHandle(fileName, { create: true });
  const writable = await handle.createWritable();
  await writable.write(content);
  await writable.close();
  return { path, content, dirty: false, handle };
}

export async function saveProjectFile(file: ProjectFile): Promise<ProjectFile> {
  if (file.handle) {
    const writable = await file.handle.createWritable();
    await writable.write(file.content);
    await writable.close();
    return { ...file, dirty: false };
  }
  if (isTauriRuntime()) {
    throw new Error("Tauri 会话请通过「打开文件夹」绑定目录后再保存；当前文件仅在内存中。");
  }
  const blob = new Blob([file.content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.path.split("/").pop() ?? "file.txt";
  a.click();
  URL.revokeObjectURL(url);
  return { ...file, dirty: false };
}
