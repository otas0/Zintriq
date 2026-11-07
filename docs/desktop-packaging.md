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

Electron **33.2.x** headers 与 MSVC `windows.h` 的 `min`/`max` 宏冲突（`error C2589` on `std::max`）。CI 已传 `CL=/DNOMINMAX`，但根因仍在 Electron headers；请使用 **Electron ≥ 33.4.3**（已钉 `33.4.11`，含 NOMINMAX backport）。`node-pty` **钉稳定版 `1.1.0`**：npm 上最新正式版仍是 1.1.0；`1.2.0-beta.*` 未升正式前不进 pack（VS18 / 新 MSVC 工具集可在 beta 绿后再评估）。重建失败时编辑器回退 Flask PTY（unix-pty / ConPTY），`Desktop pack` 不因此失败。

安装包文件名统一为 `ZintriqEditor-…`（`artifactName` / `executableName`），避免 GitHub Release 把空格改成点。

## 制品版本 ↔ git tag

`desktop/package.json` 的 `version` 决定 electron-builder 文件名中的 `${version}`。CI 在 tag 构建前把该字段写成 tag 语义版本：

- `v0.1.11` → `0.1.11` → `ZintriqEditor-0.1.11-…`
- `v0.1.11-release` → 去掉 `-release` 后缀 → 同为 `0.1.11`

本地未打 tag 时仍可用仓库里的占位版本（当前 `0.1.0`）。不要手改成与下一个 tag 不一致的值后直接 `npm run dist` 当正式包。

## Linux MIME（仅 plugin）

electron-builder 生成 Linux `.desktop` / deb / AppImage 时，会把 **每个** `fileAssociations[].mimeType` 并进 `MimeType=`（在 `afterPack` **之后**）。因此 zip/json 不能带 `mimeType` 字段——否则 CI 上 `xdg-mime` 会把 Zintriq 设成 `application/zip` 默认。Windows/macOS 仍靠 `ext` + `rank: Alternate` 做打开方式。

- `plugin.json` 保留 `mimeType: application/x-zintriq-plugin+json`
- `json` / `zip` 协会项：**无** `mimeType`（仅 Alternate 扩展名）
- Linux plugin MIME **仅**来自 `fileAssociations[plugin].mimeType`（勿再设 `linux.mimeTypes` / `linux.desktop.MimeType`，否则 `.desktop` 会重复三次）
- `afterPack` 仅作 linux-unpacked 兜底；真正约束在配置层
- pack CI `assoc-os.js`：`.desktop` 不含 zip/json；`MimeType=` 必须 **恰好一条** `application/x-zintriq-plugin+json`（禁止重复合并）；`xdg-mime` 默认不是 Zintriq

## Tag / Release 矩阵

- 日常 `v*`：slim（macos-latest + windows + ubuntu）
- 全量：`v*-release` 或 `workflow_dispatch` + `full_matrix=true`（另加 macos-15-intel）
- **当前成功 Release：slim=`v0.1.11` + 全量=`v0.1.12-release`（SUMS 合并）**（MimeType 单条 + tag→version 对齐；`v0.1.12-release` 含 macos-15-intel，合并后 `SHA256SUMS` 覆盖 mac-arm64/mac-x64/win Setup+portable/linux deb+AppImage）。Actions publish 曾因 billing/spending-limit 未启动，该次 Release 由 pack 制品手工上传；CI 现会先发 **draft** 再尝试 promote。`v0.1.7`–`v0.1.9` 为 Linux MIME 排障历史；不必强删旧 tag

## Pack 绿但 publish 被计费跳过（手动恢复）

症状：四个 `pack / *` 绿，`publish GitHub Release` 数秒失败，注解含 *payments have failed* / *spending limit*。

1. 确认 Actions artifacts 仍在（默认保留 7 天）：  
   `gh run view <run_id> -R otas0/Zintriq` → `zintriq-installers-*`
2. **大文件下载**优先走 Azure 签名 URL + Range（勿依赖易 403 的代理 `curl`）：  
   `python3 scripts/download-gh-artifact-ranges.py --artifact-id <id> -o os.zip`  
   或对 Release 资产：`--release-asset-id <id>`。解压后把各 OS 安装包摊到同一目录。
3. 合并并校验 SUMS：  
   `python3 desktop/packaging/sha256sums.py <dir> --write --verify`  
   （`python3 -m unittest desktop/packaging/test_sha256sums.py` 覆盖缺失/多余/digest）
4. 发 Release（tag 已存在时用 upload）：  
   ```bash
   gh release create vX.Y.Z-release --title vX.Y.Z-release --notes "manual recover; Actions publish blocked by billing" \
     <dir>/ZintriqEditor-* <dir>/SHA256SUMS <dir>/OFL.txt <dir>/THIRD_PARTY_NOTICES.md <dir>/sbom.cdx.json
   # 或：gh release upload vX.Y.Z-release … --clobber
   ```
5. 对照：合并后的 `SHA256SUMS` 行数应等于安装包数（slim≈6，全量含 intel≈8）；与手工/CI 发版互相 `diff`。
6. 额度恢复后：重跑失败的 publish job，或再打 `v*-release` tag；CI 会先写 **draft** 再 `gh release edit --draft=false`（promote 失败时 draft 资产仍在）。

签名：仓库无 `CSC_*` / Apple secrets 前不要打「已签名」tag。私有仓无 Pro 时 branch protection API 为 403，公开或升 Pro 后再开 PR 验 `lint`/`typecheck`/`test`/`build`。

本机同步：优先 `git fetch origin && git reset --hard origin/main`；仅在 `github.com:443` 长期挂起时才用 Contents / Git Data API 补文件。

旧产品树：`git checkout archive/pre-editor-pivot`。
