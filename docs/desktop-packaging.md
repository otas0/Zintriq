# 桌面安装包 — Zintriq Editor

`appId`：`com.editor`。本机 Python 3.9–3.12。

## 创建虚拟环境

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd desktop && npm install && npm run dist
```

## 运行时

- 仅 `127.0.0.1`
- `ZINTRIQ_DESKTOP_TOKEN` 由 Electron 生成
- 工作区：`ZINTRIQ_WORKSPACE`（默认 `$ZINTRIQ_DATA_DIR/workspace`）

签名 / 公证：产品完成前默认关闭（`CSC_IDENTITY_AUTO_DISCOVERY=false`）。仓库 Actions 暂无 `CSC_*` / Apple secrets 时打出的 tag 均为未签名包。

## Windows native rebuild（node-pty）

Electron **33.2.x** headers 与 MSVC `windows.h` 的 `min`/`max` 宏冲突（`error C2589` on `std::max`）。CI 已传 `CL=/DNOMINMAX`，但根因仍在 Electron headers；请使用 **Electron ≥ 33.4.3**（已钉 `33.4.11`，含 NOMINMAX backport）。`node-pty` 钉 `1.1.0`（评估升到支持 VS18 / MSVC 的更新版时另开 PR）。重建失败时编辑器回退 Flask PTY（unix-pty / ConPTY），`Desktop pack` 不因此失败。

安装包文件名统一为 `ZintriqEditor-…`（`artifactName` / `executableName`），避免 GitHub Release 把空格改成点。

## Linux MIME（仅 plugin）

electron-builder 生成 Linux `.desktop` / deb / AppImage 时，会把 **每个** `fileAssociations[].mimeType` 并进 `MimeType=`（在 `afterPack` **之后**）。因此 zip/json 不能带 `mimeType` 字段——否则 CI 上 `xdg-mime` 会把 Zintriq 设成 `application/zip` 默认。Windows/macOS 仍靠 `ext` + `rank: Alternate` 做打开方式。

- `plugin.json` 保留 `mimeType: application/x-zintriq-plugin+json`
- `json` / `zip` 协会项：**无** `mimeType`（仅 Alternate 扩展名）
- `linux.mimeTypes` / `linux.desktop.MimeType` 只声明 plugin MIME
- `afterPack` 仅作 linux-unpacked 兜底；真正约束在配置层
- pack CI `assoc-os.js`：`.desktop` 不含 zip/json，且 `xdg-mime` 默认不是 Zintriq

## Tag / Release 矩阵

- 日常 `v*`：slim（macos-latest + windows + ubuntu）
- 全量：`v*-release` 或 `workflow_dispatch` + `full_matrix=true`（另加 macos-15-intel）
- **当前以最新成功 Release 为准：`v0.1.6-release`**（4 OS + intel + 已发布资产）。`v0.1.7`–`v0.1.9` pack 因 Linux zip/json MimeType 红（fileAssociations mime 并入 `.desktop`），仅作排障历史；`v0.1.10+` 去掉 zip/json 的 `mimeType` 字段后应转绿，不必强删旧 tag

旧产品树：`git checkout archive/pre-editor-pivot`。
