# Zintriq Web — 产品门户规范

Oct 4, 2026 · 适配当前仓库（Flask + Jinja2）。原文案里的 Next.js / Auth0 / Clerk 栈**不采用**。收款已定为 **Stripe + Flask + 现有账号**（不是 Paddle，也不是 Next API）。本文件是双端分工的门户侧定义。

## 0. 分工

| 端 | 定位 | 包含 | 不包含 |
| --- | --- | --- | --- |
| **Web** | 产品门户（门面） | 宣传、展示、下载引导、账号、订阅、文档、法律 | 任何编辑器、任何 `/build` 运行时、任何创作画布、任何 builder API |
| **Desktop** | 创作工作站（工厂） | 全部编辑器、元系统、`/build/<slug>` Application、本地运行时、插件 | 对外营销站 |

Web 只负责：了解 → 下载 → 登录 → 订阅（及法律/文档）。  
一切「build」能力在 Desktop Application（`ZINTRIQ_DESKTOP=1`）。公开站点不得提供 `/build`、`/builder-runtime`、`/api/builder-core` 或 builder 静态资源。

中国大陆因法律原因**暂缓**上线服务，以后可能开放；公开页不写死「永不服务」。

## 1. 一句话

Web 端是 Zintriq 的官网 + 账号门户 + 下载入口。不含编辑器、创作工具、元系统执行。

## 2. 路径：现网 ↔ 文档 A

文档 A 的路径若与现网不同，**以现网为准**，不为此迁栈或做空页。

### 2.1 营销（现有）

| 文档 A | 现网 | 阶段 | 说明 |
| --- | --- | --- | --- |
| `/` 首页 | `/` | 首次上线 | 元空间定位；主 CTA 下载 |
| `/features` | **`/product`** | 首次上线 | 同一套元空间、可建造的边界。不建 `/features` |
| `/pricing` | `/pricing` | 首次上线 | 订阅；收款走 **Stripe**（Flask + 现有账号），公司注册前不开放购买 |
| `/about` `/contact` | 同 | 首次上线 | |
| `/status` | `/status` | 阶段 2 | 云同步与发布后再上 |
| `/showcase` | — | 有真实作品后再做 | 不恢复空展示页 |
| `/templates` `/blog` | **保持删除** | — | 模板/社区在 Desktop |
| `/plugins` | 只读插件包目录 | 本机装包在 Desktop；页上无编辑器 |
| 学习 | `/docs`、`/learn` 若未单列则并入文档 | 首次上线为文档入口 | 不单独做空 `/learn` |

硬件介绍 `/hardware` 是门户页（候补名单），不是编辑器。

### 2.2 账号（现有 + 阶段 2）

| 能力 | 现网 | 说明 |
| --- | --- | --- |
| 注册 / 登录 / 忘记密码 | `/register` `/login` 及现有找回流程 | 不迁 Clerk/Auth0 |
| 账号 | `/account` | 个人、设备、订阅入口 |
| 桌面授权 | `/desktop/authorize` | 阶段 2 |
| `/billing` `/devices` `/team` | 可落在 `/account` 分区，不必拆独立路由 | 阶段随订阅与团队开放 |
| `/security` | 现有「安全与隐私」营销页 + 账号内会话 | 勿与法律隐私页混淆 |

桌面**阶段 1**不做账号登录；Web 账号页可以存在，不因此在 Electron 里做登录。

### 2.3 下载与文档

| 文档 A | 现网 | 阶段 |
| --- | --- | --- |
| `/download` | `/download` | 首次上线；OS 检测、三平台 |
| `/download/releases` `/requirements` `/install` | 可先做下载页锚点/小节，独立路由有内容再拆 | |
| `/changelog` | `/changelog` | 首次上线 |
| `/docs` 及子页 | `/docs` 入口；子文档随 Desktop 版本补 | 首次上线仅入口分组 |
| `/docs/meta` | 文档分组，不是可运行元系统 | 概念文，无编辑器 |

### 2.4 法律

`/legal/*` 维持现网。收费前按公司主体再更新。

### 2.5 明确不做（Web）

- `/studio`、网页画布、可视化编程、元描述执行、模拟引擎、插件安装
- 网页社区浏览/导入（`/community` 已删）；阶段 2 仅允许 `/c/<id>` **跳板**
- 把 Flask 门户重写成 Next.js / `apps/web/`

## 3. 功能（门户侧，按现状）

| 项 | 现状 / 约束 |
| --- | --- |
| 多语言 | 现有 i18n；中英为内容源。不为此砍到「16 种」 |
| 主题 | 亮/暗，已有 |
| 响应式 / SEO | Flask SSR + 现有 canonical / hreflang |
| 动画 | 现有营销 CSS；不引入 Framer Motion |
| 定价切换 | 现有月/年；币种与税在结账时由 Stripe / 公司主体处理 |
| 分析 / 客服 / A/B | 未接；不因本文接入 PostHog、Intercom |
| 支付 | **Stripe + Flask + 现有账号**。Zintriq 是记录商户；Stripe 是处理方。公司与产品价目就绪前 `BILLING_ENABLED` 保持关闭。商家店内结账的 Stripe Connect **不是**官网订阅。 |
| 下载校验 / 镜像 / 断点 | 有包再补 SHA256 与 CDN；阶段 1 可不发布安装包 |
| 文档搜索 / 按 Desktop 版本切换 | 有文档体量后再做 |

## 4. 技术栈（本仓库）

| 层 | 技术 |
| --- | --- |
| 门户 | Flask、Jinja2、原生 JS、现有 `static/css` |
| 桌面 | `/desktop` Electron + 本地 Flask（`ZINTRIQ_DESKTOP=1`） |
| 数据 | 路径可配置的 SQLite（及现有适配） |
| 部署 | 现有站点部署；不强制 Vercel |

性能预算沿用设计步骤（Lighthouse 营销页）；不另开 Next 预算表。

## 5. 首页结构（门户，已落地方向）

- Nav：产品 · 硬件 · 定价 · 文档 · 下载
- Hero：元空间一句话（没有产品边界；边界也可以被建造）+ **下载 Desktop** + 次按钮到 `/product`
- 咖啡馆模拟：订单 / 规则 / 点单（文案与示意图，不是在网页里跑元系统）
- 实例格与「项目保存在你的电脑上」分开
- 硬件条：硬件是一种目标 → `/hardware`
- CTA：再下载

只读示意图可以有；**不可编辑**。

## 6. 开发顺序（门户，不替换 8 周 Next 计划）

1. 分工与规则（本文件 + Cursor 规则）— 本步
2. 营销文案与现有路由（已完成：首页/产品/硬件为开放元空间，公开页不写流程三步）
3. 下载页随安装包补全校验与系统要求
4. 账号/订阅随公司主体与 Stripe（Checkout / webhook 在独立实现步）
5. 文档与法律随产品真实能力
6. 有真实内容再考虑展示、博客、只读市场

桌面编辑器与元系统实现走 Desktop 路线，不在本规范展开。
