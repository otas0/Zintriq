# Zintriq 官网设计规范 v2.0（适配落地）

2026-10-04。原文案按 Next.js 写出；**本仓库不采用 Next.js**。本文是把 v2.0 像素级规范**改写成当前 Flask + Jinja2 + 原生 CSS/JS 栈**后的唯一对照表。

配套：双端分工见 [web-portal-spec.md](./web-portal-spec.md)；内容口径见 [website-content.md](./website-content.md)；黄色填充与动效底线见 [design-spec.md](./design-spec.md)。

**本步只定规范，不实现第 6–12 章页面。**

---

## 0. 栈与支付（覆盖原文）

| 原文案 | 本仓库 |
| --- | --- |
| Next.js App Router、`apps/web` | Flask + Jinja2；模板在 `templates/`，营销 CSS 在 `static/css/` |
| Clerk / NextAuth | **现有账号系统**（登录、注册、会话已在 Web 门户） |
| Stripe Checkout + Next API | **Stripe + Flask**；结账与 webhook 走现有应用，不新建 Next 路由 |
| Paddle（[web-portal-spec](./web-portal-spec.md) 初稿） | **改为 Stripe**。公司主体办妥前仍不开放真实购买；页上继续「即将开放 / 通知我」，不假装可付 |
| 自托管 Inter Variable + `preload` | Inter Variable 仅 CSS `@font-face` + `unicode-range: U+0000-00FF`；**禁止** HTML `preload` Inter |
| 品牌蓝 / `rgba(59,130,246)` glow | **不采用**。强调填充仍是 `#F5D547`（`--accent`） |

Web 端仍是门户：了解 → 下载 → 登录 → 订阅。编辑器、画布、元系统运行时只在 Desktop。

---

## 1. 原则（保留）

1. **诚实。** 不造用户数、评价、logo 墙、v1.0 已上线徽章。
2. **产品优先。** 首屏用现有 HTML 模拟界面（咖啡馆：订单 / 规则 / 点单），不靠流程口号。
3. **克制。** 动效 ≤ 300ms，只动 `transform` / `opacity`。
4. **可访问。** `prefers-reduced-motion` 关闭过渡；焦点环可见；对比度达标。
5. **跨平台门户。** 设计服务于公开站点；桌面壳不因此改营销视觉。

不采用原文「不是 X」宣言体；不采用「Free $0 forever」作为定价承诺。

---

## 2. 色彩（第 5 章：保留现网黄，不换蓝）

语义色继续用现有 CSS 变量，**不要**引入 `--bg` / `--text` / `--blue` 第二套命名。

| 语义 | 现用变量 | 值（现行） | 用法 |
| --- | --- | --- | --- |
| 页背景 | `--color-bg` | `light-dark(#FAFAF8, #0F1014)` | 页面底 |
| 表面 | `--color-surface` | `light-dark(#FFFFFF, #1C1D24)` | 卡片、页眉 |
| 次表面 | `--color-surface-2` | `light-dark(#F7F6F2, #24252E)` | 嵌套块 |
| 边框 | `--color-border` | `light-dark(#E4E2DC, #2E303A)` | 1px 分割 |
| 主文 | `--color-text` | `light-dark(#17171A, #F2F2F4)` | 标题、正文 |
| 次文 | `--color-text-muted` | `light-dark(#5C5B57, #A8A9B2)` | 说明 |
| 强调填充 | `--color-accent-solid` / `--yellow-9` | `#F5D547` | **仅实心填充**：主 CTA、少量高亮条、状态点 |
| 强调上的字 | `--color-on-accent` | `#141414` | 黄底字 |
| 浅色强调字 | `--color-accent-text` | `light-dark(#7A5C00, #E8C94A)` | 浅色主题链/字；**禁止**用 `#F5D547` 当字色 |
| 危险 | `--color-danger-text` | `light-dark(#B42318, #F97066)` | 错误 |
| 成功 | `--color-success-text` | `light-dark(#067647, #47CD89)` | 成功 |

原文 `--bg-card: #111118`、`--border: #1E1E2E`、蓝色 glow **不映射、不实施**。深色表面已从纯黑抬到 `--bg` / `--surface` 黄灰底。

黄的规则（与 [design-spec.md](./design-spec.md) 一致）：

- 可以：主按钮背景、选中 Tab 底、少量实心徽章。
- 不可以：大面积背景、细描边当强调、浅底黄字、焦点环只用黄。

---

## 3. 字体（第 1 章，改映射）

| 角色 | 落地 |
| --- | --- |
| 拉丁 UI / 英文标题 | `Inter`，`static/fonts/inter/InterVariable.woff2`，`font-display: swap`，`unicode-range: U+0000-00FF` |
| 中文正文 | 系统栈：`-apple-system, "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif` |
| 等宽（代码、规格） | `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` |

**禁止**为 Inter 增加 `<link rel="preload">`（LCP）。不引入 Space Grotesk / Satoshi / 第二套展示字体。

字号阶梯用现有 `--text-*` / 页面 class，不另建 `--text-hero` 除非后续单步扩 token。行高正文约 1.75；中文 `text-autospace: normal`。

---

## 4. 间距与圆角（第 2–3 章，映射现 token）

8px 网格，用已有变量，不新增 `--space-1` 平行系统。

| 意图 | 现用 |
| --- | --- |
| 控件内边距 | `--space-2` … `--space-4` |
| 卡片内边距 | `--space-5` / `--space-6` |
| 区块垂直节奏 | `--space-7` / `--space-8` / `--section-y` |
| 全站圆角 | `--radius-sm` / `--radius-md` / `--radius-lg`（约 6 / 10 / 16） |
| 主按钮 | `--radius-md`，不要全圆 pill（除非现有 chip） |

原文 `rounded-2xl` / `rounded-3xl` 对到 `--radius-lg`，不要再加大一档。

---

## 5. 阴影与边框（第 4 章）

| 意图 | 现用 |
| --- | --- |
| 静息卡片 | `--shadow-1` 或仅 `--color-border` |
| 悬浮 | `--shadow-2`，位移小、不投影色蓝 |
| 页眉 | 现有 `blur` + 半透明 `--surface`，不加重毛玻璃 |

禁止：多层品牌色外发光、网格+扫描线作为主装饰。点阵/径向光可极克制，且必须让位于真实界面模拟。

---

## 6. 动效（对齐 D4，不扩库）

- 时长：`--dur-fast` / `--dur-base` / `--dur-slow`（≤ 300ms）。
- 缓动：`--ease-std` / `--ease-soft`。
- 只过渡 `transform`、`opacity`、`color`/`background-color`（颜色切换短）。
- `@media (prefers-reduced-motion: reduce)` 已有则保持。
- 不引入 Framer Motion / GSAP。

---

## 7. 导航与信息架构（第 6 章 → 现网路径）

不按原文改成 `/features`。现网 IA：

| 导航 | 路径 |
| --- | --- |
| 产品 | `/product` |
| 定价 | `/pricing` |
| 硬件 | `/hardware` |
| 文档 | `/docs` |
| 下载 | `/download` |
| 关于 | `/about` |
| 登录 / 账户 | 现有账号路由 |

页脚：法律、状态（阶段 2 再强调）、语言切换保持现实现。不为此规范新增顶栏项。

---

## 8. 首页结构（第 7 章 → 积压）

原文 12 屏（英雄视频、画布演示、用户证言、无限滚动 logo、定价对比动画等）**不按屏实现**。

当前首页已对齐的口径：

- 定位：科技系统的元空间。没有产品边界。边界也可以被建造。
- 主 CTA：下载桌面工作站。
- 次 CTA：看产品。
- 演示：同一家咖啡馆的三个面（订单 / 规则 / 点单），非可运行编辑器。
- 实例格：咖啡馆、预约台、柜台、传感器、装置、模型。保存/导出单独成段。
- 硬件条：硬件是一种目标 → `/hardware`。
- 构建日志：真实日期，不造评价。

后续若做视觉加强，仍用 HTML/CSS 模拟，**禁止**在公开站点嵌入创作画布。

---

## 9. 组件对照（第 8 章）

实现时复用 `static/css/components.css` 与现有 class，不要平行造一套 `ui/`。

| 原文组件 | 现网 |
| --- | --- |
| Button primary | `.btn` / `.btn-primary`（黄底 `--on-accent` 字） |
| Button secondary | `.btn-ghost` / 描边按钮 |
| Card | `.card` / `.feature-card` |
| Chip / 积木标签 | `partials/block_chip.html` 等现有 chip |
| 表单 | 现有 `form` 控件；WCAG 目标尺寸 ≥ 24×24 |
| Toast / Modal | 已有则用已有；不新增营销弹窗拦截 |

---

## 10. 定价与结账（第 9 章）

- 展示层：`/pricing` 继续诚实候场；**开放购买前不放可点的假 Checkout**。
- 收款：**Stripe**（Checkout 或 Payment Links 由后续实现步决定），服务端 **Flask**。
- 身份：**现有账号**；支付成功绑定当前用户，不引入 Clerk。
- Webhook：Stripe → Flask，校验签名；不在本文展开密钥与实现。
- 文案：不用「Free $0 forever」；免费档若有，写清限额与「创作在桌面」。

中国大陆服务暂缓；定价页不写「永不对大陆销售」。

---

## 11. 产品 / 硬件 / 文档页（第 10 章）

已换脸口径（内容层，非本步改代码）：

- `/product`：同一套空间 + 未标注模拟窗 + 可建造的边界；不是流程三步，也不是五积木产品分类。
- `/hardware`：模块按上述三种**种类**陈述，候补名单，不假装商城。
- `/docs`：含元系统文档入口；不把官网变成 IDE。
- `/compare/*`：实例（咖啡馆、预约台、传感器、模型），不写类别墙。

视觉 token 按第 2–6 节；不新开 `/features`。

---

## 12. 响应式与主题（第 11 章）

- 断点：沿用现有 marketing CSS（约 640 / 960），不强制 Tailwind 默认。
- 主题：`color-scheme` + `light-dark()` + `data-theme` cookie，禁止首屏闪白/闪黑。
- RTL：逻辑属性（已有则保持）。

---

## 13. 明确不采用（第 12 章 + 原文杂质）

| 项 | 原因 |
| --- | --- |
| Next.js / `apps/web` | 双端已定为 Flask 门户 |
| 公开站创作画布 / 可运行元系统 | [web-portal-spec](./web-portal-spec.md) |
| Inter HTML preload | LCP |
| 品牌蓝 glow | 与黄强调冲突，且模板感 |
| 假证言、假指标、v1.0 launched | 诚实原则 |
| Free $0 forever | 未承诺的商业条款 |
| 新路由 `/features` | 现网 `/product` |
| 为 token 再写一套 `--bg-card` 蓝黑 | 已有语义变量 |
| 本步改商家 bookings/CRM | 桌面规则禁止 |

---

## 14. 积压（确认后另开步骤）

按需拆步，每次仍先计划再改代码：

1. ~~token 对照表~~ 已按 `static/css/tokens.css` 实名写入第 2–6 节。
2. ~~定价/门户 Stripe 文案~~ 已与 [web-portal-spec](./web-portal-spec.md)、[website-content](./website-content.md)、中英 i18n 对齐；购买按钮在 `BILLING_ENABLED` 关闭时仍是「即将开放」。
3. ~~首页/产品模拟图~~ 静态 HTML 咖啡馆模拟（非画布，无流程轨）。
4. ~~组件密度、焦点、表单 3.3.8~~ 门户登录/注册/找回与营销表单：标签关联、OTP 可粘贴、目标 ≥ 24×24（控件 44px）。
5. ~~Flask Stripe Checkout + webhook~~ 骨架已落：`billing_platform.py`，密钥用 `ZINTRIQ_STRIPE_*`，与商家 Connect 分开。默认 `BILLING_ENABLED` 关闭不收款。
6. **提醒（用户 2026-10-04）：** 稍后连接**真实 Stripe 账户**再开 live。未完成前不要设 `ZINTRIQ_STRIPE_LIVE=1`，不要用商家 Connect 的 `STRIPE_SECRET_KEY`。

---

## 15. 给实现代理的最短指令

- 颜色：只动 `--color-accent-solid` / `--yellow-9` 体系，黄填黑字。
- 字体：Inter 仅 CSS，不 preload。
- 支付：Stripe + Flask + 现有 session 用户。
- 路径：不要 `/features`，不要 Next。
- 公开 HTML：不要 editor、不要假评价、不要把描述/模拟/实例化写成产品口号。
