# Zintriq 元系统（核心）

Zintriq 的产品本体是**科技系统的元描述与实例化空间**，不是商家后台，也不是单一「建站工具」。

权威分层（仓库里已落地，不是愿景清单）：

1. **元描述** — 任何科技系统（及描述本身）可被描述  
2. **元模拟** — 描述可被模拟  
3. **元实例化** — 模拟结果可编译成目标产物  
4. **边界** — 边界本身是元系统对象：可描述、可模拟、可实例化（build），可注册、可扩展。不是流水线的最后一站。

宿主是 **Electron + 本地 Flask**（`desktop/`，`ZINTRIQ_DESKTOP=1`）。公开 Web 是门户，**不提供编辑器、画布或可运行的元系统 UI**。

## 与现仓库的关系

| 角色 | 位置 |
|---|---|
| **核心** | [`meta/`](../meta/) — 描述 / 模拟 / UIR / 实例化 / 边界 |
| 能力内核（过渡） | [`builder_kernel/`](../builder_kernel/) — 将逐步收成「软件/页面」边界上的实现，不再当作本体 |
| 宿主 | Studio（仅桌面）+ Electron（`desktop/`） |
| 外围 | 商家 bookings / CRM / feedback — 不进元核心；阶段 1 不改其业务逻辑 |

公开 Web 不提供 `/build`、`/builder-runtime`、`/api/builder-core` 或 `/static/builder/*`。那些是 Desktop Application 表面。未设 `ZINTRIQ_DESKTOP` 时门户行为不变。`meta/` 本身仍是纯 Python，不注册公开路由。门户 `/plugins` 是只读插件包目录，安装发生在桌面。

Workbench **视图插件**（约 28 个官方面 + pack 内额外领域插件）共用一份 `ZintriqEditorKit`：工具栏（Play / Duplicate / 增删行）、层级大纲（可过滤）、分组 Inspector（含 Transform / Camera / Light）、时间轴、Scene 视口网格与轴心 gizmo、表行增删、属性面板上的视图标记、本机 runtime 预览。仍是插件，不是 28 个独立大型应用，也不是配送 Unity。验收按「每个编辑器达到行业软件的本机核」，不是换引擎。

## 已锁（2026-10-05）

- 无限：`meta_level` 不封顶。嵌套系统用环检测；256 只是栈保险，不是元层上限。
- 实例化目标全部 compile 成本机产物（`web_build` / `desktop_host` / `device` / `os_host` / `canvas` / Desc / UIR / visual），包括 VR/芯片/机器人/打印/CNC/账本边界。
- 查询只走可视化条件树，禁止任意 SQL。
- 桌面连接器白名单。分析/遥测默认关。签名公证与自动更新停。
- 硬件配对（Phase H）现在做，不等「产品完成」。
- 本机大模型：权重只在 `ZINTRIQ_DATA_DIR/models`（GGUF 走 `ZINTRIQ_LLAMA_BIN`，或 `local-weights` JSON 表）。`/api/ai`、`/api/ai/chat`、`/api/ai/embed`、`/api/ai/tools` 仅 `ZINTRIQ_DESKTOP=1`（Workbench 走 `/api/builder-core/meta/ai/*`）。没有权重文件返回 4xx，不用哈希冒充生成，也不把托管 OpenAI 当完成条件。

The catalog of systems is open. A plugin of any form (view, AI, engine, world, layout, …) can enter Community, install on this machine, and become a project part. That project can instantiate another plugin. Transport stays `127.0.0.1`; this is not a third-party CDN or WAN save path.

**Zintriq Engine** (`meta/runtime/engine.py`) Play/Stop 在同一 Workbench 上 dt 步进 scene + physics + skin，预制 instance 来自 Desc；不是 Unity。**Zintriq World** Place + 对象复制 + loopback 双进程目录同步，脚本只走 Desc/逻辑核；不是 Roblox 协议。最低产出：工具栏 **Make**（`POST /api/builder-core/meta/produce`）用种子 Desc 实例化，不依赖权重。Workbench 侧栏本机助手可关，只走 `window.zintriq.http.*`。

## 本机运行与未签名 pack

开发态从 `desktop/` 执行 `npm run dev` / `electron .`。Electron 启动时若存在 `ZINTRIQ_DATA_DIR/desktop/<slug>/launch.json` 则读取 studio 路径与 editors（仍只绑定 `127.0.0.1`）；**没有该文件时行为与现在相同**。

未签名目录包：`cd desktop && npm run pack`（`--dir --publish never`）。商店安装包、Developer ID / Authenticode / Apple 公证仍等产品完成后再配 `CSC_LINK`、`APPLE_ID`。

## 已落地

### 元描述（`meta.description`）

- **原子**：`null` / `bool` / `int` / `float` / `string` / `bytes`；可选 `value` 或 `ref`、`unit`、约束（`min` / `max` / `enum` / `pattern`）  
- **复合**：`struct` / `sequence` / `mapping`（mapping 键暂限字符串）  
- **关系**：结构等价 `equivalent`；引用依赖收集 `depends_on`  
- **序列化**：规范 JSON 往返（`sort_keys`）  

测试：`tests/test_meta_description.py`。

### 元模拟（`meta.simulation`）

- 离散**状态机**描述（`kind=state_machine`）  
- `step(machine, event)`：一步转移；无匹配边则失败  
- 与元描述双向：`machine_to_desc` / `machine_from_desc`  

测试：`tests/test_meta_simulation.py`。

### 统一中间表示（`meta.uir`）

双表达最小核心：**视觉 ≡ 代码 ≡ UIR ≡ Desc**。编辑器里改 Code / Visual 属性 / UIR 会 debounce 预览，其它表达跟着刷新（不覆盖正在编辑的那一面）。

- 图节点：`literal` / `reference` / `record` / `array` / `map`  
- `from_desc` / `to_desc`：Desc ↔ UIR  
- `to_visual` / `from_visual`：UIR ↔ 视觉树；Workbench **Graph** 把这棵树画成 SVG（节点与边），不是 builder 画布节点树  
- **视图标记**（`properties.view`：`transform` / `pivot` / `marks` / `type`）：只挂在 UIR 视觉投影上；`to_desc` 会剥掉，文档仍是 Desc。不是第二份图数据库。`meta.uir.marks` 负责规范化与合并。  
- `to_code` / `from_code`：UIR ↔ 代码；本步仅 `language=json`（规范 Desc JSON）  
- 公理：同一 Desc 经 visual / code 往返后 `equivalent`；状态机 Desc 经 UIR 后仍可 `step`  

测试：`tests/test_meta_uir.py`。

### 元实例化（`meta.instantiation`）

`instantiate(source, target=…, events=…)` 把 Desc 或状态机（可先按事件步进）编译成 `Artifact`：

| target | 产物 |
|---|---|
| `desc` | 规范 Desc JSON |
| `uir` | UIR 代码 JSON（与 Desc 等价） |
| `visual` | 视觉树 JSON |
| `desktop_host` | 同一 Electron+Flask 宿主配方（`127.0.0.1`，打开 `/studio`）；不是第二份二进制 |

- slug：1–64 位小写字母/数字与内部连字符；禁止路径分隔符  
- 校验和：UTF-8 SHA-256  
- **不写数据库、不挂 Flask 路由**；桌面宿主把 `web_build` 写进 `ZINTRIQ_DATA_DIR/artifacts/`  

测试：`tests/test_meta_instantiation.py`、`tests/test_desktop_meta_apply.py`。

### 边界（`meta.boundary`）与元空间（`meta.space`）

- 内置边界：`software.page`、`hardware.module`、`os.surface`、`meta.space`，以及可实例化的领域边界（`scene` / `cad.solid` / `commerce.checkout` / `social.channel` / `media.channel` / `ai` / `chip` / `vr.space` / `robotics.cell` / `print3d.job` / `cnc.job` / `chain.ledger` 等）。领域描述实例化为 **本机可运行的 `web_build` / `device` 宿主**，不是 Unity / EDA / 公链整栈。边界集合可继续扩展。 
- **`meta.space` 不是进程内旁路注册表。** 它是一份 `kind=meta.system`、`id=meta.space` 的描述：`parts` 里每一项都是 `kind=meta.boundary`。进程内表只是这份空间在运行时的索引（`register` / `get` / `list_boundaries` / `space_desc()`）。  
- **`kind=meta.boundary` 描述可被实例化**：写入空间并可以 `web_build` 到 `/build/<slug>`（`data-page-kind="meta.boundary"`）。  
- **`kind=meta.system`**：一份描述的 `parts` 是其它描述。实例化时**每个部件走同一条 build 路径**（按其边界目标 `desc` / `uir` / `visual` / `web_build` 调用 `instantiate`），系统本身是这些产物的 `web_build` 索引。嵌套系统用 `parent-child` 键；嵌套 `software.site` 展开全部页面（home 用部件键，其它页 `part-page`）。深度最多 3、部件最多 32。非 `web_build` 部件在 `/build/<slug>/<key>` 提供 JSON。  
- Workbench **Space**（`/studio/space`）把这份 `meta.space` 当文档打开：边界是正文里的部分，不是页签列表。`?space=1` 会转到 `/studio/space`。

### 桌面宿主（Application）

- Studio（桌面 `/studio`）是 **Workbench**：一份引擎，文档是描述。Meta 面：**Library**、**Describe**、**Simulate**、**Instantiate**、**Space**（`meta.space` 文档）、**Community**。元系统是内置服务，不是第 27/28 号编辑器。视图插件合同：`render` / `hitTest` / `edit`，读写同一份 Desc（经 visual）。**Diagram** 加上另外 27 个视图（Scene … Meta-meta）挂在 Describe 的共用宿主 `#me-plugin-host`（`static/studio/editors/pack.js`）。名为 Meta / Meta-meta 的是描述上的视图，不是第二份 `meta/` 引擎。Code / Graph / UIR 等仍是 Meta 窗格。Studio 脚本走 `window.zintriq.http`；桌面里这条通道经 Electron preload IPC（`studio:http`）打到 127.0.0.1，渲染进程不自己带启动令牌。路径只放行 `/api/builder-core/meta/`。`/studio/p/<id>` 旧组合编辑器已关掉。body 含 list / quote / code 块；heading 仅 h2/h3。描述页有 Undo/Redo。组合编辑器脚本 `universal-builder.js` 在桌面也 404。  
- 工厂可 **Remove** 本地草稿与实例化产物（`drafts/`、`artifacts/`、`sites/`、`assets/`），不经云。桌面冒烟用 zip 往返 `software.site`，不再建 `builder_projects`。  
- 应用菜单 **File → Import zip / Export site** 走本机 `meta` zip（系统对话框）。组合包 IPC（`.zintriq` / `transfer_host`）已从 Electron 拿掉；`/api/builder-core/transfer/export|preview|commit` 在桌面也 404。
- `POST /api/builder-core/meta/drafts`：草稿原子写入 `ZINTRIQ_DATA_DIR/drafts/`（可未通过校验的 JSON，避免丢字）  
- `/studio/meta` 无草稿时默认 `software.site`（home/about + theme）；有本地草稿则恢复；`?new=1`（工厂 **New description** / File → New description）分配未占用 slug，不打开当前草稿；状态机仍可插入  
- `POST /api/builder-core/meta/instantiate`：按描述自身目标编译（可省略 `target`）；`web_build` 写入 sites + zip，`desc` / `uir` / `visual` 只写 artifact，`/build/<slug>/…` 提供 JSON。`preview` 同样按目标预览（非 `web_build` 显示编译产物 JSON，不写 artifacts）。`POST /api/builder-core/meta/page/<slug>/step` 在已存产物上前进一步，**沿用该产物的 target**，不改写成 `web_build`。  
- `POST /api/builder-core/meta/step`：状态机一次 `step`；`preview` 附带 `simulation.{state,events}`  
- 编辑器：当前态 + 合法事件按钮 + atom/struct/sequence/mapping/page/site/boundary/system 插入  
- `/build/<slug>/<page>`：`kind=software.site` 或多页 `meta.system` 导航；`GET /build/<slug>` 跳到 home（或第一页）  
- Instantiate 把相对链接 HTML 与 `meta.json` 写到 `ZINTRIQ_DATA_DIR/sites/<slug>/`；zip 可下载；`POST …/sites/import` 用 `meta.json` 再实例化（不信任 zip 内 HTML）  
- 本地图片：body `image` 块仅文件名（png/jpg/gif/webp）；`POST …/sites/<slug>/assets` 写入 `ZINTRIQ_DATA_DIR/assets/<slug>/`；`/build/<slug>/assets/<name>` 提供文件；静态 HTML 用相对 `src`；编辑器预览用 data URL；zip 带走图片，导入嗅探魔数（拒 svg）  
- Studio 首页 / 侧栏列出 `ZINTRIQ_DATA_DIR` 草稿与 `/build` 产物；`GET /api/builder-core/meta/index`  
- `/build` 与静态 HTML：`theme.background|color|accent` 仅 `#rgb` / `#rrggbb`；`theme.measure` 16–80（rem）、`theme.space` 8–96（px）仅 int  
- 编辑器 Preview / Step 返回 `page_html`（沙箱 iframe `allow-scripts`；站内链 `postMessage` 切页，不写 artifacts）  
- 编辑器页签 **Add page / Remove page**：改当前 `software.site` 的 `pages`（最多 32 页，至少留一页）；根站点或 `meta.system` 里展开后的嵌套站点都可以，页签 key 与 `/build/<slug>/<page>` 一致。根或部件若是 `software.page`，Add page 先把它升成站点（原文当 home）再加页。  
- 编辑器页签 **Add part / Remove part / Duplicate part / Move part**：改当前 `meta.system` 的 `parts`（最多 32，至少留一个）。Add 加在拥有当前页签的那一层系统上（默认 `software.page`）；Duplicate 插在源部件后（新 key 如 `home-2`，标题加 copy）；Move 与邻居对调。Remove 只在部件主页（展开 key 等于部件 key）上允许，避免在 `guide-about` 上误删整个站点部件。  
- 编辑器 **Apply copy**：改站点标题、当前页 `key`（并改写 body `to`）、`title` 与 `body` 块。系统里的 `software.page` 部件同样可改文案，并同步部件标题；Page key 在部件主页上可改部件 key。`meta.boundary`（根或系统部件）改 `name`、`id`、`surface`、`target`、`meta_level`，并同步部件标题；Page key 在部件主页上可改部件 key。嵌套 `meta.system` 部件改系统标题，并同步部件标题 / 部件 key。根 `meta.system` 另有 **System title**。预览带 `copy_surface` / `can_page_ops` / `can_theme`：当前键不是 page/site 时不显示 Add/Duplicate/Remove/Move page 和 Apply theme。  
- 编辑器 **Step**：`POST /api/builder-core/meta/step` 按当前页签的 flatten key 步进该部件上的状态机（没有则退回根描述），并刷新整份预览（含 copy/theme）。  
- 编辑器页签 **Move left / right**：改 `pages` 顺序。根或部件若是 `software.page`，先升成站点再移动（单页时顺序不变）。  
- 编辑器 **Apply theme**：`scope=site` 写根主题，`scope=page` 写当前页（渲染时页覆盖根）  
- Instantiate 后显示 **Download zip**；工具栏 **Import zip** 用 `meta.json` 再实例化并载入编辑器  
- 编辑器页签 **Duplicate page**：复制当前页（新 key 如 `about-2`，标题加 copy）。根或部件若是 `software.page`，先升成站点再复制。
- 编辑器 **Upload image**：写入本地 assets，当前页加 `image` 块（alt + 文件名）；图库可点选插入 / Remove（`GET …/assets`、`POST …/assets/remove`）

## 明确延后

- 硬件店铺与实物发货
- **中国大陆地区服务**：因法律原因**暂时搁置**
- 权重级托管 LLM、卡组织清算、影视成片流水线：需作者自备模型 / 收单 / 编码器；元系统只实例化本机会话与产物

- `/build/<slug>` 只在 Desktop Application 内。门户 404。桌面 HTML 404/403/500 用 Studio 页（Back to Studio），不渲染营销站。`/` 在桌面重定向到 `/studio`。

## 阶段门槛

阶段 1 已于 2026-10-04 验收通过。阶段 2：账号由网站核对后同步进桌面；**未登录不能进入 Studio**。云草稿、发布、应用内社区、更新检查已落地。**macOS 公证 / Windows 签名与自动更新安装保持停**，产品完成后再配 `CSC_LINK`、`APPLE_ID`。硬件配对在桌面本机做（串口 / ESPHome / 打印与 CNC 产物），不是等产品完成。

## 下一步

1. 产品完成后再把 Developer ID / Authenticode / Apple 公证密钥配进发布机  
2. 托管页仍不运行元系统（公开页只是入口；`/plugins` 只读） 
