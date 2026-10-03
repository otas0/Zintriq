# Builder 桌面迁移审计

只读结论，基于当前仓库。创作功能的产品入口是 Studio（`/studio`），Universal Builder API 在 `/api/builder-core/*`。`desktop/` 已有一个 Electron 壳，但它连的是已运行的 Flask，并且登录走 Auth0。阶段 1 要求的是：Electron 拉起本地 Flask 子进程、单用户、不登录、三平台。

Web 路由都还在。本文件不改任何运行代码。

## 1. Builder 入口

### 页面路由

| 路径 | 处理 | 模板 | 登录 |
| --- | --- | --- | --- |
| `GET /studio` | `studio_platform.studio_home` | `templates/workspace_dashboard.html` | 要 |
| `GET /studio/p/<project_id>` | `studio_platform.studio_editor` | `templates/builder/editor.html` | 要，且必须是该项目 workspace 成员 |
| `GET /studio/desktop` | `studio_platform.studio_desktop_gate` | `templates/studio/desktop_gate.html` | 不要；已登录则跳到 `/studio` |
| `GET /app/builder` | `universal_builder_home` | 无，302 到 `/studio` | 要 |
| `GET /app/builder/<project_id>` | `universal_builder_editor` | 无，302 到 `/studio/p/<id>` | 要 |
| `GET /app/builder-module/<module_id>` | `universal_builder_module_host` | `bos/store_module.html` 或 `builder/module_placeholder.html` | 要 |
| `GET /build/<slug>/<document_key>` | `universal_builder_public` | 运行时 HTML，无模板 | 不要 |
| `POST /build/.../booking`、`POST /builder-runtime/.../booking` | `universal_builder_public_booking` | 重定向 | 不要 |
| `POST /build/.../form-submit`、`POST /builder-runtime/.../form-submit` | `universal_builder_public_form_submit` | 重定向 | 不要 |

注册位置：`studio_platform.register_studio_platform`（`app.py` 约 5506 行调用），`universal_builder_core.register_universal_builder_core`（约 5503 行）。

Studio 附属 API：`/api/studio/surfaces`、`/handoff`、`/me`、`/tokens`、`/auth/pkce/exchange`、`/download/<platform>`。

创作 API 全部在 `universal_builder_core.py` 的 `register_universal_builder_core`，前缀 `/api/builder-core/`，另有别名 `GET /api/community/templates`。覆盖：schema、组件、能力、模板、项目、页面、节点、绑定、动作、数据模型与记录、状态、条件、包安装、入口、路由所有权、组件定义与实例、设计令牌、变量、交互、预览、发布。Marketplace 路由在 `universal_builder_marketplace.py`（`/app/marketplace`、`/app/community`、`/api/marketplace/*`）。

每个已登录的 Builder API 先走 `context()`：当前用户、`session["active_workspace_id"]` 或第一份成员关系、`bos.permissions.has_permission`。权限名是 `builder.read` / `builder.create` / `builder.publish`，但这些 key **不在** `bos/permissions.py` 的 `ALL_PERMISSIONS` 里。失败后回退到 `workspace.read`（只读）或 `workspace.update`（写和发布）。owner 角色拥有全部 workspace 权限，所以所有者可以创作。viewer 不能写。

`GET /studio` 会调用 `ensure_studio_workspace_for_user`：没有 workspace 时创建组织、名为 “Studio tenant” 的 workspace、owner 成员。`ensure_default_workspace` 还会调用 `bos/workspace_store.ensure_workspace_store`，顺手插入一条 `stores` 记录。这是商家数据的副作用，不是 Builder 画布本身。

### 模板

- 编辑器：`templates/builder/base.html`、`editor.html`、`module_placeholder.html`、`_header.html`
- 项目列表：`templates/workspace_dashboard.html`，套 `templates/zintriq/base.html`，加上 `zintriq/partials/topbar.html`、`sidebar.html`、`create_modal.html`
- 桌面登录门：`templates/studio/desktop_gate.html`
- 官方模板清单：`builder_templates/zintriq-system/manifest.json`、`zintriq-customer/manifest.json`、`zintriq-business/manifest.json`（由 `universal_builder_core` 在初始化时写入 `builder_templates` 表）

`editor.html` 和 `zintriq/base.html` 都从 `https://cdn.jsdelivr.net` 拉 Geist 字体。离线时页面仍能打开，字体回退。

### 静态资源

编辑器模块（`editor.html` 以 `type="module"` 加载）：

- `static/builder/universal-builder.js`
- `static/builder/universal-api.js`（`fetch`，`credentials: "same-origin"`，可带 Bearer）
- `static/builder/universal-canvas.js`
- `static/builder/studio-graph.js`
- `static/builder/universal-builder.css`

Studio 壳：

- `static/studio-shell.css`、`static/studio-desktop.css`、`static/studio-desktop.js`
- `static/workspace-dashboard.css`、`static/workspace-dashboard.js`
- `static/tokens.css`、`static/materials.css`、`static/system.css`
- `static/zintriq-shell.js`、`static/mq-i18n.js`

同目录里还有旧的 QR/体验编辑器资源，当前 Studio 编辑器不加载它们：`experience-builder.js/css`、`builder-state.js`、`builder-preview.js`、`builder-history.js`、`builder-api.js`、`component-registry.js`、`universal-home.js`、`universal-marketplace.js`、`universal-runtime.css`。

### 相关 Python 模块

创作核心：

- `universal_builder_core.py` — 表、项目、路由
- `universal_builder_creator.py` — 组件定义与实例
- `universal_builder_runtime.py` — 已发布页面渲染
- `universal_builder_packages.py` — 包清单校验
- `universal_builder_marketplace.py` — 社区/市场路由（阶段 1 页面不做）
- `universal_builder_modules.py` — 受控模块与领域数据源
- `universal_builder_capabilities.py` — 能力登记（含 booking、payments、crm）
- `universal_builder_migration.py` — 路由所有权
- `universal_component_registry.py`、`builder_components.py`
- `studio_platform.py` — Studio 壳、Bearer token、Auth0 PKCE

租户（创作门禁，不是画布）：`bos/permissions.py`、`bos/services/workspace.py`、`bos/services/organization.py`、`bos/workspace_store.py`。

旧的 QR 体验编辑器是另一条产品线，不在 Studio 画布里：`qr_experience_builder.py`、`qr_experience_platform.py`（`/api/qr-experiences*`、`/experience/<code>`）、`qr_experience_runtime.py`、`qr_experience_revisions.py`、`qr_experience_workflow.py`。发布页上的预约组件会调用 `qr_experience_runtime.public_create_booking`。

## 2. 数据库与上传路径

初始化：`app.init_db()`（`app.py`）。只有 `python app.py` 和 `scripts/dev_studio_sqlite.py` 会调用它。`import app` 不会建表。Builder 表在 `init_universal_builder_tables`（`universal_builder_core.py`），Studio token 表在 `init_studio_tables`。同一次 `init_db` 也会建商家表（stores、bookings、feedback、checkout 等）。

数据库文件：

- 默认路径写在代码里：`db_adapter.DEFAULT_SQLITE_PATH` = 仓库根目录 `marketqr.db`。
- 可用环境变量 `SQLITE_PATH` 覆盖，`db_adapter.sqlite_path()` 用 `pathlib.Path`，不写死分隔符。
- **时序问题：** `app.py` 在第 36 行就把 `DATABASE = sqlite_path()` 算死了，`.env.local` 在第 54 行才加载。只写在 `.env.local` 里的 `SQLITE_PATH` 不会生效。进程环境里事先设好的 `SQLITE_PATH` 可以。`scripts/dev_studio_sqlite.py` 就是在 import 之前设置的。
- `DATABASE_URL` 以 `postgres://` 或 `postgresql://` 开头时走 Postgres（`psycopg`），路径在连接时读取，所以 `.env.local` 里的 `DATABASE_URL` 会生效。`DATABASE_IAM_AUTH=1` 时还会用 boto3 向 RDS 要 token。桌面模式必须显式丢掉 `DATABASE_URL`，否则会连云库。开发脚本已经这样做。

上传：

- `UPLOAD_DIR = BASE_DIR / "static" / "uploads"`，写死在仓库 `static/uploads`。
- 没有环境变量。`init_db` 和 `save_uploaded_image` 会 `mkdir`。
- 对外 URL 是 `url_for("static", filename="uploads/<name>")`，也就是必须放在 Flask static 目录下。换到用户数据目录时，现有 URL 会 404，除非加单独的发送路由。
- 请求体上限 `MAX_CONTENT_LENGTH` = 5 MB，写在 `app.config`。

密钥文件：没有 `SECRET_KEY` 时，`_dev_secret_key()` 把密钥写到仓库根目录 `.dev_secret_key`。桌面安装包里这个位置通常不可写。

## 3. 登录、Workspace、外部服务

### 登录

- `login_required`（`app.py`）要求 `session["user_id"]`，否则重定向 `/login`。`current_user()` 也接受 `g.studio_bearer_user`（`Authorization: Bearer zst_…` 或 `X-Studio-Token`）。
- 纯顾客账号（`is_shopper_only_user`）会被清掉，进不了 Builder。
- Web 登录：`AUTH_PROVIDER=auth0` 且配齐 `AUTH0_DOMAIN`、`AUTH0_CLIENT_ID`、`AUTH0_CLIENT_SECRET`、`AUTH0_CALLBACK_URL` 时，`/login` 与 `/register` 跳 Auth0。`?local=1` 可走本地口令。
- 桌面登录：`desktop/main.js` 打开系统浏览器做 Auth0 Native PKCE，回调 `zintriq://auth/callback`，再 `POST /api/studio/auth/pkce/exchange`。没配 `AUTH0_DOMAIN` 和 `AUTH0_NATIVE_CLIENT_ID` 时，`startLogin()` 直接抛错。服务端未配置则该接口返回 503。
- 其他账号能力：密码重置、魔法链接（`email_delivery`）、2FA、Twilio 手机号登录（`merchant_phone_auth.py`、`customer_verification.py`）、Turnstile（`TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` / `TURNSTILE_REQUIRED`）。

阶段 1 明确不做账号登录。以现在的门禁，没有 session 或 Bearer 就打不开 `/studio` 和全部创作 API。

### Workspace

创作数据的租户边界是 `builder_projects.workspace_id`，不是可选字段。`context()` 找不到成员关系就 `abort(400)`。列表页会自动补一个默认 workspace，但只发生在 `GET /studio`。直接打 API、用户还没有任何 workspace 时，API 会 400。

Sidebar 仍链到 `/app/settings#account` 和 `/app/community`。Community 在 Electron 里会被送到系统浏览器（`desktop/main.js` 的 `isCommunityPath`，以及 `static/studio-desktop.js`）。

### 邮件 / 短信 / 支付

创作画布的保存、节点、预览、本地发布记录不调用这些服务。发布只是往 `builder_deployments` 写一行，`public_url` 是站内相对路径（`/build/<slug>`，商家模板则是 `/manage/<store slug>`）。

会碰到外部服务的相邻能力：

| 能力 | 位置 | 没配置时 |
| --- | --- | --- |
| SMTP 邮件 | `email_delivery.py`（`SMTP_HOST` 等） | `send_transactional_email` 返回 False |
| 短信 | `customer_verification.py`（`TWILIO_*`） | 手机号登录不可用 |
| 支付 | `integrations/config.py` 的 `PAYMENT_PROVIDER`（默认 `none`）、`checkout_platform.py`、`payment_connect_plugin.py`（Stripe / PayPal / PayPay） | 结账走不了真实收款 |
| 日历 | `CALENDAR_PROVIDER`（默认 `none`） | 外部日历同步不做 |
| 字体 CDN | 两个 base 模板 | 离线用系统字体 |
| Auth0 | Web 与 `desktop/main.js` | 桌面登录失败 |

`universal_builder_capabilities.py` 把 `payments`、`booking`、`crm`、`feedback`、`auth` 登记成能力。`universal_builder_modules.py` 的受控模块指向商家后台：`/app/store`、`/app/booking`、`/app/store#experiences`。领域数据源 `commerce.stores`、`commerce.products` 读 `stores` / `items`；`workspace.current` 读 `workspaces`。Marketplace 路由只查本地 SQLite，没有出站 HTTP。

公开预约 `public_create_booking` 只插入 `bookings` 并发本地事件，不发邮件。公开表单提交写入 `builder_data_records`。两者都要项目已经发布，预约还要求该 workspace 至少有一个 store（默认 workspace 创建时会有）。

## 4. 单用户本地模式下会停的功能

这里的“单用户本地模式”指：本机 SQLite、无 Auth0、无 SMTP、无短信、无支付、不打开 Community。阶段 1 也不做云同步和硬件配对。

**现在就会整段停住**

- Studio 首页、编辑器、全部 `/api/builder-core/*`：没有本地用户 session 或 `zst_` token。
- 现有 Electron 的“登录”按钮：依赖 Auth0。这和阶段 1“不做账号登录”直接冲突。
- 桌面壳不会自己启动 Flask。`desktop/README.md` 要求另开终端跑 `app.py`。

**有了本地所有者用户之后，创作主路径可以跑**

新建项目、页面、节点、绑定、动作、数据模型与记录、撤销重做（前端内存）、预览、发布到本机 `/build/<slug>/...`、官方模板（随 `init_db` 从 `builder_templates/` 种入）。owner 通过 `workspace.update` 回退拿到写权限。

**仍然不能按现在的产品语义运行**

- Community 浏览、从网页导入包、`zintriq://studio?action=install` 所依赖的线上目录。本地已安装包的增删改可以，因为数据在 SQLite。
- Auth0 登录、魔法链接、忘记密码、2FA、Twilio 登录、Turnstile。
- 团队邀请（要邮件，也是多用户）。
- 真实收款、PayPal/Stripe Connect、带平台抽成的结账（`PLATFORM_TAKE_RATE_*`）。
- 商家模块的操作界面：Store Manager、Booking Manager、Analytics、`/manage/<slug>`、`/app/settings`。发布“business”模板时，`public_url` 会指到 `/manage/<slug>`，那是商家后台，不是画布。阶段 1 不应改这些模块的业务逻辑，桌面里也不应把它们当成创作功能。
- 给别人扫的二维码。发布 URL 是相对路径；不设 `PUBLIC_BASE_URL` 时，只有本机 Flask 能打开。`PUBLIC_BASE_URL` 默认空。
- 把上传目录放到用户数据目录之后，现有 `/static/uploads/` URL 会失效（见第 2 节）。
- Postgres / RDS。若环境里留着 `DATABASE_URL`，本地模式会连错库。
- Geist CDN。功能不受影响，离线时字体变样。
- 账号设置页 `/app/settings#account`（侧栏仍有链接）。Electron 对同源导航放行，点进去会离开创作壳。

公开预览和本机表单提交不依赖登录。预约写入依赖 store 行，默认租户创建时会有；若以后去掉 `ensure_workspace_store` 的副作用，预约接口会 409。

## 5. 平台相关假设

Builder 的 Python 路径多用 `pathlib.Path`（`/` 运算符在 Windows 上也会拼对）。没有在创作模块里调用 shell，也没有写死 `\`。

需要在桌面方案里处理的假设：

- **监听地址。** `app.py` 与 `scripts/dev_studio_sqlite.py` 的默认 `HOST` 是 `0.0.0.0`，不是 `127.0.0.1`。端口默认 `5001`（注释写明是为了躲开 macOS AirPlay 占用的 5000）。没有启动令牌。现有 Electron 只校验 Origin 是否等于 `serverUrl`，不校验本机令牌。
- **密钥文件位置。** `.dev_secret_key` 写在程序目录。打包后 macOS 的 `.app`、Windows 的 Program Files、Linux 的只读安装前缀都可能不可写。应改到用户数据目录，并用环境变量。
- **SQLite 方言。** `bos/workspace_store.py` 使用 `last_insert_rowid()`。`COLLATE NOCASE` 出现在商店查询里。这些在 SQLite 上可用；桌面不应走 Postgres 分支。
- **Electron 平台差异（已有，且合理）。** `window-all-closed` 在 `darwin` 上不退出；协议 `zintriq` 在 macOS 走 `open-url`，Windows/Linux 第二实例走 `argv`。`safeStorage` 在 Linux 上依赖 Secret Service（GNOME Keyring / KWallet），不可用时 token 以明文 base64 落地。
- **开发文档里的 Unix 路径。** `desktop/README.md` 写的是 `.venv/bin/python`。Windows 是 `.venv\Scripts\python.exe`。
- **原生依赖。** `requirements.txt` 里的 `cryptography`、`psycopg[binary]`、`qrcode[pil]`（Pillow）靠 wheel。三平台都有官方 wheel；不要在安装时从源码编译。桌面阶段 1 可以不装 Postgres 驱动，但现在它是硬依赖，`import app` 不强制 import psycopg（`db_adapter` 把 ImportError 吃掉）。
- **商家表默认时区** `events.timezone` 默认 `Asia/Singapore`。这是 `init_db` 里的商家表，不是画布逻辑。桌面第一次 `init_db` 仍会执行这段 SQL。
- **preload 过宽。** `zintriqDesktop.openExternal` 把任意字符串交给 `shell.openExternal`，主进程没有限制 scheme。`getToken` 把 Bearer token 交进渲染进程。`contextIsolation`、`sandbox`、`nodeIntegration: false` 已经符合目标。没有 CSP。窗口对同源任意路径放行（包括 `/manage`、`/app/settings`）。
- **跨平台打包。** `desktop/package.json` 已声明 mac dmg/zip、win nsis/portable、linux AppImage/deb。在一台机器上打另外两个系统的包需要 electron-builder 的额外工具链，代码里没有这个步骤。

`app.py` 的 favicon 使用 `os.path.join`，这是跨平台的，不是缺陷。

## 6. 启动、端口、环境变量、依赖

### 现在怎么启动

```bash
# Web / 本机 Flask（仓库根目录）
python app.py
# 等价：PORT 默认 5001，HOST 默认 0.0.0.0，debug=True
# 会调用 init_db()

# 强制 SQLite、忽略 .env.local 里的 DATABASE_URL
python scripts/dev_studio_sqlite.py

# 已有 Electron 壳（不启动子进程）
cd desktop && npm install && npm start
# 默认打开 http://127.0.0.1:5001 ，没 token 时是 /studio/desktop
```

健康检查：`GET /healthz`（`observability/health.py`）。

### 端口与主机

| 变量 | 默认 | 谁读 |
| --- | --- | --- |
| `PORT` | `5001` | `app.py`、`dev_studio_sqlite.py` |
| `HOST` | `0.0.0.0` | 同上 |
| `ZINTRIQ_SERVER_URL` | `http://127.0.0.1:5001` | `desktop/main.js`，也可写在 `desktop/.env.desktop.json` 的 `serverUrl` |

Flask 不会读 Electron 实际监听的端口。两边要同时改。

### 和桌面相关的环境变量

数据与进程：`SQLITE_PATH`、`DATABASE_URL`、`DATABASE_IAM_AUTH`、`AWS_REGION`、`SECRET_KEY`、`SESSION_COOKIE_SECURE`、`PUBLIC_BASE_URL`、`FLASK_USE_RELOADER`、`ENV` / `FLASK_ENV`、`LOG_LEVEL`、`LOG_DIR`。

身份：`AUTH_PROVIDER`、`AUTH0_DOMAIN`、`AUTH0_CLIENT_ID`、`AUTH0_CLIENT_SECRET`、`AUTH0_CALLBACK_URL`、`AUTH0_NATIVE_CLIENT_ID`、`AUTH0_AUDIENCE`、`STUDIO_DEEP_LINK_SCHEME`（默认 `zintriq`）。

邮件 / 短信 / 支付 / 人机验证：`EMAIL_PROVIDER`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM`、`SMTP_USE_TLS`、`SMTP_USE_SSL`、`PAYMENT_PROVIDER`、`STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`、`PAYPAL_*`、`PAYPAY_*`、`TWILIO_ACCOUNT_SID`、`TWILIO_AUTH_TOKEN`、`TWILIO_FROM_NUMBER`、`TURNSTILE_SITE_KEY`、`TURNSTILE_SECRET_KEY`、`TURNSTILE_REQUIRED`、`CALENDAR_PROVIDER`。

安装包下载页（营销，不是创作）：`STUDIO_DOWNLOAD_MAC_URL`、`STUDIO_DOWNLOAD_WIN_URL`、`STUDIO_DOWNLOAD_LINUX_URL`。

没有 `ZINTRIQ_DESKTOP`。没有上传目录变量。没有本机访问令牌变量。

### Python 依赖（`requirements.txt`）

```
Flask>=3.0
cryptography>=42.0
psycopg[binary]>=3.1
qrcode[pil]>=7.4
```

桌面 Node 依赖（`desktop/package.json` 的 devDependencies）：`electron` ^33.2.0、`electron-builder` ^25.1.8。没有运行时 npm 依赖。

测试：`tests/test_studio_surfaces.py` 覆盖 Studio 表面和 PKCE 交换的假 Auth0。没有单独的 Universal Builder 测试文件。另外还有登录相关测试（`test_auth0_callback.py`、`test_email_login_standalone.py` 等），和桌面创作无直接关系。

## 7. 建议的最小改动（风险从低到高）

只列阶段 1。每一项都应先单独做，并保持 Web 在不设 `ZINTRIQ_DESKTOP` 时行为不变。

1. **文档与启动开关，不改行为。** 约定 `ZINTRIQ_DESKTOP=1`、`HOST=127.0.0.1`、在 import 前设置 `SQLITE_PATH`、清空 `DATABASE_URL`。风险低，因为还不动路由。
2. **把 `DATABASE = sqlite_path()` 挪到读完环境之后**，或在桌面启动器里于 import 前写入 `SQLITE_PATH`。顺手让 `UPLOAD_DIR` 接受环境变量，默认仍是 `static/uploads`，Web 不变。风险低，但要保住测试里对 `app.DATABASE` 的 monkeypatch。
3. **桌面启动器只绑定 `127.0.0.1`，并生成一次性令牌。** Flask 在 `ZINTRIQ_DESKTOP=1` 时拒绝没有该令牌的请求；Electron 只把令牌放在主进程请求头里。不要默认 `0.0.0.0`，不要开 debug reloader（子进程会复制端口）。风险中低：Web 默认不进入该分支。
4. **本地所有者，不做登录 UI。** `ZINTRIQ_DESKTOP=1` 时确保一行本地 `users` 记录和 owner workspace，并用现有 session 或一个只在本机有效的 `zst_` token 通过 `current_user()`。不要改 `bos/permissions.py` 的角色表；沿用 owner + `workspace.update` 回退。风险中：门禁若写错，会把 Web 也变成免登录。必须用环境变量包住，并加一条“无该变量时 `/studio` 仍跳登录”的测试。
5. **Electron 改为拉起 Flask 子进程**，工作目录、Python 路径、`SQLITE_PATH`、上传目录、端口都来自配置（用户数据目录 + `path.join`）。退出时关掉子进程。三平台差异只放在“python 可执行文件在哪”。风险中：进程生命周期、端口占用、Windows 路径。
6. **收紧壳。** 加 CSP；导航白名单只留 `/studio`、`/studio/p/`、`/build/`、创作 API 和静态资源；Community 与 `/manage`、`/app/settings` 不进窗口。`openExternal` 只允许 `http:` / `https:`。preload 去掉“把任意 URL 交给主进程”的宽接口；本机令牌不要再注入 `localStorage`。风险中：白名单漏掉编辑器依赖的静态文件或预览 iframe，画布会空白。
7. **上传与密钥改到用户数据目录（仅桌面）。** 需要一条发送已上传文件的路由，或让桌面的 static 映射包含该目录。`SECRET_KEY` 不要再写进安装目录。风险中高：URL 和现有 `save_uploaded_image` 耦合在 `/static/uploads/`。
8. **先不要做的事。** 不要抽掉 Workspace 外键，不要改 bookings / CRM / feedback 的业务函数，不要把 Community 嵌进窗口，不要在这一阶段做签名、公证、自动更新。商家模块留在 Web。

### 建议的第一步改哪些文件（尚未改）

若下一步只做第 1–2 项（可配置路径 + 桌面进程读到正确的 SQLite），预计只碰：

- `db_adapter.py`（已有 `SQLITE_PATH`，可能只加注释或上传路径的同类函数）
- `app.py`（`DATABASE` / `UPLOAD_DIR` 的读取时机与上传目录环境变量）
- `scripts/dev_studio_sqlite.py` 或新建 `desktop` 用的启动入口（仍不改 Electron）
- 一条最小测试：设置 `SQLITE_PATH` 与上传目录环境变量后，连接和目录落在指定位置
- 本文件的后续修订

等确认后再改代码。

## 待办

- 桌面 Workspace 不应创建商家 `stores` 记录。当前 `ensure_default_workspace` 会调用 `ensure_workspace_store`，桌面模式复用了这条路径，所以本地所有者第一次进来时仍会插入一条 store。下一步应让桌面租户只建 workspace 成员，不写商家表。
- 打包阶段用 waitress 替换 Flask 开发服务器。现在 `ZINTRIQ_DESKTOP=1` 仍走开发服务器，只是绑在 `127.0.0.1` 并关掉 reloader。安装包里应改成 waitress，并继续只监听回环地址。
- 打包产物不得包含 `.env.local`、开发库 `marketqr.db`，以及仓库里的开发上传目录。桌面数据只来自 `ZINTRIQ_DATA_DIR`。
- 桌面 CSP 的 `script-src` 暂时保留 `'unsafe-inline'`。下一步改为 nonce，或把模板里的内联脚本（`window.STUDIO_BOOT`、`window.WORKSPACE_BOOT`、`window.__MQ_T__`）拆到静态文件。
- 升级本地 Python。当前开发虚拟环境是 3.9，已经过官方支持期。下一步升到与 CI 主版本一致的 3.11，并再跑桌面和 Web 测试。
- Community 阶段的作品包需要发布者签名。当前 `checksums.json` 只验证完整性，不验证来源。详见 `docs/project-packages.md`。
