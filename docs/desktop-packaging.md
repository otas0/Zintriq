# 桌面安装包

`appId` 为 `com.zintriq.studio`。本机 **Python 3.9–3.12**（含两端）。不要用 3.13/3.14 打包。解释器由打包脚本自己解析（当前 venv 的 `python`，或 `ZINTRIQ_PYTHON`），不要求 PATH 上有名为 `python` 的命令。

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

## appId

`com.zintriq.studio`（`zintriq.com` 倒写）。改 `appId` 会让 Windows 当成新应用安装。

## 签名、公证、自动安装

有证书时，`npm run dist` 会签 macOS Developer ID、Windows Authenticode，并在有 Apple 账号时公证。打包应用的 **Check for updates** 会下载并安装签名更新（`electron-updater`，feed：`https://zintriq.com/desktop/updates`）。开发态 `electron .` 仍只打开下载页。

本机或 CI **没有证书**时保持未签名；macOS CI 仍做 ad-hoc 仅供 smoke。把证书放进 GitHub Actions secrets 后，tag 构建会走正式签名，并跳过 ad-hoc（避免盖掉 Developer ID）。

本机开发：`cd desktop && electron .`（或 `npm run dev`）。未签名目录产物：`npm run pack`（`--dir --publish never`）。商店安装包仍等产品完成后再配下面的 `CSC_LINK` / `APPLE_ID`。

环境变量（不要提交私钥）：

| 变量 | 用途 |
| --- | --- |
| `CSC_LINK` | macOS Developer ID `.p12`（base64 或文件路径） |
| `CSC_KEY_PASSWORD` | 该 p12 密码 |
| `WIN_CSC_LINK` / `WIN_CSC_KEY_PASSWORD` | Windows Authenticode p12 |
| `APPLE_ID` | 公证用 Apple ID |
| `APPLE_APP_SPECIFIC_PASSWORD` | 应用专用密码 |
| `APPLE_TEAM_ID` | 团队 ID |
| `ZINTRIQ_SIGN=1` | 缺证书时构建直接失败（发布用） |
| `STUDIO_UPDATE_DIR` | 网站上托管 `latest*.yml` 与安装包的目录 |

```bash
# 发布机（macOS）
export CSC_LINK=/secure/developer-id.p12
export CSC_KEY_PASSWORD=…
export APPLE_ID=…
export APPLE_APP_SPECIFIC_PASSWORD=…
export APPLE_TEAM_ID=…
export ZINTRIQ_SIGN=1
cd desktop && npm run dist:mac
```

把 `desktop/release/latest-mac.yml`（及 dmg/zip/blockmap）拷到 `STUDIO_UPDATE_DIR`。Linux 无 Apple/Microsoft 证书；AppImage 仍走同一 feed。

GitHub Actions secrets 同名：`CSC_LINK`、`CSC_KEY_PASSWORD`、`WIN_CSC_LINK`、`WIN_CSC_KEY_PASSWORD`、`APPLE_ID`、`APPLE_APP_SPECIFIC_PASSWORD`、`APPLE_TEAM_ID`。

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

打出来的 `.app` 应能直接启动。GitHub Actions 在没有 `APPLE_ID` 时仍对 CI 包做 ad-hoc 签名（`codesign --sign -`）。有 Developer ID 与公证密钥时走正式签名，不再 ad-hoc。

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
- Linux 冻结包须显式带上 `backports` / `backports.tarfile`（并 pin `setuptools`）：PyInstaller 的 `pyi_rth_pkgres` 会加载 `pkg_resources`→`jaraco.context`，在 Python <3.12 上缺 `backports` 时进程会在 `ZINTRIQ_READY` 前退出。Flask 启动失败时 smoke 会立刻写出 `loaded: false` 的 session，不再干等 90s。
- Desktop CI：功能分支只靠 `pull_request` 触发（`push` 仅 `main`），避免同 SHA 跑两遍；Windows 上探测 pid 存活不得用 `os.kill(pid, 0)`（那是 `CTRL_C_EVENT`，会打断整个 unittest 控制台组）。
- 桌面 Studio 壳露出 Community（`/app/community`）与元编辑器；仍不露出团队 / 账号设置。Electron 导航白名单放行 `/studio`、`/app/community`、`/build`、创作 API 与静态资源（见 `desktop/navigation.js`）。
- **元系统是核心**（见 `docs/META.md` / 包 `meta/`）；Studio 与桌面是宿主。中国大陆地区服务因法律原因暂时搁置，不永久排除。
- 数据库 `PRAGMA user_version`：比应用新则拒绝打开并提示升级；比应用旧则迁移后盖章。当前桌面 schema 为 3（`builder_data_records.surface`：preview / published；发布快照不嵌入预览记录）。
- 匿名公开写入限流：桌面用进程内 `builder_kernel.rate_limit.InProcessRateLimiter`（每 IP+项目 10/分钟、100/小时）。**云端多进程部署必须替换** `get_rate_limiter()` 为共享后端，否则各 worker 各自计数。
- waitress：`max_request_body_size=40MiB`（大于 32MiB 作品包上限）、`expose_tracebacks=False`、空 `ident`（不暴露服务器标识）、`clear_untrusted_proxy_headers=True`。stdin EOF 时 `server.close()`，3 秒后 `os._exit` 兜底，从而释放锁文件。
- 应用只写 userData。把安装目录设为只读后，打包 smoke 仍应成功。Windows CI 用 `icacls` 去掉继承、授 `(OI)(CI)RX` 再 `/deny (OI)(CI)W`（仅 RX 时所有者仍常能新建文件；`attrib +R` 无效）。macOS / Linux 仍用 `chmod -R a-w`。
- 桌面默认工作区 `type=personal`，不调用 `ensure_workspace_store`，空白项目发布为 `/build/<slug>` 而不是 hybrid 店铺首页。
- 能力包可选 `contributes`，仅允许 `editor` / `sidebar` / `commands`（每项需 `id`+`title`）；kernel `editor_payload` 汇总露出。不做 bos.workflows 合并，不做沙箱审核。
- 许可清单只看 desktop lock 中的包。未知或需要审核的许可（GPL、AGPL、LGPL 等）时构建失败，除非该包已在 `desktop/packaging/license-exceptions.json` 写明原因。PyInstaller 本身带 GPL+exception，只作为构建工具列入该白名单。

## 文件关联手测（Alternate，安装后）

zip / `.zintriq-plugin.json` 都是 **Alternate**，不能抢系统默认解压程序。CI 的 `desktop/scripts/assoc-os.js` 会查注册表/`mdls`/`xdg-mime`；下面是人在三台机器上点「打开方式」的清单。

### Windows（NSIS 安装后）

手测录像核对：NSIS 安装后截资源管理器「打开方式」与 `OpenWithProgids`，对照本文档。
手测补 `.zintriq-plugin.json`：NSIS 后截该扩展「打开方式」与 `OpenWithProgids`，对照文档。

1. 跑 `npm run dist:win`，用 Setup `/S` 装到本机。
2. 资源管理器里对任意 `.zip` 右键 **打开方式**：默认仍是资源管理器/压缩工具，**不是** Zintriq Studio。录像或截图该菜单。
3. 注册表：`reg query HKCU\Software\Classes\.zintriq-plugin.json` 以及 `HKCU\Software\Classes\.zip\OpenWithProgids` 里能看到 Zintriq（Alternate），`.zip` 的默认 ProgId 不是 Zintriq。截 `OpenWithProgids`。
4. 对 `.zintriq-plugin.json` 右键 **打开方式** 并截图，对照 `OpenWithProgids`；不要把 zip 设成默认。

### macOS（pack `.app`）

访达核对：pack `.app` 上确认插件 JSON 不是 Archive Utility。
访达补 content type：pack `.app` 上对插件 JSON 跑 `mdls`，确认不是 Archive Utility。

1. 对 pack 产物里的 `Zintriq Studio.app` 跑 `mdls -name kMDItemContentType` 指向一份 `*.zintriq-plugin.json`：UTI 不能是 zip-archive，不能落到 Archive Utility。
2. 访达选中该 JSON → 文件 → 打开方式：默认不是 Archive Utility；zip 默认仍是归档实用工具。
3. 可选：`duti -x json` 不应把插件 JSON 指到 unzip。

### Linux（deb 与 AppImage）

mime 核对：deb/AppImage 用户目录 `xdg-mime query default application/zip` 非 Zintriq。
mime 补 `application/json`：用户目录 `xdg-mime query default application/json` 非 Zintriq，zip 继续 Alternate。

1. 安装 deb，或首次运行 AppImage 后查看 `~/.local/share/applications`。
2. `xdg-mime query default application/zip` **不得**变成 Zintriq（zip 保持 Alternate）。
3. `xdg-mime query default application/json` **不得**变成 Zintriq；zip 继续 Alternate。
