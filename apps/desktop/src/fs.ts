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

export function canUseDirectoryPicker(): boolean {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
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
      continue;
    }
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

export async function openProjectFolder(): Promise<{ root: ProjectRoot; files: ProjectFile[] }> {
  const picker = window.showDirectoryPicker;
  if (!canUseDirectoryPicker() || typeof picker !== "function") {
    throw new Error("当前浏览器不支持打开文件夹（需要 Chromium 的目录选择器）");
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
  const blob = new Blob([file.content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.path.split("/").pop() ?? "file.txt";
  a.click();
  URL.revokeObjectURL(url);
  return { ...file, dirty: false };
}
