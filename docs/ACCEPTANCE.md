# 验收复现

本页只描述如何本地复现 typed MVP。不承诺翻译、AI 补全或自动构建。

## 1. 安装与启动

```bash
corepack pnpm install
corepack pnpm --filter core-service dev
```

另开终端：

```bash
corepack pnpm --filter desktop dev
```

浏览器打开 `http://localhost:5173`。

## 2. curl 五条路由

```bash
curl -s http://127.0.0.1:4317/health
curl -s http://127.0.0.1:4317/boards
curl -s -X POST http://127.0.0.1:4317/build \
  -H 'content-type: application/json' \
  -d '{"boardId":"esp32","entryFile":"main.cpp","files":[{"path":"main.cpp","content":"int main(){return 0;}\n"}]}'
curl -s http://127.0.0.1:4317/extensions
curl -s -X POST http://127.0.0.1:4317/extensions/fixture-fs-read/run \
  -H 'content-type: application/json' -d '{}'
curl -s -X POST http://127.0.0.1:4317/extensions/fixture-no-fs/run \
  -H 'content-type: application/json' -d '{}'
curl -s 'http://127.0.0.1:4317/audit?limit=20'
```

期望：health 为 `ok`；boards 至少含 esp32 / rp2040 / stm32；合法 build 为 `success`；声明 `fs.read` 的扩展 `ok: true`；未声明能力返回 `403 CAPABILITY_DENIED`；`/audit` 能看到 denied 记录。

非法请求对照：

```bash
curl -s -X POST http://127.0.0.1:4317/build -H 'content-type: application/json' -d '{}'
curl -s -X POST http://127.0.0.1:4317/build \
  -H 'content-type: application/json' \
  -d '{"boardId":"missing","entryFile":"main.cpp","files":[{"path":"main.cpp","content":"int main(){return 0;}\n"}]}'
```

## 3. Desktop 手工验收

1. 顶部状态为 `ok`，开发板下拉有多块板。
2. **打开文件夹**（Chromium / Tauri 系统对话框）或 **导入文件**（Firefox/Safari 降级）；**新建文件**、编辑后出现脏标记 `*`，**保存**清除脏标记。
3. 改成非法 C++，点 **构建检查**：徽章 `failed`，诊断列表有条目；点击第一条跳到编辑器行列并高亮（含跨文件 pendingJump）。
4. 若诊断含 `BUILD_TIMEOUT` / `COMPILER_NOT_FOUND`，顶部出现对应中文说明。
5. 扩展面板显示 `extensionsDir`；运行 FS read fixture 得到数字输出；运行 No FS fixture 显示「扩展未声明该能力」。
6. **连接语言服务** 仅接 mock，不自动在每次按键时请求；状态显示 `mock`。可选 **连接 clangd**（Tauri sidecar 探测，仍显式）。
7. 审计只读面板可按 `extensionId` 过滤并刷新；`GET /audit?extensionId=` 与 UI 一致。

## 4. 自动化

```bash
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
corepack pnpm --filter desktop test:e2e
```

Playwright 冒烟默认走本机 Electron（见 `apps/desktop/e2e`）。若本机已安装 Chromium，可自行把配置切到 `chromium`；CDN 不可用时不要阻塞验收。

## 5. Tauri

需要本机 Rust + `cargo`。当前 CI / 默认开发路径不依赖付费云账号：

```bash
cd apps/desktop && corepack pnpm exec tauri build
```

本机已用 Rust 1.99 + `@tauri-apps/cli` 跑通 release 打包（产出 `Zintriq_*.dmg`）。无 `cargo` 时跳过此步，以 Vite + Electron 冒烟为准。
