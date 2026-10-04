# 桌面安装包（阶段 1）

阶段 1 **不发布**任何对外安装包，直到 `appId` 从占位值改成你们拥有的域名倒写。

本机 **Python 3.9–3.12**（含两端）。不要用 3.13/3.14 打阶段 1 包。解释器由打包脚本自己解析（当前 venv 的 `python`，或 `ZINTRIQ_PYTHON`），不要求 PATH 上有名为 `python` 的命令。

## 创建虚拟环境

macOS / Linux：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --require-hashes -r requirements-desktop.lock.txt
```

若本机没有 3.11，用 `python3.12` 或 `python3.9` 同样可以：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --require-hashes -r requirements-desktop.lock.txt
```

Windows（PowerShell）：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-desktop.lock.txt
```

许可门只扫描 `requirements-desktop.lock.txt` 里的包（lock-only）。未知或需审核的许可必须写进 `desktop/packaging/license-exceptions.json`，每条都要有 `reason`，构建时会打印 `license exception used:`，不会静默放行。

## Web 不提供 Studio

这是预期行为，不是回归。在 `ZINTRIQ_DESKTOP` 未开启时，`GET /studio`、`GET /studio/`、`GET /studio/p/<id>` 返回 **404**（不是跳到登录页）。Studio 只由桌面应用在本地提供。测试见 `tests/test_desktop_mode.py` 的 `test_web_does_not_provide_studio`。

## appId（发布前必须确定）

## appId（发布前必须确定）

当前占位：`com.example.zintriq.unreleased`

发布前必须改成你们**拥有的域名倒写**（例如拥有 `zintriq.com` 时用 `com.zintriq.studio`）。改动 `appId` 会影响：

- Windows 安装身份（卸载/升级是否当成同一个应用）
- macOS bundle identifier
- 之后的登录回调 / 协议关联

在确定之前不要把安装包放到下载页或对外分发。

## 怎么在三个平台打出安装包

先装 Python 依赖（带哈希的锁定文件），再冻结构建本地服务，再打 Electron 包。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-desktop.lock.txt
.venv/bin/python desktop/packaging/generate_notices.py desktop/resources/notices
.venv/bin/python desktop/packaging/check_licenses.py license-report.json
.venv/bin/python desktop/packaging/build_server.py
cd desktop
npm ci
```

固定版本：PyInstaller `6.11.1`，Electron `33.2.0`，electron-builder `25.1.8`。PyInstaller **关闭 UPX**。`npm run dist` / `dist:mac` / `dist:win` / `dist:linux` 结束后会在 `desktop/release/` 写入 `SHA256SUMS` 和 `sbom.cdx.json`。CI 的 check 步骤会确认这两个文件存在。

| 平台 | 命令 | 产物 |
| --- | --- | --- |
| macOS | `cd desktop && npm run dist:mac` | `desktop/release/*.dmg`、`*.zip` |
| Windows | `cd desktop && npm run dist:win` | NSIS 安装程序、portable |
| Linux | `cd desktop && npm run dist:linux` | AppImage、deb |

不要上传 `*-unpacked` 目录。每个产物目录生成 `SHA256SUMS` 和 `sbom.cdx.json`。

CI 的 pack job：PR 仅在改动 `desktop/`、`requirements*.txt`、打包脚本、`.github/workflows` 时运行；合并到 `main`、打 `v*` 标签、手动 `workflow_dispatch` 时必跑。产物保留 **7 天**。打包 smoke 的日志仍走 `desktop/scripts/check_log_artifact.py`（令牌检查）。

## macOS（arm64 与 Intel）

打出来的 `.app` 应能直接启动。GitHub Actions **只对 CI 测试包做 ad-hoc 签名**（`codesign --sign -`），阶段 1 不做 Developer ID 公证。

本机验证未签名包时，可以只做**本地测试签名**（不是发布签名、不是 Developer ID）：

```bash
sh desktop/packaging/sign_macos_adhoc.sh "desktop/release/mac-arm64/Zintriq Studio.app"
# 等价于：codesign --force --deep --sign - "$APP" && codesign --verify --verbose=2 "$APP"
```

`npm run sign:mac-adhoc -- path/to/Zintriq\ Studio.app` 同样可以。这只让本机 `codesign --verify` 通过，**不能**当作对外分发签名，Gatekeeper 仍会拦截未公证的下载包。

从网站或网盘下载的 **dmg 会被 Gatekeeper 拦截**（“来自身份不明的开发者”）。用户需要在系统设置里允许，或把应用拖出隔离。这是未公证包的预期行为，不是启动崩溃。

Intel Mac 的 GitHub-hosted runner：**不要用 `macos-13`**。该镜像已于 2025 年 12 月退役（[GitHub Changelog，2025-09-19](https://github.blog/changelog/2025-09-19-github-actions-macos-13-runner-image-is-closing-down/)）。当前可用的 Intel 标签是 **`macos-15-intel`**，计划支持到 2027 年 8 月（[actions/runner-images#13045](https://github.com/actions/runner-images/issues/13045)）。Apple Silicon 用 `macos-latest` / `macos-15`。

## Windows NSIS

per-user 安装，不要求管理员（`perMachine: false`，`allowElevation: false`）。卸载默认保留 userData；只有用户在卸载对话框里明确选择删除时才删本地数据。

## Linux（Ubuntu 24.04）

在 Ubuntu 24.04 上应用 AppImage 和 deb。Electron 沙箱依赖用户命名空间。Ubuntu 24.04 默认 **AppArmor 限制非特权 user namespace**（`kernel.apparmor_restrict_unprivileged_userns=1`）时，沙箱可能无法启动。

可以让用户改系统策略，例如允许 Electron 的 userns，或在自己的机器上临时放宽限制。**正式包绝不默认加 `--no-sandbox`。** CI Linux 的开发 smoke 可以关沙箱，安装包不行。

AppImage 在无 FUSE 的环境用 `APPIMAGE_EXTRACT_AND_RUN=1`。

## 运行时约束

- 冻结后的 `zintriq-server` 不得再把 `app.py` 传给 `sys.executable`（会递归拉起自己）。入口调用 `multiprocessing.freeze_support()`。Flask 子进程必须丢掉 Electron 继承的 `LD_LIBRARY_PATH`（Linux 上会指向 chrome/ffmpeg，冻结解释器对不上）。
- 数据库 `PRAGMA user_version`：比应用新则拒绝打开并提示升级；比应用旧则迁移后盖章。当前桌面 schema 为 3（`builder_data_records.surface`：preview / published；发布快照不嵌入预览记录）。
- 匿名公开写入限流：桌面用进程内 `builder_kernel.rate_limit.InProcessRateLimiter`（每 IP+项目 10/分钟、100/小时）。**云端多进程部署必须替换** `get_rate_limiter()` 为共享后端，否则各 worker 各自计数。
- waitress：`max_request_body_size=40MiB`（大于 32MiB 作品包上限）、`expose_tracebacks=False`、空 `ident`（不暴露服务器标识）、`clear_untrusted_proxy_headers=True`。stdin EOF 时 `server.close()`，3 秒后 `os._exit` 兜底，从而释放锁文件。
- 桌面默认工作区 `type=personal`，不调用 `ensure_workspace_store`，空白项目发布为 `/build/<slug>` 而不是 hybrid 店铺首页。
- 能力包可选 `contributes`，仅允许 `editor` / `sidebar` / `commands`（每项需 `id`+`title`）；kernel `editor_payload` 汇总露出。不做 bos.workflows 合并，不做沙箱审核。
- 许可清单只看 desktop lock 中的包。未知或需要审核的许可（GPL、AGPL、LGPL 等）时构建失败，除非该包已在 `desktop/packaging/license-exceptions.json` 写明原因。PyInstaller 本身带 GPL+exception，只作为构建工具列入该白名单。
