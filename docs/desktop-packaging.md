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

Electron **33.2.x** headers 与 MSVC `windows.h` 的 `min`/`max` 宏冲突（`error C2589` on `std::max`）。CI 已传 `CL=/DNOMINMAX`，但根因仍在 Electron headers；请使用 **Electron ≥ 33.4.3**（已钉 `33.4.11`，含 NOMINMAX backport）。`node-pty` 升到 `^1.1.0`。重建失败时编辑器回退 Flask PTY（unix-pty / ConPTY），`Desktop pack` 不因此失败。

安装包文件名统一为 `ZintriqEditor-…`（`artifactName` / `executableName`），避免 GitHub Release 把空格改成点。

## Tag / Release 矩阵

- 日常 `v*`：slim（macos-latest + windows + ubuntu）
- 全量：`v*-release` 或 `workflow_dispatch` + `full_matrix=true`（另加 macos-15-intel）
- 中间失败 tag（如 v0.1.0–v0.1.4 pack 红）：仅作排障历史，以最新成功 tag / Release 为准；不必删除，Release 说明里指向最新即可

旧产品树：`git checkout archive/pre-editor-pivot`。
