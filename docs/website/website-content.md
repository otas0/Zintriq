# Zintriq 网站内容方案

Oct 3, 2026 · @Matsu

## 改动概览

**Web 是门面，Desktop 是工厂。** 网站只负责了解、下载、账号、付款和访问已发布作品（阶段 2 的托管跳板）。网页 Builder 和网页社区直接删除：网站从未发布过，不需要跳转或迁移页。社区（Community）整体在桌面端里。收费前先注册公司，在此之前网站以“免费下载试用、订阅即将开放”上线。门户路径与阶段见 [web-portal-spec.md](./web-portal-spec.md)。

### 旧文案里已经不适用的内容

| 位置 | 旧说法 | 问题 | 处理 |
| --- | --- | --- | --- |
| 导航「Studio」、下载页「打开网页版 Studio」、「下载 Zintriq Studio」 | 网页 Builder 是入口之一；桌面端叫 Studio | 网页 Builder 删除；桌面端就叫 Zintriq | 删除入口和路由；全站不再出现“Studio” |
| 首页、工作原理「三种进入方式：模板 / 构建器 / 社区」 | 构建器和社区在网页上 | 创作和社区都在桌面端 | 改为「下载 → 在应用里从模板开始 → 保存并导出 / 发布」 |
| 社区页 `/community`、模板页 `/templates` | 网页上浏览、导入作品 | 社区在桌面端 | 直接删除 |
| 激活流程（`/build/<slug>`、`/manage/<store>`、「激活」） | 在网页里安装模板并发布 | 旧 Business App 流程 | 直接删除 |
| 下载页「社区留在网页端」「通过浏览器接力从社区导入」 | 社区只在网页 | 现在正好相反 | 改为“社区在应用里” |
| 下载页「请从 desktop/ 本地构建，或配置 STUDIO\_DOWNLOAD\_\*\_URL」 | 开发者提示 | 内部信息泄露到公开页面 | 改为面向用户的“即将推出”状态 |
| 下载页「租户（成员、账单、隔离）」 | 内部术语 | 用户看不懂 | 改为 Workspace、成员、权限 |
| 定价页 Free / $29 / $99、「Stripe/Braintree 尚未配置」 | 永久免费档 + 自建支付 | 已定：订阅、无永久免费档、**Stripe** 收款（Flask + 现有账号） | 重写，见定价一节 |
| 客户故事页、博客 | 示意引述、重复正文 | 空页和不实案例伤信任 | 直接删除，有真实内容再做 |
| 附录「顾客到店页」 | 扫码进店、市集与场馆 | 旧 Business App 产品 | 删除；以后由发布的作品自己提供 |
| 服务条款：捐赠/小费、Owner/Customer、二维码生成、评价聚合 | 旧产品的条款 | 与现在卖软件、托管作品、社区完全不符 | 重写，见「法律页需改动清单」 |
| 隐私政策：手机号必填；服务条款：邮箱必填 | 两页互相矛盾 | 同一事实两种说法 | 统一为实际注册方式 |
| 安全页「正在从技术栈移除 Google 服务」 | 进行中的内部事项 | 公开页面写半成品状态 | 删掉，完成后再写进更新日志 |

### 新文案的写法

- **先说是什么，少说不是什么。** 旧文案几乎每段都有“——不是 X”“绝不伪装成”，读起来像在和人争论。新文案正面陈述，对比只留在对比页。
- **元系统定位。** 对外主叙事是「科技系统的元空间」：没有产品边界；边界也可以被建造。咖啡馆、传感器、网站、模型不是产品线。编辑器只在桌面应用。中国大陆因法律原因暂缓，以后可能开放；公开页不写死「永不服务」。
- **用用户的词。** 中文写“社区”，品牌处写“Zintriq 社区”，英文写 Community；桌面端就叫 Zintriq，不加 Studio。不说“表面、组合套件、租户、诚实预览”。
- **只写现在真能做的。** 阶段 1 只有咖啡馆这类软件实例、本机保存与导出算「现在可用」，其他写「即将推出」；每条文案都标注从哪个阶段起显示。
- **每个页面一个主动作。** 首页和产品页的主按钮都是「下载」。
- **中文和英文各自写，不互译。** 英文用短句和动词开头；中文不加多余破折号和引号。

## 站点地图

主导航 5 项：**产品 · 硬件 · 定价 · 文档 · 下载**（下载做成按钮）。文档 A 里的 `/features` 对应本站 **`/product`（能力展示，不是网页编辑器）**。`/showcase` `/templates` `/marketplace` `/blog` 有真实内容前不上线。网站没有发布过，所以旧页面直接删除，不做 301 跳转。「阶段」一列指桌面端路线图阶段，到了该阶段再上线对应页面。

| 路径 | 页面 | 处理 | 阶段 | 说明 |
| --- | --- | --- | --- | --- |
| `/` | 首页 | 重写 | 首次上线 | 主动作：下载 |
| `/product` | 产品 | 新建 | 首次上线 | 同一套元空间、可建造的边界；主 CTA 下载 Desktop。阶段 2 可含社区介绍 |
| `/download` | 下载 | 重写 | 首次上线 | 自动识别系统；三个平台 |
| `/hardware` | 硬件 | 新建 | 首次上线 | 介绍 + 候补名单；硬件在独立店铺销售 |
| `/pricing` | 定价 | 重写 | 首次上线 | 公司注册前显示“订阅即将开放” |
| `/login` `/signup` `/account` | 账号 | 微调 | 首次上线 | 设备列表、订阅、Workspace 成员 |
| `/desktop/authorize` | 桌面登录授权 | 新建 | 阶段 2 | 授权码 + PKCE 的确认页 |
| `<作品地址>` | 已发布作品 | 新建外框 | 阶段 2 | 作品全屏，只加一个可收起的「用 Zintriq 制作」 |
| `/c/<id>` | 社区分享落地页 | 新建，允许搜索引擎收录 | 阶段 2 | 一张卡片：名称、封面、作者、「在 Zintriq 中打开」和下载 |
| `/checkout` | 结账 | 新建 | 公司注册后 | Stripe Checkout（Flask 建 session）；桌面端的订阅跳转到这里，回到现有账号 |
| `/docs` | 文档 | 重写入口 | 首次上线 | 先只有「开始」「创作」两组 |
| `/extend` | 开发者 | 微调 | 阶段 3 | 能力契约和 SDK 就绪后上线 |
| `/security` | 安全与隐私 | 微调 | 首次上线 | 加入桌面端、离线、同步 |
| `/compare/*` | 对比 | 保留 | 首次上线 | 不进导航 |
| `/changelog` | 更新日志 | 保留 | 首次上线 | 从桌面端第一个公开版本开始记录 |
| `/about` `/contact` | 关于、联系 | 微调 | 首次上线 |  |
| `/status` | 服务状态 | 新建 | 阶段 2 | 有云同步和发布后才需要 |
| `/translate` | 参与翻译 | 新建 | 首次上线 | 见「本地化规范」 |
| `/legal/*` | 法律页 | 重写 | 首次上线 | 收费前还要按公司主体再更新一次 |
| `/community` `/templates` `/primitives` `/how-it-works` `/compositions` `/connections` `/customers` `/blog` `/build/*` `/manage/*` 网页 Studio | 旧页面 | **删除** | — | 直接删除路由、模板和翻译键 |

已定：做并允许收录。理由：`/c/<id>`：创作者在微信、X、论坛里分享社区作品时，链接需要有个地方落脚：显示预览卡片，已安装的人点一下打开应用，没安装的人看到下载。它不是网页版社区，只是一个跳板。如果不要它，分享链接只能用 `zintriq://` 协议，在聊天软件里通常点不开。

## 全站

以下每条文案都带翻译键，可以直接写进 `i18n/locales/zh-Hans.json` 和 `en.json`。`{}` 是变量，翻译时保留。

### 导航

| 键 | 中文 | English |
| --- | --- | --- |
| nav.product | 产品 | Product |
| nav.hardware | 硬件 | Hardware |
| nav.pricing | 定价 | Pricing |
| nav.docs | 文档 | Docs |
| nav.download | 下载 | Download |
| nav.login | 登录 | Log in |
| nav.signup | 注册 | Sign up |
| nav.account | 我的账户 | Account |
| nav.logout | 退出登录 | Log out |
| nav.menu | 菜单 | Menu |
| nav.skip | 跳到正文 | Skip to content |

手机端：汉堡菜单内顺序同上，「下载」在手机上显示为「发送下载链接到邮箱」（见下载页）。

### 页脚

| 分组 | 中文 | English |
| --- | --- | --- |
| footer.col.product | 产品：产品介绍 · 下载 · 硬件 · 定价 · 更新日志 | Product: Overview · Download · Hardware · Pricing · Changelog |
| footer.col.resources | 资源：文档 · 参与翻译 | Resources: Docs · Help translate |
| footer.col.company | 关于：关于 Zintriq · 安全与隐私 · 联系我们 | Company: About · Security & privacy · Contact |
| footer.legal | 隐私政策 · 服务条款 · Cookie · 法律信息 | Privacy · Terms · Cookies · Legal |
| footer.region | 国家或地区：{region} · {language} | Region: {region} · {language} |
| footer.copyright | © {year} Zintriq | © {year} Zintriq |
| footer.residency | 运营于中国上海，数据存储于德国法兰克福（欧盟）。 | Operated from Shanghai, China. Data stored in Frankfurt, Germany (EU). |
| footer.mor | 软件订阅付款由 Stripe 处理。记录商户是 Zintriq；税费在结账时按地区计算。 | Software subscriptions are processed by Stripe. Zintriq is the merchant of record. Tax is calculated at checkout based on your location. |

「创作者」栏等社区付费上架开放、「博客」等有真实内容、「服务状态」等阶段 2 再加回页脚。`footer.mor` 只在 `BILLING_ENABLED` 打开后显示。Stripe 不是经销商；客服与退款走 Zintriq，不把 Paddle MoR 声明套过来。「保留所有权利」可以删掉。

### 地区选择

| 键 | 中文 | English |
| --- | --- | --- |
| region.title | 选择国家或地区 | Choose your region |
| region.lead | 地区决定价格币种和硬件是否可购买。语言在语言菜单里单独选择。 | Region sets currency and hardware availability. Language is chosen in the language menu. |
| region.suggested | 建议 | Suggested |
| region.all | 所有地区 | All regions |
| region.language\_only | 只切换语言 | Change language only |
| region.banner | 你似乎在{region}。要切换到{region}的语言和价格吗？ | Looks like you're in {region}. Switch to local language and prices? |
| region.switch | 切换 | Switch |
| region.stay | 留在这里 | Stay here |

地区和语言分开选：在法国的中文用户应该能用中文界面看欧元价格。这对少数语言用户尤其重要，很多人不在语言的主要地区。

## 首页 `/`

首页只回答三件事：这是什么（元空间）、空间里有什么、怎么开始下载。主按钮始终是下载。标注「阶段 2」的文案要等桌面端阶段 2（账号互通、云同步、发布）验收后再显示。不把描述 / 模拟 / 实例化写成公开流程。

### 1. 首屏

| 键 | 中文 | English |
| --- | --- | --- |
| home.hero.title | 本机创作。云端发布与同步。 | Build on your machine. Publish & sync in the cloud. |
| home.hero.lead | 免费下载。本机创作与导出。需要分享链接与跨设备同步时再订阅。 | Download free. Make and export offline on your computer. Subscribe when you want Publish & sync — share links and keep work across devices. |
| home.hero.cta\_download | 下载 {os} 版 | Download for {os} |
| home.hero.cta\_download\_generic | 下载 Zintriq | Download Zintriq |
| home.hero.cta\_mobile | 发送下载链接到邮箱 | Email me the download link |
| home.hero.cta\_secondary | 了解用法 | See how it works |
| home.hero.platforms | 支持 Windows、macOS、Linux | Windows, macOS and Linux |

### 2. 咖啡馆演示（不是流程）

公开首页不使用 `home.steps.*`（已从 en / zh-Hans 删除）。演示是同一家咖啡馆的三个面：订单、规则、点单。

| 键 | 中文 | English |
| --- | --- | --- |
| home.demo.title | 元空间里的一家咖啡馆 | A café in the meta-space |
| home.demo.tab.orders | 订单 | Orders |
| home.demo.tab.rules | 规则 | Rules |
| home.demo.tab.live | 点单 | Phone |
| home.layers.describe | 订单 | Orders |
| home.layers.simulate | 规则 | Rules |
| home.layers.instantiate | 点单 | Phone |

### 3. 编辑器表面

网页没有编辑器。`home.blocks.*` 已从 en / zh-Hans 删除。内部 `/__design` 的 chip 只用咖啡馆三面（订单 / 规则 / 点单）。

### 4. 能做什么

状态标签只有两种：「现在可用」「即将推出」。

| 键 | 中文 | English | 状态 |
| --- | --- | --- | --- |
| home.make.title | 同一套元空间里的系统 | Systems in the same meta-space |  |
| home.make.build | 咖啡馆 | A café | 现在可用 / Available now |
| home.make.booking | 预约台 | A booking desk | 即将推出 |
| home.make.store | 柜台 | A shop counter | 即将推出 |
| home.make.device | 传感器 | A sensor | 即将推出 |
| home.make.automation | 持续运转的装置 | A device that keeps running | 即将推出 |
| home.make.ai | 模型 | A model in the space | 即将推出 |

保存、导出、发布不放在实例格里，见「哪里都能用」。

### 5. 社区（阶段 2 起显示）

| 键 | 中文 | English |
| --- | --- | --- |
| home.community.title | 别从零开始 | Don't start from zero |
| home.community.lead | Zintriq 社区就在应用里：别人分享的模板和作品，都可以一键 Remix 成你自己的版本。做出好东西，也可以免费分享给别人。 | Zintriq Community is built into the app. Remix templates and projects others have shared into your own version, and share what you make for free. |
| home.community.note | 在应用左侧栏打开社区，需要联网。 | Open Community from the sidebar in the app. Requires an internet connection. |
| home.community.cta | 下载 Zintriq | Download Zintriq |

### 6. 硬件

| 键 | 中文 | English |
| --- | --- | --- |
| home.hw.badge | 即将推出 | Coming soon |
| home.hw.title | 硬件是一种目标 | Hardware is one target |
| home.hw.lead | 传感器、按钮、屏幕与继电器也在这套空间里。模块插上即可在应用中编辑。 | Sensors, buttons, displays, and relays live in the same space. Plug in a module and edit it in the app. |
| home.hw.cta | 加入候补名单 | Join the waitlist |

### 7. 哪里都能用

| 键 | 中文 | English | 阶段 |
| --- | --- | --- | --- |
| home.anywhere.title | 在电脑上建造，在任何地方打开。 | Build on your computer. Open it anywhere. | 2 |
| home.anywhere.title.s1 | 项目保存在你的电脑上 | Projects on your computer | 仅阶段 1 |
| home.anywhere.offline | **离线可用**：即将推出。上线后没网也能继续做。 | **Work offline**: coming later. You will be able to keep working without a network. | 未来 |
| home.anywhere.export | **随时导出**：整个项目或整个 Workspace 都能导出成文件，数据始终在你手里。 | **Export any time**: export a project or a whole workspace to a file. Your data stays in your hands. | 1 |
| home.anywhere.sync | **自动同步**：项目同步到云端，换台电脑继续做。也可以设为只保存在本机。 | **Synced**: projects sync to the cloud, so you can pick up on another computer. Or keep any project local-only. | 2 |
| home.anywhere.publish | **随处打开**：发布后是一个链接，手机、平板、电脑都能打开。 | **Open anywhere**: published work is a link on phones, tablets, and computers. | 2 |

### 8. 信任

| 键 | 中文 | English |
| --- | --- | --- |
| home.trust.title | 你的作品和数据归你 | Your work and data stay yours |
| home.trust.tracking | **不追踪你**：没有广告像素，没有第三方追踪。 | **No tracking**: no ad pixels, no third-party trackers. |
| home.trust.drafts | **草稿只有你看得到**：没发布的修改不会出现在公开链接上。 | **Drafts stay private**: unpublished changes never appear on your public link. |
| home.trust.workspace | **团队各自隔离**：每个 Workspace 有自己的成员和权限。 | **Separate workspaces**: each workspace has its own members and permissions. |
| home.trust.residency | **数据在欧盟**：存储于德国法兰克福。 | **Stored in the EU**: Frankfurt, Germany. |
| home.trust.cta | 安全与隐私 | Security & privacy |

### 9. 结尾

| 键 | 中文 | English |
| --- | --- | --- |
| home.end.title | 没有产品边界。边界也可以被建造。 | No product walls. Boundaries can be built. |
| home.end.pricing | 免费下载试用。付费方案将包含云同步和存储，没有额外费用。 | Free to download and try. Paid plans will include cloud sync and storage, with no extra fees. |
| home.end.cta\_download | 下载 Zintriq | Download Zintriq |
| home.end.cta\_pricing | 查看定价 | See pricing |

## 下载 `/download`

页面自动识别系统并把对应平台放在最上面；其他两个平台折叠在下方。下载后跳到「安装引导」状态，而不是留在原页。

### 页头与主下载

| 键 | 中文 | English |
| --- | --- | --- |
| dl.title | 下载 Zintriq | Download Zintriq |
| dl.lead | 在电脑上创作。本网站没有编辑器。 | Make systems on your computer. This website has no editor. |
| dl.detected | 已为你选择：{os} | Recommended for you: {os} |
| dl.version | 版本 {version} · {date} · {size} | Version {version} · {date} · {size} |
| dl.release\_notes | 本次更新内容 | What's new |
| dl.other | 其他平台 | Other platforms |
| dl.mac | macOS（Apple 芯片与 Intel）· .dmg | macOS (Apple silicon and Intel) · .dmg |
| dl.mac.req | 需要 macOS {min} 或更新版本 | Requires macOS {min} or later |
| dl.win | Windows（64 位）· 安装程序 | Windows (64-bit) · Installer |
| dl.win.req | 需要 Windows 10 或更新版本 | Requires Windows 10 or later |
| dl.linux | Linux · .AppImage / .deb | Linux · .AppImage / .deb |
| dl.linux.req | 适用于主流 64 位发行版 | For most 64-bit distributions |
| dl.btn | 下载 | Download |
| dl.checksum | 校验值（SHA-256） | Checksum (SHA-256) |
| dl.mobile | 在手机上呢？Zintriq 需要在电脑上安装。留下邮箱，我们把下载链接发给你。 | On your phone? Zintriq installs on a computer. Leave your email and we'll send you the link. |
| dl.mobile.sent | 已发送到 {email}。 | Sent to {email}. |
| dl.unavailable | {platform} 版即将推出。留下邮箱，上线时通知你。 | Zintriq for {platform} is coming soon. Leave your email and we'll tell you when it's ready. |

### 下载之后

| 键 | 中文 | English |
| --- | --- | --- |
| dl.after.title | 下载已开始 | Your download has started |
| dl.after.retry | 没有开始？重新下载 | Didn't start? Try again |
| dl.after.mac | 打开 .dmg，把 Zintriq 拖到「应用程序」文件夹，然后打开。 | Open the .dmg, drag Zintriq into Applications, then open it. |
| dl.after.win | 运行安装程序，按提示完成安装。 | Run the installer and follow the steps. |
| dl.after.win.smartscreen | 如果看到「Windows 已保护你的电脑」，点「更多信息」→「仍要运行」。我们正在办理 Windows 代码签名，完成后这个提示会消失。 | If you see “Windows protected your PC,” select More info → Run anyway. We're getting Windows code signing set up, and this warning will go away. |
| dl.after.linux | AppImage：加上可执行权限后运行。.deb：用系统的软件安装器打开。 | AppImage: make it executable, then run it. .deb: open it with your software installer. |
| dl.after.signin | 第一次打开时，应用会在浏览器里打开登录页。登录后自动回到应用。 | The first time you open the app, it opens a sign-in page in your browser. After you sign in, you'll be sent back to the app. |
| dl.after.no\_account | 还没有账号？现在注册 | No account yet? Sign up now |

`dl.after.win.smartscreen` 只在未签名期间显示。

### 桌面端与网站分别做什么

替换旧版「Studio 里有什么 / 留在网页端的内容」。

| 键 | 中文 | English | 阶段 |
| --- | --- | --- | --- |
| dl.split.title | 一个账号，两个入口 | One account, two places | 2 |
| dl.split.app.title | 在应用里 | In the app | 2 |
| dl.split.app.body | 创作和编辑项目 · 预览与发布 · 浏览、Remix 和分享社区作品 · 离线工作 | Create and edit projects · Preview and publish · Browse, remix and share on Community · Work offline | 2 |
| dl.split.web.title | 在网站 | On the web | 2 |
| dl.split.web.body | 管理账号、订阅和 Workspace 成员 · 付款与发票 · 已发布作品。网站上没有编辑器。 | Manage your account, subscription and workspace members · Payments and invoices · Published work. No editor on the web. | 2 |

阶段 1 时这一块整块不显示：那时还没有账号互通、发布和社区。`dl.after.signin`、`dl.after.no_account` 同理从阶段 2 起显示。

## 社区（应用内，阶段 2 起）

社区只在应用里，下面的文案写进桌面端的语言文件。第一版只开放免费分享作品和模板：付费上架等公司主体和审核体系就绪后再开；含可执行代码的能力包等沙箱策略启动后再开。网站只保留分享落地页和结账页，文案在本节末尾。

### 列表（应用内）

| 键 | 中文 | English |
| --- | --- | --- |
| community.title | 社区 | Community |
| community.lead | 别人分享的模板和作品，都可以拿来用、改成自己的。 | Templates and projects people have shared, ready to use and make your own. |
| community.search | 搜索模板和作品 | Search templates and projects |
| community.filter.all | 全部 | All |
| community.filter.template | 模板 | Templates |
| community.filter.project | 作品 | Projects |
| community.filter.official | 官方 | Official |
| community.sort.popular | 最受欢迎 | Most popular |
| community.sort.new | 最新 | Newest |
| community.sort.remixed | 最多 Remix | Most remixed |
| community.card.by | 作者 {name} | by {name} |
| community.card.installs | {n} 次使用 | {n} uses |
| community.card.remixes | {n} 次 Remix | {n} remixes |
| community.badge.official | 官方 | Official |
| community.empty.title | 没有找到结果 | No results |
| community.empty.body | 换个关键词，或清除筛选条件。 | Try different words, or clear the filters. |
| community.empty.clear | 清除筛选 | Clear filters |
| community.offline | 社区需要联网。连上网络后会自动加载。 | Community needs an internet connection. It loads automatically when you're back online. |
| community.error | 社区暂时无法加载，请稍后重试。 | Community couldn't load. Try again in a moment. |
| community.share\_cta | 分享你的作品 | Share your work |

以后再加：组件、能力包、适用硬件、免费/付费筛选，以及「已验证创作者」徽章。

「{n} 次安装」改为「{n} 次使用」：普通用户不说“安装模板”。数字要走复数规则（英文 1 use / 2 uses），见本地化规范。

### 详情（应用内）

| 键 | 中文 | English |
| --- | --- | --- |
| item.remix | Remix | Remix |
| item.remix.help | 复制一份到你的 Workspace，随便改。原作不受影响。 | Make your own copy in your workspace. The original stays as it is. |
| item.use\_template | 用这个模板新建项目 | New project from this template |
| item.view\_live | 查看在线演示 | View live demo |
| item.tab.overview | 介绍 | Overview |
| item.tab.versions | 版本 | Versions |
| item.tab.remixes | Remix 作品 | Remixes |
| item.meta.updated | 更新于 {date} | Updated {date} |
| item.meta.version | 版本 {version} | Version {version} |
| item.meta.requires | 需要 Zintriq {version} 或更新版本 | Requires Zintriq {version} or later |
| item.meta.license | 许可：{license} | License: {license} |
| item.meta.remix\_of | Remix 自 {title}（作者 {name}） | Remixed from {title} by {name} |
| item.report | 举报 | Report |
| item.share | 复制分享链接 | Copy share link |
| item.copied | 链接已复制 | Link copied |

已删除的键：网页专用的 `item.open_in_app`、`item.no_app.*`、`item.login_required`；付费用的 `item.buy`、`item.owned`；能力包用的 `item.install`、`item.permissions.*`、`item.meta.hardware`。后三类等付费上架和沙箱策略启动时再加回。

### 分享作品（应用内）

| 键 | 中文 | English |
| --- | --- | --- |
| share.title | 分享到社区 | Share to Community |
| share.type | 以什么形式分享？ | Share it as |
| share.type.template | 模板：别人以此为起点做自己的作品 | Template: others start their own project from it |
| share.type.project | 作品：展示你做的东西，可选允许 Remix | Project: show what you made, with remixing optional |
| share.name | 名称 | Name |
| share.summary | 一句话介绍 | One-line summary |
| share.description | 详细介绍 | Description |
| share.cover | 封面图 | Cover image |
| share.allow\_remix | 允许别人 Remix | Allow remixing |
| share.license | 许可协议 | License |
| share.free\_note | 社区作品目前都是免费分享的。 | Everything on Community is free to share for now. |
| share.check.title | 分享前检查 | Before you share |
| share.check.secrets | 已自动移除 {n} 项密钥和连接凭证，别人拿到的副本里不包含。 | We removed {n} keys and connection credentials. Copies others get won't include them. |
| share.check.data | 样例数据会一起分享，真实数据不会。 | Sample data is shared. Real data is not. |
| share.check.links | 发现 {n} 个可疑链接，请删除后再提交。 | We found {n} suspicious links. Remove them before submitting. |
| share.submit | 提交 | Submit |
| share.status.review | 审核中，通常在 1–3 个工作日内上架。 | In review. Usually live within 1–3 business days. |
| share.status.live | 已上架 | Live |
| share.status.changes | 需要修改：{reason} | Changes needed: {reason} |
| share.status.hidden | 已下架。已经用了的人不受影响。 | Unlisted. People who already use it aren't affected. |
| share.update | 发布新版本 | Publish new version |
| share.update.note | 使用旧版本的人会收到更新提示，由他们决定是否升级。 | People on older versions get an update notice and choose whether to upgrade. |

审核流程：自动扫描密钥和恶意链接 + 举报下架 + 人工抽查。密钥在分享时自动移除，是必须实现的功能，不只是文案。付费上架开放时加回价格字段，分成文案写成：“按扣除税和支付手续费后的净额计算：累计 {threshold} 以内 Zintriq 不抽成，超过后抽成 15%。”

### 创作者主页（应用内）

| 键 | 中文 | English |
| --- | --- | --- |
| profile.works | 作品 | Work |
| profile.joined | {date} 加入 | Joined {date} |
| profile.empty | 还没有公开的作品。 | No public work yet. |
| profile.empty.self | 你还没有分享作品。 | You haven't shared anything yet. |
| profile.empty.self\_cta | 分享一个项目 | Share a project |

社区里分享的作品始终保留作者署名和链接（`item.meta.remix_of` 等），不受付费状态影响。

### 网站：分享落地页 `/c/<id>`

只是一张卡片，不能浏览其他作品。页面输出 Open Graph 标签，让链接在聊天软件里显示封面和标题。

| 键 | 中文 | English |
| --- | --- | --- |
| share\_page.by | 作者 {name} · {type} | by {name} · {type} |
| share\_page.open | 在 Zintriq 中打开 | Open in Zintriq |
| share\_page.no\_app | 还没有 Zintriq？下载后登录，再点一次「在 Zintriq 中打开」。 | Don't have Zintriq? Download it, log in, then select “Open in Zintriq” again. |
| share\_page.download | 下载 Zintriq | Download Zintriq |
| share\_page.mobile | 社区作品需要在电脑上的 Zintriq 里打开。把链接发到邮箱，稍后在电脑上看。 | Community projects open in Zintriq on a computer. Email yourself the link to open later. |
| share\_page.live\_demo | 查看在线演示 | View live demo |
| share\_page.unavailable | 这个作品已不在社区里。 | This project is no longer on Community. |
| share\_page.report | 举报 | Report |

`share_page.live_demo` 只在作者把作品同时发布为线上作品时显示，链接到托管页。已定允许搜索引擎收录：已上架的作品进 sitemap；审核中、已下架的返回 noindex。

### 网站：结账页 `/checkout`

公司注册、Stripe 产品价目就绪后上线。须已登录现有账号。应用里点「订阅」或「升级」后在浏览器打开这里，由 Flask 创建 Stripe Checkout Session，付款后 webhook 写回该账号，然后回到应用。`checkout.title.item` 等社区付费上架开放后再启用。

| 键 | 中文 | English |
| --- | --- | --- |
| checkout.title.item | 购买「{name}」 | Buy “{name}” |
| checkout.title.plan | 升级到 {plan} | Upgrade to {plan} |
| checkout.secure | 付款由 Stripe 安全处理。 | Payment securely processed by Stripe. |
| checkout.done | 付款完成。回到 Zintriq 即可使用，这个页面可以关闭。 | Payment complete. Head back to Zintriq to use it. You can close this tab. |
| checkout.done.open | 打开 Zintriq | Open Zintriq |
| checkout.cancel | 已取消，没有扣款。 | Cancelled. You haven't been charged. |
| checkout.failed | 付款没有成功，没有扣款。请重试或换一种付款方式。 | Payment didn't go through and you haven't been charged. Try again or use another payment method. |
| checkout.pending | 付款正在确认，完成后应用会自动更新。 | Confirming your payment. The app updates automatically when it's done. |

## 已发布作品的托管页

作品页属于创作者，不属于 Zintriq：除了一个小角标和系统状态页，不加任何 Zintriq 导航。作品自己的文案跟随创作者设置的语言；下面这些系统文案跟随访客浏览器语言。

### 角标

| 键 | 中文 | English |
| --- | --- | --- |
| hosted.badge | 用 Zintriq 制作 | Made with Zintriq |
| hosted.badge.remix | Remix 这个作品 | Remix this |
| hosted.badge.report | 举报 | Report |
| hosted.badge.hide | 收起 | Hide |

角标规则：试用期内强制显示，付费用户可以在发布设置里关闭。「举报」必须始终可达，角标关闭时放在页脚一个小链接里。停止付费后，已发布作品有 30 天宽限期，之后显示 `hosted.unpublished`。

### 系统状态页

| 键 | 中文 | English |
| --- | --- | --- |
| hosted.404.title | 找不到这个作品 | This page doesn't exist |
| hosted.404.body | 链接可能有误，或者作者已经把它下线了。 | The link may be wrong, or the creator took it down. |
| hosted.unpublished.title | 这个作品暂时不可访问 | This project isn't available right now |
| hosted.unpublished.body | 作者暂停了发布。 | The creator has paused it. |
| hosted.private.title | 需要登录才能查看 | Log in to view this |
| hosted.private.body | 这个作品只对 {workspace} 的成员开放。 | This project is only for members of {workspace}. |
| hosted.password.title | 输入密码 | Enter password |
| hosted.password.wrong | 密码不对，请再试一次。 | That password didn't work. Try again. |
| hosted.suspended.title | 这个作品已被下架 | This project has been taken down |
| hosted.suspended.body | 它违反了 Zintriq 的使用政策。如果你是作者，请查看邮件了解原因和申诉方式。 | It broke Zintriq's usage policy. If you made it, check your email for the reason and how to appeal. |
| hosted.error.title | 加载出错了 | Something went wrong |
| hosted.error.body | 请稍后刷新。问题持续的话，可以在服务状态页查看。 | Refresh in a moment. If it keeps happening, check our status page. |
| hosted.offline | 你现在处于离线状态，显示的是上次加载的内容。 | You're offline. Showing what was last loaded. |
| hosted.install\_pwa | 添加到主屏幕 | Add to home screen |

### 举报表单

| 键 | 中文 | English |
| --- | --- | --- |
| report.title | 举报这个作品 | Report this project |
| report.reason | 原因 | Reason |
| report.reason.scam | 诈骗或钓鱼 | Scam or phishing |
| report.reason.ip | 侵犯版权或商标 | Copyright or trademark |
| report.reason.illegal | 违法内容 | Illegal content |
| report.reason.harm | 仇恨、骚扰或危险内容 | Hate, harassment or dangerous content |
| report.reason.other | 其他 | Something else |
| report.details | 补充说明（选填） | Details (optional) |
| report.email | 你的邮箱（选填，用于告知处理结果） | Your email (optional, so we can follow up) |
| report.submit | 提交举报 | Submit report |
| report.done | 已收到，谢谢。我们会尽快处理。 | Thanks. We've got it and will look into it. |

托管他人作品后，钓鱼和侵权举报是法律义务（欧盟 DSA 要求有通知与处理机制），所以举报入口不是可选项。

## 硬件 `/hardware`

现阶段是介绍页加候补名单，不写价格和日期。开售后，只需把「加入候补名单」换成「购买」并启用下方的销售文案。具体模块列表用占位，等你定下第一批。

### 介绍（现在上线）

| 键 | 中文 | English |
| --- | --- | --- |
| hw.badge | 即将推出 | Coming soon |
| hw.title | 进入物理世界 | Into the physical world |
| hw.lead | Zintriq 硬件模块是元空间里的一种目标。在应用里建造，再写入设备——感知、显示、动作，不必手写固件。 | Zintriq hardware modules are one target in the meta-space. Build in the app, then flash to the device — sense, display, act — without hand-writing firmware. |
| hw.cta | 加入候补名单 | Join the waitlist |
| hw.cta.note | 开售时第一时间通知你。不会发其他邮件。 | We'll email you when they're available. Nothing else. |
| hw.how.title | 怎么接到元系统里 | How it joins the meta-system |
| hw.how.1 | 用 USB 接到电脑，模块出现在应用里，成为设备对象。 | Plug it in over USB. The module appears in the app as a device object. |
| hw.how.2 | 把读数、按钮与继电器接上，先在本机跑通。 | Wire readings, buttons, and relays. Run it on your machine first. |
| hw.how.3 | 一键写入模块。断开电脑后照样工作，也可通过 Wi-Fi 继续更新。 | Flash the module in one click. It keeps running on its own, and you can update it over Wi-Fi. |
| hw.for.title | 适合谁 | Who it's for |
| hw.for.merchants | **搭建者**：把设备接到你已经在空间里建造的东西上——叫号、温控、签到。 | **Builders**: attach devices to what you already made in the space — queues, climate alerts, check-in. |
| hw.for.makers | **创客与研究者**：家庭自动化、实验装置、桌面原型——从元空间到实物，不必先学固件。 | **Makers and researchers**: home automation, lab rigs, desk prototypes — from the meta-space to physical without learning firmware first. |
| hw.modules.title | 第一批模块 | The first modules |
| hw.modules.item | {name}：{one\_line} | {name}: {one\_line} |
| hw.open.title | 也支持常见开发板 | Works with common boards too |
| hw.open.body | Zintriq 基于成熟的 ESPHome 生态。常见的 ESP32 开发板也能用；Zintriq 模块只是省去了接线和配置。 | Zintriq builds on the proven ESPHome ecosystem. Common ESP32 boards work too — Zintriq modules just skip the wiring and setup. |
| hw.works\_with | 元系统 | Meta-system |

第一批三个模块（`hw.modules.item` 的内容），都基于 ESP32 + ESPHome：

| 键 | 中文 | English |
| --- | --- | --- |
| hw.mod.climate | **温湿度模块**：监测房间、冷柜、温室，超出范围就提醒你。 | **Climate module**: watch a room, a fridge or a greenhouse, and get alerted when it's out of range. |
| hw.mod.relay | **继电器模块**：用界面按钮或定时规则开关灯、风扇、水泵等用电器。 | **Relay module**: switch lights, fans or pumps from a button in your interface or on a schedule. |
| hw.mod.presence | **人体存在模块**：知道有没有人在，用来自动开灯、统计客流或无人时节电。 | **Presence module**: know when someone's there — turn on lights, count visitors or save power when a space is empty. |

`hw.open`（支持第三方 ESP32 开发板）和 `hw.how.3`（Wi-Fi 更新）已确认保留。Wi-Fi 更新必须签名，可以在安全页加一句：“设备只接受经过签名的更新。”

### 候补名单表单

| 键 | 中文 | English |
| --- | --- | --- |
| hw.wait.email | 邮箱 | Email |
| hw.wait.use | 你打算用来做什么？（选填） | What would you make? (optional) |
| hw.wait.region | 收货国家或地区 | Shipping country or region |
| hw.wait.submit | 加入 | Join |
| hw.wait.done | 已加入。开售时会发邮件到 {email}。 | You're on the list. We'll email {email} when they're available. |
| hw.wait.already | 这个邮箱已经在名单里了。 | That email is already on the list. |

收货地区是为了规划第一批发货地区和认证（CE、FCC、CCC 等），值得收集。

### 销售（开售后启用）

| 键 | 中文 | English |
| --- | --- | --- |
| hw.buy | 购买 {price} | Buy for {price} |
| hw.buy.tax | 含税价，结账时按地区计算 | Tax calculated at checkout |
| hw.buy.ships | 可发货到：{regions} | Ships to: {regions} |
| hw.buy.not\_shipping | 暂不发货到 {region}。加入名单，开通时通知你。 | We don't ship to {region} yet. Join the list and we'll tell you when we do. |
| hw.buy.in\_box | 包装内容 | What's in the box |
| hw.buy.specs | 规格 | Specs |
| hw.buy.returns | 退货与保修 | Returns & warranty |
| hw.buy.app\_included | 已包含 Zintriq 软件的硬件功能，无需额外付费。 | Includes Zintriq's hardware features at no extra cost. |

硬件不走官网 Stripe 订阅，在独立店铺销售：「购买」按钮链接到店铺，退货与保修政策按店铺和发货地区另写。`hw.buy.app_included` 删除：硬件不含软件订阅，设备数据存储计入订阅的存储额度。开店前选定实物电商平台，不默认用软件订阅的 Stripe 账户卖货。

## 定价 `/pricing`

定价已定：订阅制，免费下载试用，没有永久免费档；个人约 $10/月、团队约 $20/席位/月、企业与教育联系销售；年付按 10 个月计价；**Stripe** 收款（Flask + 现有账号）；首次付费 14 天内可退。价格是起点假设，上线后用数据调整。公司注册前，定价页展示价格但不提供购买，用 `pricing.not_yet` 代替购买按钮。

### 页头

| 键 | 中文 | English |
| --- | --- | --- |
| pricing.title | 简单的定价 | Simple pricing |
| pricing.lead | 免费下载。本机创作与导出无需订阅。付费解锁发布与同步——分享链接与云同步。不是通用主机套餐。 | Download free. Make and export on your computer with no subscription. Pay for Publish & sync — share links and cloud sync. Not a generic hosting plan. |
| pricing.monthly | 按月 | Monthly |
| pricing.yearly | 按年 | Yearly |
| pricing.yearly\_save | 按年付，只付 10 个月 | Pay yearly, get 2 months free |
| pricing.per\_month | / 月 | / month |
| pricing.per\_seat | 每位成员 / 月 | per member / month |
| pricing.tax\_note | 价格以 {currency} 显示。税费在结账时按你所在地区计算。 | Prices in {currency}. Tax is calculated at checkout based on where you are. |
| pricing.not\_yet | 订阅即将开放。应用就绪后再下载。 | Plans are coming soon. Download when the app is ready. |

### 档位

| 键 | 中文 | English |
| --- | --- | --- |
| plan.trial.name | 免费试用 | Free trial |
| plan.trial.for | 试用上线后：下载即可开始，试用 {trial\_days} 天全部功能。到期后项目仍然可以查看和导出。 | When trials ship: download and try everything for {trial\_days} days. After that you can still view and export your projects. |
| plan.trial.cta | 免费下载 | Download free |
| plan.personal.name | 个人 | Personal |
| plan.personal.for | 适合独立创作者和小店主 | For solo creators and small shops |
| plan.personal.price | {price} / 月 | {price} / month |
| plan.team.name | 团队 | Team |
| plan.team.for | 适合一起做项目的团队 | For teams building together |
| plan.team.price | {price} / 席位 / 月 | {price} per seat / month |
| plan.enterprise.name | 企业与教育 | Enterprise & Education |
| plan.enterprise.for | 适合学校和需要统一管理、离线激活的组织 | For schools and organizations that need central management or offline activation |
| plan.enterprise.cta | 联系我们 | Contact us |
| plan.subscribe | 订阅 {plan} | Subscribe to {plan} |
| plan.recommended | 最受欢迎 | Most popular |
| plan.current | 当前方案 | Current plan |

各档差异只在席位、协作、存储额度和支持上：

| 差异项 | 个人 | 团队 | 企业与教育 |
| --- | --- | --- | --- |
| 创作功能 | 全部 | 全部 | 全部 |
| 席位 | 1 | 按席位 | 按合同 |
| Workspace 协作、角色与邀请 | — | 有 | 有，另加统一管理 |
| 云存储额度 | {quota\_personal} | 每席位 {quota\_seat} | 按合同 |
| 支持 | 邮件 | 优先邮件 | 专人联系 |

「去掉角标」不作为档位差异：任何付费档都能关闭。

`{trial_days}`、`{quota_personal}`、`{quota_seat}` 还没定，见文末。

### 所有方案都包含

| 键 | 中文 | English |
| --- | --- | --- |
| pricing.all.title | 所有方案都包含 | Every plan includes |
| pricing.all.platforms | Windows、macOS、Linux 应用 | The app for Windows, macOS and Linux |
| pricing.all.blocks | 元空间里没有功能锁 | Nothing locked in the meta-space |
| pricing.all.community | 浏览、Remix 和分享社区作品 | Browse, remix and share on Community |
| pricing.all.offline | 离线使用 | Offline use |
| pricing.all.export | 随时导出全部数据 | Export all your data any time |
| pricing.all.versions | 发布版本和一键退回 | Release history and one-click rollback |
| pricing.all.privacy | 无广告、无第三方追踪 | No ads, no third-party tracking |

### 社区付费上架（暂不显示）

| 键 | 中文 | English |
| --- | --- | --- |
| pricing.creators.title | 在社区出售作品 | Sell on Community |
| pricing.creators.body | 分成按扣除税费和支付手续费后的净额计算：累计净收入 {threshold} 以内全部归你，超过后 Zintriq 收取 15%。 | Revenue share is based on net sales after tax and payment fees. Keep 100% of your first {threshold}; after that, Zintriq keeps 15%. |
| pricing.creators.cta | 创作者条款 | Creator terms |

公司主体和审核体系就绪、付费上架开放后再加到定价页；在此之前定价页不提分成。

### 常见问题

| 问（中文） | 答（中文） | Q (English) | A (English) |
| --- | --- | --- | --- |
| 可以先试用吗？ | 下载免费。试用上线后，有 {trial\_days} 天全部功能。到期后项目仍可以查看和导出，订阅后继续编辑。 | Can I try it first? | Downloading is free. When trials ship, you get every feature for {trial\_days} days. After that you can still view and export your projects, and subscribing lets you keep editing. |
| 云同步和存储要另外付费吗？ | 云同步和存储上线后包含在订阅里，不另收费。每个方案会有各自的存储额度。 | Do I pay extra for cloud sync and storage? | No extra fee when cloud sync and storage ship. Each plan will have its own storage allowance. |
| 没有网络还能用吗？ | 即将推出。上线后没网也能继续做。能离线多久会在上线时写清。 | Can I use it offline? | Coming later. You will be able to keep working without a network. We will publish how long a device can stay offline when that ships. |
| 停止付费后我的作品怎么办？ | 付费和托管上线后：账号进入只读与导出。已发布作品再保持在线 30 天；云端数据保留 90 天，期间重新订阅即可全部恢复。 | What happens to my work if I stop paying? | When paid plans and hosting exist: the account becomes view-and-export only. Published work stays online for 30 more days, and cloud data is kept for 90 days — subscribe again in that time to get everything back. |
| 谁向我收款？ | 订阅由 Zintriq 出售，付款由 Stripe 处理。账单上通常显示 Zintriq；税费在结账时按地区计算。 | Who charges me? | Zintriq sells the subscription. Payments are processed by Stripe. Your statement typically shows Zintriq. Tax is calculated at checkout. |
| 可以退款吗？ | 首次付费后 14 天内可以申请全额退款。 | Can I get a refund? | Yes. You can get a full refund within 14 days of your first payment. |
| 可以随时升级、降级或取消吗？ | 可以，在账户页里操作。 | Can I change or cancel my plan? | Yes, any time from your account page. |
| 有教育或非营利优惠吗？ | 企业与教育方案请联系我们。 | Education or nonprofit discounts? | Contact us about Enterprise & Education. |

## 账号与桌面登录授权

桌面端登录会经过四个网页状态：登录页（带桌面端提示）→ 授权确认 → 成功或失败。授权确认页是防钓鱼的关键，必须让用户看清是哪台设备在请求。

### 登录 / 注册页的桌面端提示

| 键 | 中文 | English |
| --- | --- | --- |
| auth.from\_app | 登录后会自动回到 Zintriq 桌面端。 | After you log in, you'll go back to the Zintriq app. |
| auth.login.title | 登录 Zintriq | Log in to Zintriq |
| auth.signup.title | 创建 Zintriq 账号 | Create your Zintriq account |
| auth.signup.lead | 这个账号用于本网站。桌面端登录和社区以后会用同一个账号。 | One account for this website. The app and Community will use it later. |
| auth.email | 邮箱 | Email |
| auth.password | 密码 | Password |
| auth.magic | 用邮件链接登录 | Email me a login link |
| auth.magic.sent | 登录链接已发到 {email}，15 分钟内有效。 | We sent a login link to {email}. It works for 15 minutes. |
| auth.magic.same\_device | 请在这台电脑上打开邮件里的链接，这样才能回到桌面端。 | Open the link on this computer so we can send you back to the app. |
| auth.forgot | 忘记密码 | Forgot password |
| auth.no\_account | 还没有账号？注册 | No account? Sign up |
| auth.has\_account | 已有账号？登录 | Have an account? Log in |
| auth.error.credentials | 邮箱或密码不对。 | Email or password is incorrect. |
| auth.error.rate | 尝试次数太多，请 {minutes} 分钟后再试。 | Too many tries. Try again in {minutes} minutes. |
| auth.magic.other\_device | 你在另一台设备上打开了这个链接。已在这里登录网站；要登录桌面端，请在电脑上的 Zintriq 里重新点「登录」。 | You opened this link on a different device. You're logged in to the website here. To log in to the app, select Log in again in Zintriq on your computer. |

`auth.magic.other_device` 处理的是 Magic Link 在手机上打开的情况：回环地址只在发起登录的那台电脑上有效。

### 授权确认 `/desktop/authorize`

| 键 | 中文 | English |
| --- | --- | --- |
| desk.auth.kicker | 这台电脑 | This computer |
| desk.auth.title | 要连接 Zintriq 吗？ | Connect Zintriq? |
| desk.auth.lead | 将以 {email} 继续。 | Continue as {email}. |
| desk.auth.account | 账号：{email} | Account: {email} |
| desk.auth.account\_label | 账号 | Account |
| desk.auth.switch | 换一个账号 | Use a different account |
| desk.auth.device | 设备：{device\_name} · {os} · Zintriq {version} | Device: {device\_name} · {os} · Zintriq {version} |
| desk.auth.device\_label | 电脑 | Computer |
| desk.auth.device\_meta | {os} · Zintriq {version} | {os} · Zintriq {version} |
| desk.auth.access.title | 连接后可以 | This lets Zintriq |
| desk.auth.access.projects | 在这台电脑上同步你的项目 | Sync your projects on this computer |
| desk.auth.access.publish | 以你的名义发布到社区 | Publish to Community as you |
| desk.auth.access.workspaces | 在这台设备保持登录 | Stay signed in on this device |
| desk.auth.warning | 只有你刚刚在应用里点了「登录」时才允许。 | Allow only if you just chose Log in in the app. |
| desk.auth.allow | 允许 | Allow |
| desk.auth.deny | 不允许 | Don't allow |

### 结果页

| 键 | 中文 | English |
| --- | --- | --- |
| desk.ok.title | 已登录 | You're logged in |
| desk.ok.body | 可以回到 Zintriq 了。这个页面可以关闭。 | Head back to Zintriq. You can close this tab. |
| desk.ok.open | 打开 Zintriq | Open Zintriq |
| desk.denied.title | 已拒绝 | Request denied |
| desk.denied.body | 没有设备登录你的账号。如果不是你发起的，建议修改密码。 | No device was logged in. If you didn't start this, consider changing your password. |
| desk.err.expired.title | 登录请求已过期 | This login request has expired |
| desk.err.expired.body | 请回到 Zintriq，重新点「登录」。 | Go back to Zintriq and select Log in again. |
| desk.err.callback.title | 没能连上 Zintriq 桌面端 | We couldn't reach the Zintriq app |
| desk.err.callback.body | 请确认 Zintriq 还开着，然后在应用里重新点「登录」。如果安装了防火墙或安全软件，它们可能拦截了本机连接。 | Make sure Zintriq is still open, then select Log in again in the app. A firewall or security app may be blocking local connections. |
| desk.err.invalid.title | 这个登录请求无效 | This login request isn't valid |
| desk.err.invalid.body | 请只从 Zintriq 应用里发起登录。 | Only start logging in from inside the Zintriq app. |
| desk.err.help | 仍然不行？查看登录问题帮助 | Still stuck? Get help logging in |

`desk.err.invalid` 用于 state 不匹配、client\_id 或回调地址不合法等情况，不要在页面上暴露具体原因。

### 账户页：已登录设备

| 键 | 中文 | English |
| --- | --- | --- |
| account.devices.title | 已登录的设备 | Logged-in devices |
| account.devices.last | 上次活动：{time} | Last active {time} |
| account.devices.this | 当前设备 | This device |
| account.devices.signout | 退出这台设备 | Log out of this device |
| account.devices.signout.confirm | 这台设备下次联网时会退出。本地未同步的修改会保留在那台电脑上，重新登录后继续同步。 | That device will be logged out next time it goes online. Unsynced changes stay on that computer and sync after logging in again. |
| account.devices.offline\_note | 离线设备最长 30 天后需要重新联网验证。 | Offline devices need to reconnect at least every 30 days. |

`account.devices.signout.confirm` 中“未同步修改保留”是一个产品承诺，需要实现时保证；远程退出时不应删除本地数据。

## 产品页与其他页面

### 产品 `/product`（同一套空间）

| 键 | 中文 | English |
| --- | --- | --- |
| product.title | 科技系统的元空间。 | The meta-space for technology systems. |
| product.lead | Zintriq 是科技系统的元空间。软件、硬件和其他目标也在这个空间里。没有产品边界。边界也可以被建造。 | Zintriq is the meta-space for technology systems. Software, hardware, and other targets live in that space. No product walls. Boundaries can be built. |
| product.open.title | 同一套空间。 | One space. |
| product.open.body | 咖啡馆、传感器、网站、模型——不是产品线。它们同在一套元空间里。 | A café, a sensor, a site, a model — they are not product lines. They live in the same meta-space. |
| product.space.title | 没有类别墙 | No category wall |
| product.desktop.title | 工厂在你的电脑上 | The factory is on your computer |
| product.bounds.title | 边界也可以被建造 | Boundaries can be built |
| product.examples.title | 同一套元空间里的系统 | Systems in the same meta-space |
| product.cta | 下载 Zintriq | Download Zintriq |

示例是空间里的实例，不是产品线：

| 你做的 | 说明 | 状态 |
| --- | --- | --- |
| 咖啡馆 / A café | 菜单、订单、现场 | 现在可用（阶段 1 可保存与导出，阶段 2 可发布） |
| 预约台 / A booking desk | 时段、客人、提醒 | 即将推出 |
| 柜台 / A shop counter | 商品、支付、取餐 | 即将推出 |
| 传感器 / A sensor | 读数与告警 | 即将推出 |
| 持续运转的装置 / A device that keeps running | 泵、阀、循环 | 即将推出 |
| 模型 / A model in the space | 推理与接口 | 即将推出 |

产品页上的社区区块（阶段 2 起显示）：

| 键 | 中文 | English |
| --- | --- | --- |
| product.community.title | Zintriq 社区，就在应用里 | Zintriq Community, right in the app |
| product.community.lead | 在 Zintriq 里浏览别人分享的模板和作品，一键 Remix 成自己的版本。不用离开应用，也不用下载文件再导入。 | Browse templates and projects others have shared, right inside Zintriq, and remix them in one click — no downloading and importing files. |
| product.community.share | 做出好东西？免费分享到社区。 | Made something good? Share it on Community for free. |
| product.community.cta | 下载 Zintriq | Download Zintriq |

### 文档入口 `/docs`

| 分组 | 中文 | English |
| --- | --- | --- |
| docs.start | 开始：安装、登录、第一个项目 | Get started: install, log in, first project |
| docs.build | 创作：在电脑上做 | Create on your computer |
| docs.meta | 元系统：概念与边界 | Meta-system: concepts and boundaries |
| docs.publish | 发布：域名、版本、退回 | Publish: domains, versions, rollback |
| docs.community | 社区：Remix 与分享 | Community: remix and share |
| docs.workspace | 团队：Workspace、成员和权限 | Teams: workspaces, members, permissions |
| docs.hardware | 硬件（即将推出） | Hardware (coming soon) |
| docs.dev | 开发者：自定义组件、操作和连接 | Developers: custom components, actions and connections |
| docs.search | 搜索文档 | Search docs |

### 开发者 `/extend`

| 键 | 中文 | English |
| --- | --- | --- |
| extend.title | 需要更多？写一点代码 | Need more? Write a little code |
| extend.lead | 代码在 Zintriq 里是可选的。内置描述不够用时，可以写自己的组件、操作和连接，再分享到社区。 | Code is optional in Zintriq. When built-in description isn’t enough, write your own components, actions and connections — then share them on Community. |
| extend.1 | 自定义组件 | Custom components |
| extend.2 | 自定义操作 | Custom actions |
| extend.3 | 新的连接 | New connections |
| extend.4 | 版本、权限声明与审核 | Versions, permission declarations and review |
| extend.cta | 阅读开发者文档 | Read the developer docs |

### 安全与隐私 `/security`

保留旧版前五条（改写为下面的语气），删掉“正在移除 Google 服务”，新增桌面端相关三条。

| 键 | 中文 | English |
| --- | --- | --- |
| sec.title | 安全与隐私 | Security & privacy |
| sec.workspace | **Workspace 隔离**：每个 Workspace 的数据、成员和权限分开管理。 | **Separate workspaces**: data, members and permissions are kept apart per workspace. |
| sec.drafts | **草稿不外泄**：公开链接只显示已发布的版本。 | **Drafts stay private**: public links only show published versions. |
| sec.ids | **改动不会弄乱引用**：每个元素有固定编号，修改外观不会破坏绑定和逻辑。 | **Edits don't break links**: every element keeps a permanent ID, so restyling never breaks bindings or logic. |
| sec.tracking | **不追踪**：没有广告像素和第三方追踪，只使用不写 Cookie 的第一方统计。 | **No tracking**: no ad pixels or third-party trackers — only cookieless first-party analytics. |
| sec.residency | **数据存放**：运营于中国上海，数据存储于德国法兰克福（欧盟）。 | **Data location**: operated from Shanghai, China; stored in Frankfurt, Germany (EU). |
| sec.signin | **桌面端登录**：在系统浏览器里完成，应用本身不接触你的密码。 | **App sign-in**: happens in your browser, so the app never sees your password. |
| sec.local | **本地优先**：项目先保存在你的电脑上。设为“仅本地”的项目不会上传。 | **Local first**: projects save to your computer first. Local-only projects are never uploaded. |
| sec.packages | **社区内容审核**：每次分享都会自动移除密钥并扫描恶意链接；目前不接受含可执行代码的内容。 | **Checked Community content**: keys are stripped and links scanned on every share, and content with executable code isn't accepted yet. |

可以再加一条 `sec.ota`：“**签名更新**：硬件模块只接受经过签名的无线更新。” / “**Signed updates**: hardware modules only accept signed over-the-air updates.”，阶段 4 上线。

### 关于 `/about`

| 键 | 中文 | English |
| --- | --- | --- |
| about.title | 科技系统的元空间。 | The meta-space for technology systems. |
| about.body | Zintriq 是科技系统的元空间。没有产品边界。边界也可以被建造。软件、硬件和其他目标也在这个空间里。可视化是默认入口，代码也欢迎。创作在桌面端完成。 | Zintriq is a meta-space for technology systems. No product walls. Boundaries can be built. Software, hardware, and other targets live there. Visual editing is the default; code is welcome. Making happens in the desktop app. |
| about.ops | 运营于中国上海，数据存储于德国法兰克福（欧盟）。 | Operated from Shanghai, China. Data stored in Frankfurt, Germany (EU). |
| about.cta | 联系我们 | Contact us |

### 联系 `/contact`

| 键 | 中文 | English |
| --- | --- | --- |
| contact.title | 联系我们 | Contact us |
| contact.lead | 合作、团队采购、安全问题都可以写信给我们。使用问题先看文档，通常更快。 | Write to us about partnerships, team purchases or security. For how-to questions, the docs are usually faster. |
| contact.topic | 主题 | Topic |
| contact.topic.options | 一般问题 · 账号与付款 · 合作 · 硬件 · 安全漏洞 · 隐私请求 | General · Account & billing · Partnerships · Hardware · Security issue · Privacy request |
| contact.name / email / message / send | 姓名 · 邮箱 · 留言 · 发送 | Name · Email · Message · Send |
| contact.ok | 已收到，我们会在 {days} 个工作日内回复。 | Got it. We'll reply within {days} business days. |
| contact.err | 请填写姓名、有效邮箱和留言。 | Please add your name, a valid email and a message. |
| contact.billing\_note | 订阅付款由 Stripe 处理。发票和退款请写信给我们。 | Subscription payments are processed by Stripe. Write to us about invoices and refunds. |

### 博客与更新日志

- 博客：删除。有真实内容时再开，第一篇可以是桌面端发布公告。
- 更新日志：从桌面端第一个公开版本开始记录，格式为「版本号 · 日期 · 新增 / 改进 / 修复」。

| 键 | 中文 | English |
| --- | --- | --- |
| changelog.title | 更新日志 | Changelog |
| changelog.lead | Zintriq 桌面端和网站的每次更新。 | Every update to the Zintriq app and website. |
| changelog.new / improved / fixed | 新增 · 改进 · 修复 | New · Improved · Fixed |

### 对比页 `/compare/*`

保留两张对比表。对方一列写成「常见建站工具 / 常见低代码平台」。Zintriq 一列写同一套空间里的实例（咖啡馆、预约台、传感器、模型），不写产品类别，也不写描述 / 模拟 / 实例化。硬件是空间里的一种目标（即将推出）。不点名具体竞品。

## 状态与恢复文案

每条状态都回答两个问题：现在是什么情况、接下来能做什么。这些键 Web 和桌面端共用。

### 发布

| 键 | 中文 | English |
| --- | --- | --- |
| pub.draft | 草稿 · 有未发布的修改 | Draft · Unpublished changes |
| pub.live | 已发布 · 版本 {n} · {time} | Live · Version {n} · {time} |
| pub.publishing | 正在发布… | Publishing… |
| pub.done | 已发布版本 {n}。 | Version {n} is live. |
| pub.done.view | 查看 | View |
| pub.done.copy | 复制链接 | Copy link |
| pub.failed | 发布失败，线上仍是版本 {n}。你的修改已保留在草稿里。 | Publishing failed. Version {n} is still live, and your changes are saved in your draft. |
| pub.retry | 重试 | Try again |
| pub.rollback | 退回到这个版本 | Roll back to this version |
| pub.rollback.confirm | 线上将立即改为版本 {n}。你的草稿不受影响，之后也可以再改回来。 | Version {n} goes live right away. Your draft isn't affected, and you can switch back later. |
| pub.rollback.done | 已退回到版本 {n}。撤销 | Rolled back to version {n}. Undo |
| pub.unpublish | 停止发布 | Unpublish |
| pub.unpublish.confirm | 链接将无法访问，直到你再次发布。所有版本都会保留。 | The link stops working until you publish again. All versions are kept. |

### 保存与同步

| 键 | 中文 | English |
| --- | --- | --- |
| sync.saved | 已保存 | Saved |
| sync.saving | 正在保存… | Saving… |
| sync.synced | 已同步 | Synced |
| sync.pending | 已保存在本机，联网后同步 | Saved on this computer. Syncs when you're online |
| sync.local\_only | 仅保存在本机 | Only on this computer |
| sync.offline\_days | 离线中。还可以离线使用 {n} 天。 | Offline. You can keep working offline for {n} more days. |
| sync.offline\_expired | 已离线超过 30 天，请联网验证账号。你的项目都在，可以查看和导出。 | You've been offline for over 30 days. Connect to verify your account. Your projects are safe, and you can still view and export them. |
| sync.conflict | 这个项目在另一台设备上也改过。两个版本都已保留，请选择保留哪个。 | This project was also changed on another device. Both versions are kept — choose which to keep. |
| sync.conflict.mine | 保留这台电脑上的 | Keep this computer's |
| sync.conflict.theirs | 保留 {device} 上的 | Keep the one from {device} |
| sync.conflict.both | 两个都保留为独立项目 | Keep both as separate projects |
| sync.quota | 云空间已用 {used} / {total}。 | {used} of {total} cloud storage used. |
| sync.quota\_full | 云空间已满。新的修改会保存在本机，清理或升级后继续同步。 | Cloud storage is full. New changes save on this computer and sync once you free up space or upgrade. |

“离线超过 30 天锁编辑、不锁查看和导出”已确认，和试用到期、停止付费后的只读模式是同一套行为。

### 删除与恢复

| 键 | 中文 | English |
| --- | --- | --- |
| del.project.confirm | 删除「{name}」？它会在回收站保留 {days} 天，已发布的链接会立即停用。 | Delete “{name}”? It stays in Trash for {days} days. Its published link stops working now. |
| del.project.done | 已移到回收站。撤销 | Moved to Trash. Undo |
| del.restore | 恢复 | Restore |
| del.forever | 永久删除 | Delete forever |
| del.forever.confirm | 永久删除后无法恢复。输入项目名称确认。 | This can't be undone. Type the project name to confirm. |
| del.account.confirm | 账号和所有云端数据将在 30 天后删除。在此之前登录即可取消。本机的项目文件不会被删除。 | Your account and all cloud data will be deleted in 30 days. Log in before then to cancel. Project files on your computer won't be deleted. |

### 试用与订阅状态

| 键 | 中文 | English |
| --- | --- | --- |
| bill.trial\_left | 试用还剩 {n} 天。订阅 | {n} days left in your trial. Subscribe |
| bill.trial\_ended | 试用已结束。你的项目都在，可以查看和导出；订阅后继续编辑。 | Your trial has ended. Your projects are safe and you can view and export them. Subscribe to keep editing. |
| bill.lapsed | 订阅已到期。项目可以查看和导出；已发布的作品将在 {date} 下线。 | Your subscription has ended. You can view and export projects. Published work goes offline on {date}. |
| bill.lapsed\_offline | 已发布的作品已下线。云端数据保留到 {date}，在此之前重新订阅即可全部恢复。 | Your published work is offline. Cloud data is kept until {date} — subscribe again before then to get everything back. |
| bill.payment\_failed | 扣款没有成功。请在 {date} 前更新付款方式，以免影响使用。 | We couldn't take your payment. Update your payment method by {date} to avoid interruption. |
| bill.renewed | 订阅已恢复，可以继续编辑了。 | Your subscription is back. You can keep editing. |
| bill.refund\_window | 首次付费 14 天内可申请全额退款。 | Full refund available within 14 days of your first payment. |

### 错误页

| 键 | 中文 | English |
| --- | --- | --- |
| err.403.title | 没有权限 | You don't have access |
| err.403.body | 这个页面或 Workspace 需要其他权限。请联系 Workspace 的管理员。 | This page or workspace needs other permissions. Ask a workspace admin. |
| err.403.cta | 回到我的账户 | Go to my account |
| err.404.title | 页面不存在 | Page not found |
| err.404.body | 它可能已经移动或删除。 | It may have moved or been deleted. |
| err.404.cta | 回到首页 | Go home |
| err.500.title | 出错了 | Something went wrong |
| err.500.body | 是我们这边的问题，请稍后刷新。 | That's on us. Refresh in a moment. |
| err.500.status | 查看服务状态 | Check service status |
| err.maintenance | 我们正在维护，预计 {time} 恢复。保存在你电脑上的项目仍在那台电脑上。 | We're doing maintenance until about {time}. Projects saved on your computer stay there. |

403 的「返回 Studio」改为「回到我的账户」，因为网页 Studio 已不是主入口。

## 法律页需改动清单

现有服务条款是为旧的“二维码 + 捐赠/小费 + 评价聚合”产品写的，和现在卖软件、托管作品、社区、卖硬件基本不对应，需要重写而不是修补。下面是必须改的点，不是法律文本。我不是律师，开始收费前建议请律师审阅，并对照 Stripe 对卖家的条款与税务义务（Zintriq 是记录商户）。

| 问题 | 现状 | 需要改成 |
| --- | --- | --- |
| 运营主体 | “个人学生项目” | 已定：收费前注册公司；法律页、Stripe 账户、Windows 签名都按公司主体。公司注册前上线的不收费网站也要写清当时的运营方 |
| 服务内容 | 二维码生成、支付聚合、评价聚合 | 桌面软件许可、云同步与存储、作品托管、社区、（以后）硬件 |
| 用户角色 | Owner（收捐赠）/ Customer（捐赠者） | 用户、Workspace 成员与管理员、创作者（在社区分享，以后可出售）、作品访客 |
| 付款 | “不处理任何付款”“捐赠不可退还” | 订阅由 Zintriq 出售、Stripe 处理付款；首次付费 14 天内可退；试用到期与停止付费后的只读模式、作品 30 天后下线、数据保留 90 天 |
| 软件许可 | 无 | 授予使用许可的范围、设备数；不连网工作为计划能力，上线后再写期限；阶段 1 无自动更新 |
| 用户内容所有权 | 仅有“提交数据即授予许可用于存储” | 用户保留作品所有权；Zintriq 只取得托管、同步、在社区展示所需的许可 |
| 社区 | 无 | 创作者条款：先写免费分享的许可、Remix、署名和下架规则；付费上架开放时再加分成（净额计算，门槛内 0%，之后 15%）、结算和税务 |
| 托管与内容治理 | 只针对二维码内容 | 可接受使用政策；举报与处理流程、申诉渠道（欧盟 DSA）；版权投诉流程 |
| 责任上限 | “前 12 个月收到的捐赠总额” | 一般改为“用户前 12 个月支付的费用” |
| 硬件 | 无 | 硬件在独立店铺销售，开售前增加店铺的销售条款：保修、退货、发货、安全使用、认证 |
| 注册方式 | 隐私政策说手机号必填，服务条款说邮箱必填 | 以实际为准统一两页 |
| 第三方 | PayPal、Stripe、Trustpilot、Google 小部件 | 列出实际的处理方：Stripe（订阅付款）、托管商、邮件服务、Cloudflare |
| 隐私政策新增 | 无 | 桌面端收集什么（设备名、系统版本、崩溃报告是否开启）；本地项目与同步数据；作品访客的数据由创作者负责（控制者/处理者关系）；Stripe 作为付款处理方 |
| Cookie 政策 | 提到支付按钮和评价小部件 | 删掉；如果确实只用必要 Cookie 和无 Cookie 统计，可以去掉「点击接受」的横幅 |
| 年龄 | 16 岁（中国 14 岁加监护人同意） | 可保留；付费购买还需符合 MoR 的年龄要求 |

页面层面：法律页保持单语言正式版本（建议英文和中文各有效），其他语言仅作参考译文，并在页首写明“如有出入，以 {语言} 版本为准”。社区翻译不应覆盖法律页。

## 本地化规范

语言分三级上线：中英文由我们写；主流语言先出草稿再请母语者审；其余所有语言（包括藏语、与那国语等）通过社区翻译。任何语言都不在未经母语者审阅时标为“已完成”。

### 语言分级

| 级别 | 语言 | 谁来翻 | 上线条件 |
| --- | --- | --- | --- |
| 1 · 源语言 | 简体中文 `zh-Hans`、英文 `en` | 本文档 | 随网站上线 |
| 2 · 主流语言 | 繁体中文 `zh-Hant`、日语 `ja`、韩语 `ko`、西班牙语 `es`、巴西葡萄牙语 `pt-BR`、法语 `fr`、德语 `de`、意大利语 `it`、俄语 `ru`、阿拉伯语 `ar`、土耳其语 `tr`、印尼语 `id`、越南语 `vi`、泰语 `th`、印地语 `hi` | Claude 出草稿 + 至少 1 位母语者审阅 | 核心页面（首页、下载、定价、登录授权、状态文案）100% 审完 |
| 3 · 社区语言 | 其他所有语言，如藏语 `bo`、维吾尔语 `ug`、蒙古语 `mn`、粤语 `yue`、闽南语 `nan`、与那国语 `yoi`、冲绳语 `ryu`、阿伊努语 `ain`、威尔士语 `cy`、斯瓦希里语 `sw` 等 | 母语者提交 + 另一位母语者审核 | 核心页面覆盖 ≥ 90% 后出现在语言列表；之前可在 `/translate` 预览 |

为什么第 3 级不由我直接翻：这些语言的训练语料很少，有些没有统一书写规范（与那国语使用者约数百人，通常用假名书写，写法因人而异）。机器生成的文字很可能不自然甚至错误，对这些语言的使用者反而是不尊重。由社区翻译，也更符合“人人创造”的定位。

### 回退规则

- 每种语言配置一条回退链，缺失的字符串按链显示。例：`yoi → ja → en`；`ryu → ja → en`；`yue → zh-Hant → zh-Hans → en`；`ug → en`；`pt-PT → pt-BR → en`。
- 藏语、维吾尔语、蒙古语等的回退语言由用户选择（中文或英文），不替用户做假设。
- 页面有回退内容时，在页顶显示一条提示（见下方 `i18n.partial`）。

### 技术要求

- **不拼接句子。** 整句做一个键，变量用 `{name}`；不同语言语序不同。
- **复数和数字用 CLDR。** 服务端用 Babel（Flask-Babel），前端用 `Intl.PluralRules`、`Intl.NumberFormat`、`Intl.DateTimeFormat`。例如阿拉伯语有 6 种复数形式。
- **从右到左。** `ar`、`ug`、`he`、`fa`、`ur` 设置 `<html dir="rtl" lang="…">`；CSS 改用 `margin-inline-start` 等逻辑属性；箭头类图标要镜像。
- **字体。** 用 Noto 系列按需加载：藏文 Noto Serif Tibetan、蒙文竖排需单独评估（传统蒙文是竖写，国内用户和蒙古国用户的文字不同）。
- **留出长度。** 德语、俄语等比英文长 30–40%。按钮和导航不写死宽度，手机上允许换行。
- **图片里不放文字。** 示意图里的文字用 HTML 叠加。
- **翻译备注。** 每个键可加一句上下文说明和截图，例如 `item.remix`：“按钮，动词，意为复制后修改”。
- **法律页不开放社区翻译。** 见上一节。
- **工具。** 不必自建翻译平台：Weblate 可自托管且支持 JSON、复数、审核和贡献者署名。`/translate` 页面可以只是一个介绍和跳转。

### 术语表

| 术语 | 规则 | 中文 | English |
| --- | --- | --- | --- |
| Zintriq | 不翻译，不音译；桌面端就叫 Zintriq，不加 Studio | Zintriq | Zintriq |
| 社区 | 中文界面写“社区”，品牌处写“Zintriq 社区”；英文写 Community；其他语言翻译 | 社区 / Zintriq 社区 | Community / Zintriq Community |
| Remix | 各语言可保留英文，备注释义 | Remix | Remix |
| Workspace | 保留英文（与桌面端一致） | Workspace | Workspace |
| 元空间 | 对外主叙事；没有产品边界，边界也可以被建造。描述 / 模拟 / 实例化只用于引擎与桌面工厂，不写进公开口号 | 科技系统的元空间 | The meta-space for technology systems |
| 模板 / 作品 | 社区第一版的两种类型（组件、能力包以后加） | 模板 · 作品 | Template · Project |
| 发布 / 分享 | 发布 = 让作品上线；分享 = 放到社区 | 发布 · 分享 | Publish · Share |
| 退回 | 不用“回滚”（技术词） | 退回 | Roll back |
| 只读与导出模式 | 试用到期、停止付费、离线超 30 天用同一个说法 | 可以查看和导出 | view and export only |

### 语言相关文案

| 键 | 中文 | English |
| --- | --- | --- |
| i18n.partial | 本页部分内容尚未翻译成{language}，暂以{fallback}显示。帮忙翻译 | Parts of this page aren't in {language} yet and are shown in {fallback}. Help translate |
| i18n.legal\_note | 本译文仅供参考，如有出入，以{language}版本为准。 | This translation is for reference. If it differs, the {language} version applies. |
| translate.title | 把 Zintriq 带到你的语言 | Bring Zintriq to your language |
| translate.lead | Zintriq 的大多数语言由母语者翻译。不管你说的是大语种还是只有几百人使用的语言，都欢迎加入。 | Most of Zintriq's languages are translated by native speakers. Whether your language has a billion speakers or a few hundred, you're welcome here. |
| translate.progress | {language}：已完成 {percent} | {language}: {percent} done |
| translate.start | 开始翻译 | Start translating |
| translate.request | 没有你的语言？申请添加 | Don't see your language? Request it |
| translate.credit | 翻译贡献者会显示在对应语言的致谢页上。 | Translators are credited on each language's thank-you page. |
| translate.orthography | 如果你的语言有多种写法，请在开始前与其他贡献者约定一种，并写在语言说明里。 | If your language has more than one writing system or spelling, agree on one with other contributors and note it in the language guide. |

## 已确认的决定与待办

下表是已经定下、并已写进上面各节文案的决定。

| 事项 | 决定 |
| --- | --- |
| 桌面端名称 | Zintriq；有第二个产品时再区分 |
| 定价 | 订阅；免费下载试用，到期只读与导出；个人约 $10/月、团队约 $20/席位/月、企业与教育联系销售；年付 10 个月；差异只在席位、协作、存储、支持 |
| 收款 | 软件走 Stripe + Flask + 现有账号；Zintriq 为记录商户；首次付费 14 天内可退；硬件走独立店铺 |
| 定位词 | 对外主叙事是科技系统的元空间：没有产品边界，边界也可以被建造。描述 / 模拟 / 实例化只用于 `meta/` 与桌面工厂 |
| 社区 | 中文“社区”、品牌“Zintriq 社区”、英文 Community；只在桌面端；先只开放免费分享；自动扫描 + 举报下架 + 人工抽查，1–3 个工作日上架；分成按净额，门槛内 0%、之后 15% |
| 「现在可用」 | 阶段 1 只写咖啡馆这类软件实例、本机保存与导出 |
| 停止付费 | 只读与导出；作品 30 天后下线；数据保留 90 天 |
| 离线超 30 天 | 锁编辑，不锁查看和导出 |
| 角标 | 试用期强制显示，付费可关；社区作品保留署名 |
| 硬件 | 温湿度、继电器、人体存在三个模块；ESP32 + ESPHome；支持第三方板；OTA 必须签名 |
| 运营主体 | 收费前注册公司；之前可以上线不收费的网站 |
| 旧页面 | 网站未发布过，网页 Builder、网页社区、博客、客户故事直接删除；若以后出现付费老用户，给 3–6 个月免费期 |

网站建好后要回头定的事（然后把对应占位符替换掉）：

- [ ] **网站首次上线时桌面端处于哪个阶段**：决定登录、试用、发布、社区这些文案用「阶段 1」还是「阶段 2」版本。阶段 1 没有账号登录，试用期也没法计时。
- [ ] **试用天数** `{trial_days}`。
- [ ] **各档云存储额度** `{quota_personal}`、`{quota_seat}`，以及公平使用条款。
- [ ] **社区分成门槛金额** `{threshold}`（付费上架开放时）。
- [x] 分享落地页 `/c/<id>`：已定，做并允许收录。
- [ ] **公司注册地**：决定法律页主体、Stripe 开户和 Windows 签名方案。
- [ ] **选定硬件独立店铺平台**（不默认用软件订阅的 Stripe 账户卖实物）。
- [ ] **法律页正文**：按「法律页需改动清单」起草，收费前请律师审阅。
- [ ] **价格复盘**：$10 / $20 是起点假设，上线后按数据调整。
