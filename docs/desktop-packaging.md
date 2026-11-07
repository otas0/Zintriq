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

`fileAssociations` 仍可为 Windows/macOS 注册 zip/json 的 Alternate；electron-builder 会把这些 mime 合并进 Linux `.desktop` 的 `MimeType=`，从而在无其他默认时让 `xdg-mime` 把 Zintriq 设成 `application/zip` 默认。因此：

- `linux.mimeTypes` / `linux.desktop.MimeType` 只声明 `application/x-zintriq-plugin+json`
- `afterPack`（`packaging/after-pack-linux-mime.js`）在打包前把 `.desktop` 的 MimeType 剥成 plugin-only
- pack CI 的 `assoc-os.js` 断言：`.desktop` 不含 zip/json，且 `xdg-mime` 默认不是 Zintriq

## Tag / Release 矩阵

- 日常 `v*`：slim（macos-latest + windows + ubuntu）
- 全量：`v*-release` 或 `workflow_dispatch` + `full_matrix=true`（另加 macos-15-intel）
- **当前以最新成功 Release 为准：`v0.1.6-release`**（4 OS + intel + 已发布资产）。`v0.1.7` / `v0.1.8` pack 因 Linux zip MIME 红，仅作排障历史；修好后以更新 tag / Release 取代说明，不必强删旧 tag

旧产品树：`git checkout archive/pre-editor-pivot`。
