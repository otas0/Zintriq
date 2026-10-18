# 用真实界面和克制的黄色重塑 Zintriq 官网

**现行对照表（2026-10-04）：** 像素级 v2.0 已按本仓库适配，见 [design-spec-v2.md](./design-spec-v2.md)。支付为 **Stripe + Flask + 现有账号**；强调色仍是本文件的黄填充 `#F5D547`，不换蓝。下文是调研与黄色/动效底线，不覆盖 v2 的栈决定。

Zintriq 官网要显得精致可信，关键在三件事。第一，**把纯文字要点和表格换成"真实产品界面 + 真实示例数据"的 HTML/CSS 模拟图**，用一家咖啡馆贯穿：订单表、规则、点单屏，再放空间里的实例（预约台、传感器、模型），不要五积木分类，也不要把描述/模拟/实例化写成口号。第二，**把亮黄 #F5D547 限定为"实心填充色"**：只用于主按钮、少量高亮和状态标签，填充上的文字一律用近黑色（对比度 12.7:1）。浅色主题里另设一个深赭色 #7A5C00 作为"强调文字色"，因为这个黄色放在白底上只有 1.45:1，不能做文字、细边框或焦点环。第三，**全站动效保持在 300ms 以内，只动 `transform`/`opacity`**，以 CSS 为主、原生 API 为渐进增强，不需要任何前端框架。这些都能在 Flask + Jinja2 + 原生 JS/CSS 里落地：用 `light-dark()` 加 `color-scheme` 做三态主题，服务端按 cookie 渲染 `data-theme`，彻底消除首屏闪烁；中文正文用系统字体栈，配一款自托管拉丁字体，行高 1.75，开启 `text-autospace`；RTL 布局全部用逻辑属性；表单按 WCAG 2.2 新增的 3.3.8（验证码可粘贴、支持密码管理器）和 2.5.8（目标至少 24×24）来做。安装包尚未发布，所以下载页、硬件页、定价页都要按"诚实的候场室"来设计：给出"通知我"这样的可用操作、注明日期的进度，不放灰掉的按钮，不造假的社交证明。报告最后附一份可以直接交给编码代理的设计规格。现行公开口径以 [design-spec-v2.md](./design-spec-v2.md) 与 [website-content.md](./website-content.md) 为准。

## 标杆网站都在首屏放产品界面，没有一家靠要点列表

所调研的软件标杆，首页骨架几乎一致：一句定位标题、一行副标题、一到两个 CTA，紧接着就是**真实的产品界面**。Linear 的首屏是两张叠放的真实界面截图，后面的每个功能章节都配一张带逼真数据的界面模拟图，比如 ENG-2085 这样的工单号、跨 2026 年的甘特图、带状态徽章的代码 diff，首页还嵌了一个**带日期的 changelog** 来证明产品在持续交付 ([Linear](https://linear.app))。Framer 首屏是一段 36 秒的产品视频，设计、CMS、代码三个能力各配一张模拟图和一个 CTA ([Framer](https://www.framer.com/))。Raycast 用可交互的键盘图形，并标出 99.8% 崩溃率这样的硬指标，扩展生态则用**分类标签页**来浏览，页面不至于拉得太长 ([Raycast](https://www.raycast.com))。这些网站上几乎看不到纯文字要点列表；确实需要列举时，会做成每格带小图的卡片网格。Zintriq 现在"纯文字要点 + 表格、没有图像"的状态，恰好是这些网站都在回避的做法。

对 Zintriq 来说，最有效的改法是**一家咖啡馆贯穿模拟图**。Linear 把系统拆成接收→规划→构建→发布几个阶段，每段配上该阶段的真实产物；Framer 把产品拆成三项能力，各配一张模拟图 ([Linear](https://linear.app)；[Framer](https://www.framer.com/))。照这个思路，用三个标签页展示同一家店：订单（一张 4 行的订单表）、规则（"新订单进来时 → 通知后厨"）、点单（手机模拟框）。之后再放一组空间里的实例卡片（预约台、柜台、传感器、模型），不标注积木类别。整套方案只需要 HTML/CSS 模拟图和原生 JS 标签页，不需要 WebGL。

可信度方面，产品还没上线，就不能伪造社交证明。Dia 用三张真实功能截图代替用户评价，并且在可用的下载按钮旁边直接写上 "Windows coming soon" ([Dia](https://www.diabrowser.com/))。Raycast 的订阅表单附有 "No spam" 微文案 ([Raycast](https://www.raycast.com))。Zintriq 可以从 Jinja 列表渲染一个"构建日志"区块，内容是带日期的真实进展，比如"2026-09 · 咖啡馆示例可在本机保存"；公开页用"现在可用 / 即将推出"，不按积木分类。有创始人照片和"我们为什么做这个"就放，不放虚构的用户数、评价或 logo 墙。

硬件模块页可以参照创客品牌的做法。Arduino 按产品家族分组卡片，每张卡写明芯片型号、关键能力，并给出"Documentation"入口 ([Arduino Hardware](https://www.arduino.cc/en/hardware))。Raspberry Pi 5 每个子系统一个区块，后面跟完整规格、配件、FAQ 和**机械图纸** ([Raspberry Pi](https://www.raspberrypi.com/products/raspberry-pi-5/))。Flipper Zero 用带标注的渲染图和单独的 GPIO 引脚图 ([Flipper](https://flipper.net/))。Adafruit 给出精确尺寸、重量和多角度照片 ([Adafruit](https://www.adafruit.com/product/4116))。Zintriq 的温湿度、继电器、人体存在三个模块应该统一拍摄机位和背景，用内联 SVG 在照片上标注接口、指示灯和端子，规格控制在 6–10 行，并写清它们也在同一套元空间里，把硬件和软件的叙事连起来。

还有一个反面提醒：近黑底、渐变发光标题、1px 细边框、网格背景、毛玻璃这类"Linear 风格"已经被大量模仿，模仿多到"深色模式"都被人戏称为"Linear style" ([UX Collective](https://bootcamp.uxdesign.cc/the-rise-of-linear-style-design-origins-trends-and-techniques-4fd96aab7646)；[Frontend Horse](https://frontend.horse/articles/the-linear-look/))。光靠这些效果只会让网站显得像模板。效果可以用，但只能克制地点缀在真实产品内容周围，比如首屏视觉后面放一团径向光晕，再配一层带遮罩渐隐的点阵背景。

## 黄色 #F5D547 只能当填充，不能当文字

Zintriq 现在显得"廉价"，主要原因不在黄色本身，而在**用法缺少体系**：黄色铺得太多，大块使用，背景是纯黑。Refactoring UI 建议避免纯黑（"从一个很深的灰开始"），配 8–10 级灰阶，强调色"相当节制地"使用，并且事先定义好色阶，而不是临时生成 ([Refactoring UI](https://www.refactoringui.com/previews/building-your-color-palette))。Linear 改版时把每套主题的 98 个变量压缩到 3 个（底色、强调色、对比度），在 LCH 色彩空间里生成，还刻意**减少强调色渗进界面表面的比例**，好让界面"更中性、更耐看"；它的深色底是带一点冷调的 `#08090a`，不是 #000 ([Linear 改版](https://linear.app/now/how-we-redesigned-the-linear-ui)；[Linear](https://linear.app))。

令牌建议分两层。第一层是原始色阶，按 Radix 的 12 级角色划分：1–2 级做背景，3–5 级做组件底色（常态/悬停/按下），6–8 级做边框（8 级用于强边框和焦点环），9–10 级做实色填充，11–12 级做文字 ([Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale))。第二层是少量语义令牌，组件只引用语义令牌。Radix 明确说明黄色、琥珀等亮色在 9–10 级要**配深色前景文字** ([Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale))，这正好对上 #F5D547 的情况。我用 WCAG 2 相对亮度公式算了一下：#F5D547 在 #0B0C0E 上是 **13.5:1**，在白色上只有 **1.45:1**；近黑 #141414 放在黄色上是 **12.7:1**；深赭 #7A5C00 在白色上是 **6.25:1**，在 #FAFAF8 上是 5.98:1。结论是：

| 用法 | 浅色主题 | 深色主题 |
|---|---|---|
| 主按钮填充 | #F5D547 + 文字 #141414（12.7:1） | 同左 |
| 主按钮悬停 | 略深 #E9C736（文字 11.1:1） | 略亮 #F8E07A（文字 14.0:1） |
| 强调文字/链接/图标 | #7A5C00（6.25:1） | #F5D547（13.5:1） |
| 黄色浅底标签 | 底 #FFF6CC + 字 #6B5000（6.96:1） | 底 ≈#2A2612 + 字 #F5D547（10.5:1） |
| 焦点环 | 近黑 #17171A | #F5D547 |
| 禁止 | 黄色做文字、细边框、焦点环（1.45:1，低于 SC 1.4.11 要求的 3:1） | 大面积黄色铺底（刺眼） |

实现上用 `light-dark()`，它从 2024 年 5 月起已是 Baseline，但**必须先设置 `color-scheme`** 才会生效 ([MDN light-dark()](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark))。这带来一个对 Flask 很友好的做法：`:root { color-scheme: light dark }` 本身就能纯 CSS 跟随系统，完全不用 JS；用户手动选了"浅色"或"深色"时，服务端从 cookie 读出来，渲染成 `<html data-theme="dark">`，CSS 再用 `:root[data-theme="dark"]{color-scheme:dark}` 覆盖。这样一来，三种状态都没有首屏闪烁，也不需要阻塞渲染的内联脚本。OKLCH 适合生成色阶，悬停色可以用相对颜色语法推导，比如 `oklch(from var(--accent) calc(l + 0.1) c h)` ([Evil Martians](https://evilmartians.com/chronicles/oklch-in-css-why-quit-rgb-hsl))。不过交给编码代理的规格里，我直接给出了逐一核过对比度的 hex 值，省得代理自己再算。

WCAG 3 草案在探索 APCA，但 2.2 的合规仍按 2.x 对比度公式算（正文 4.5:1，大字和 UI 组件 3:1）。本次没有核实 APCA 阈值，所以规格只以 WCAG 2 比值为准。深色模式下阴影几乎看不见，层级应该靠表面逐级变亮（bg → surface → surface-2）来表达，阴影只留给下拉菜单、弹层这类"浮起"的元素。

## 中文排版靠系统字体、1.75 行高和 text-autospace

CJK 字体体积是排版方案的硬约束。一套韩文字体要覆盖"上万字符"，约 4 MB，而一套完整的拉丁字体约 250 KB；Google Fonts 用 `unicode-range` 按"常一起出现的字符"切片，最好的切法比均匀切片少用 **20 倍**的连接请求 ([Google Developers Blog](https://developers.googleblog.com/en/google-fonts-launches-korean-support/))。对一个小团队的 Flask 站点来说，结论很直接：**中文用系统字体栈**（PingFang SC、HarmonyOS Sans SC、MiSans、Microsoft YaHei、Noto Sans SC / Source Han Sans SC），**拉丁用一款自托管可变字体**，放在字体栈最前面，西文字形就走品牌字体，汉字自动回落到系统 CJK 字体。Linear 标题用 Inter Display、正文用 Inter ([Linear 改版](https://linear.app/now/how-we-redesigned-the-linear-ui))；Vercel Geist 把字号、行高、字距、字重打包成 `text-heading-72`、`text-copy-16` 这类命名类 ([Vercel Geist](https://vercel.com/geist/typography))。Zintriq 可以选 Inter（OFL 授权）作品牌拉丁字体，同样采用"命名字号类"的做法。如果首屏想用品牌化的中文展示字体，就在构建时用 `pyftsubset` 只截取标题实际用到的字，不要整套加载。HarmonyOS Sans 和 MiSans 能否作为 web font 自托管，本次没有核实授权条款，所以它们只出现在系统字体栈里。

断行和间距方面，2025–2026 年的进展对中文站点很重要。`text-autospace` 在 **2025 年 11 月成为 Baseline**，会在汉字与拉丁字母、数字之间自动插入窄间隙，比如 `HTML超文本标记语言` ([MDN text-autospace](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/text-autospace))。所以内容规范应改成"**中英之间不要手敲空格**"：浏览器加的是排版上更正确的窄间隙，默认的 `insert` 模式也不会在已有空格处再叠加。`text-wrap: balance`（标题）和 `pretty`（正文）是 Baseline 2024 的安全增强，其中 balance 在 Chromium 里最多处理 6 行 ([MDN text-wrap-style](https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap-style))。`text-spacing-trim`（压缩相邻 CJK 标点）目前只有 Chromium 123+ 支持，Firefox 和 Safari 都不支持，全球覆盖约 72.7% ([caniuse](https://caniuse.com/mdn-css_properties_text-spacing-trim))，而且需要字体带 `halt`/`chws` 特性 ([MDN text-spacing-trim](https://developer.mozilla.org/en-US/docs/Web/CSS/text-spacing-trim))。`word-break: auto-phrase` **只对 `lang="ja"` 生效** ([Chrome for Developers](https://developer.chrome.com/blog/css-i18n-features))，所以中文标题避免单字孤行只能靠人工：在 Jinja 模板里用 `<span class="nowrap">无代码平台</span>` 或 `<wbr>` 标出短语。中文绝不能用 `word-break: keep-all`，否则整段连续汉字会溢出容器。Chrome 118 已经取消了 CJK 的最小字号限制，小号中文现在按设定字号渲染 ([Chrome for Developers](https://developer.chrome.com/blog/css-i18n-features))。

数值建议如下，属于行业惯例，本次未逐一找到出处：中文正文 16–18px、行高 1.75，标题行高约 1.35；中文字距为 0，负字距只用 `:lang(en)` 限定在大号拉丁标题上；中文行宽约 40em（1em 约等于一个汉字，`ch` 是数字"0"的宽度，不适合中文），拉丁约 65ch；中文禁用斜体和伪粗体（`font-synthesis: none`），强调靠字重或颜色。另外要在 `<html>` 上写准确的 `lang`（`zh-Hans`、`ja`、`ko`），确保汉字统一码选用正确的地区字形。

RTL 和 130 多种语言这部分，本次没有抓取一手资料，下面是业界通行做法，实施前建议对照 MDN 的逻辑属性文档复核。Jinja 根据 Babel 的 `Locale.character_order` 输出 `dir="rtl"`；所有间距和定位一律用 `margin-inline-start`、`padding-inline`、`inset-inline-end`、`text-align: start`；只镜像有方向含义的图标（箭头、"返回"、进度），logo、对勾、播放键、电话图标不镜像；手机号、品牌名、代码用 `<bdi>` 或 `dir="ltr"` 隔离，`tel` 输入框固定 `dir="ltr"`；阿拉伯文不加字距，以免破坏连写。语言切换器不能用国旗，每个语言名要用它自己的文字书写（`<a hreflang="ar" lang="ar">العربية</a>`）。130 多种语言就做成可搜索的对话框，母语名和当前界面语言里的名称都能匹配。

## 动效控制在 300ms 内，原生 CSS 已经够用

几大设计系统对时长的划分基本一致。Material 3 的短档是 50–200ms，中档 250–400ms，长档 450–600ms；标准曲线是 `cubic-bezier(0.2,0,0,1)`，强调减速（入场）是 `cubic-bezier(0.05,0.7,0.1,1)`，强调加速（退场）是 `cubic-bezier(0.3,0,0.8,0.15)` ([M3 Motion](https://raw.githubusercontent.com/material-components/material-components-android/master/docs/theming/Motion.md))。IBM Carbon 的按钮切换是 70ms，展开和 toast 是 240ms，大型展开是 400ms，并明确"位移或缩放越大，动画越长" ([Carbon motion](https://carbondesignsystem.com/elements/motion/overview/))。Fluent 2 的时长令牌从 50ms 到 500ms 共 8 级 ([Fluent durations.ts](https://raw.githubusercontent.com/microsoft/fluentui/master/packages/tokens/src/global/durations.ts))。实践者的意见更直接：UI 动画"通常应短于 300ms"，用 ease-out 带来"响应迅速"的感觉，**键盘触发的操作永远不要做动画**，只动会走合成层的 `transform`/`opacity`，因为 margin、padding 会触发重排和重绘 ([Emil Kowalski](https://emilkowal.ski/ui/great-animations))。综合下来，Zintriq 的动效规则是：入场用减速曲线，退场时长约为入场的 60–75%、用加速曲线（例如菜单 300ms 打开、200ms 关闭）；交错动画每项间隔 30–60ms，最多 5–6 项。交错时长是经验值，不是标准规定。

哪些该动、哪些不该动，判断标准是"状态变化如果不过渡，会不会显得突兀或让人丢失空间感"。按钮悬停、按下、菜单展开、手风琴、标签指示条、月付/年付切换、表单校验反馈都值得做短动画；首屏的 LCP 内容**绝不能**藏在淡入动画后面，首屏 H1、副标题和 CTA 要直接写在 HTML 里，一开始就可见。LCP 资源应出现在初始 HTML 中，不要懒加载，`fetchpriority="high"` 最多给一两张图 ([web.dev LCP](https://web.dev/articles/optimize-lcp))。滚动渐显只用"透明度 + ≤16px 位移"，每个元素只播一次，而且显隐 class 必须由 JS 添加，保证不开 JS 时内容依然可见。用 `translate` 做起始偏移不会产生 CLS；手风琴改变高度确实会让布局移动，但点击后 500ms 内的位移不计入 CLS ([web.dev CLS](https://web.dev/articles/cls))，所以手风琴的过渡要控制在 300ms 内。INP 的"良好"线是 200ms ([web.dev INP](https://web.dev/articles/inp))，事件处理函数要轻，保证下一帧就能给出视觉反馈。`will-change` 只作为"最后手段"由脚本临时开关，不要写死在样式表里 ([MDN will-change](https://developer.mozilla.org/en-US/docs/Web/CSS/will-change))。

截至 2026 年 10 月，各项原生 API 的支持情况决定了它们怎么用：

| API | 状态 | Zintriq 用法 |
|---|---|---|
| `@starting-style` + `transition-behavior: allow-discrete` | 2024 年 8 月 Baseline ([web.dev](https://web.dev/blog/baseline-entry-animations)) | 移动菜单（Popover API）、弹层入场，直接使用 |
| 同文档 View Transitions | 2025 年 10 月 Baseline，Firefox 144+ ([web.dev](https://web.dev/blog/same-document-view-transitions-are-now-baseline-newly-available)) | 主题切换的圆形揭示，直接使用 |
| 跨文档 View Transitions | Chrome/Edge 126、Safari 18.2，Firefox 不支持 ([Chrome](https://developer.chrome.com/docs/web-platform/view-transitions/cross-document)) | Flask 多页站只需加 `@view-transition{navigation:auto}`，作为增强 |
| 滚动驱动动画 | Chrome 115、Safari 26，Firefox 稳定版仍需打开开关 ([buildmvpfast](https://www.buildmvpfast.com/blog/css-scroll-driven-animations-replace-js-2026))；已列入 Interop 2026 ([web.dev](https://web.dev/blog/interop-2026)) | 仅在 `@supports` 内作增强，默认写成最终状态 |
| `interpolate-size` / `::details-content` | 仅 Chromium 129+ ([Chrome](https://developer.chrome.com/docs/css-ui/animate-to-height-auto)) | FAQ 高度动画作增强，其他浏览器瞬时展开 |
| IntersectionObserver、Web Animations API | 普遍支持 | 滚动渐显、价格数字切换的兜底层 |

因此**不需要 GSAP 或 Motion One**。只有复杂的滚动编排或需要速度衔接的弹簧物理时，才值得引入库。

无障碍方面，SC 2.3.3（AAA）要求交互触发的**运动**可以关闭，同时明确颜色、模糊、透明度变化不算运动，并点名视差是非必要动画 ([WCAG 2.3.3](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html))。所以 `prefers-reduced-motion` 的正确做法是"减少而非全删"：保留淡入淡出和颜色变化，去掉位移、缩放、视差、页面滑动和抖动。写法上采用"先无动效"，即只在 `(prefers-reduced-motion: no-preference)` 里开启运动，不要用一刀切的 `0.01ms` 重置 ([Josh Comeau](https://www.joshwcomeau.com/react/prefers-reduced-motion/))。SC 2.2.2（A 级，即使只做 AA 也适用）要求自动播放、持续超过 5 秒的移动内容提供暂停机制 ([WCAG 2.2.2](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html))，所以首屏如果用循环视频或跑马灯，必须配一个可见的暂停按钮。

主题切换用 `document.startViewTransition()` 做一次从按钮位置展开的 `clip-path` 圆形揭示，时长约 400ms；不支持 View Transitions 或开启了减少动效时，直接瞬时切换。这是社区通行做法，非规范 ([dev.to](https://dev.to/renekaesler/a-modern-approach-of-implementing-dark-mode-20f8))。千万不要给 `*` 加 `transition: background-color, color`：既耗性能，各元素褪色的节奏也不一致。

## 关键页面要把"还没发布"设计成可用的候场室

**下载页。** 现在的下载页大致分两类。Obsidian 自动识别操作系统，给出一个带版本号的主按钮，下方完整列出各平台 ([Obsidian](https://obsidian.md/download))。VS Code 把各平台并排放成网格，架构单独列出，用户熟悉的 "Apple silicon / Intel chip" 措辞旁边标出最低系统版本，还附一行许可条款 ([VS Code](https://code.visualstudio.com/download))。Docker 在 Mac 上直接放两个按钮，校验和放在 release notes 里，并配有"打开 .dmg → 拖到 Applications → 启动"的编号步骤 ([Docker docs](https://docs.docker.com/desktop/setup/install/mac-install/))。Zintriq 目前一个安装包都没有，所以下载页应该是"按平台订阅通知"的网格：识别出的系统排第一并标注"已识别：macOS"，三个平台始终都可见，识别错了也不影响使用；每张卡显示中性的"即将推出"徽章，主操作改成"macOS 版就绪时通知我"（邮箱 + 预勾选当前系统的平台复选框）；版本、最低系统、文件大小、SHA-256、更新日志的位置先留出来，标"待公布"。**绝不出现灰掉的"下载"按钮**，那看起来就像页面坏了。手机访客装不了桌面应用，主 CTA 应换成"把下载链接发到我邮箱"。安装包发布后，点击下载即弹出"接下来会发生什么"面板，说明 Gatekeeper/SmartScreen 提示，以及首次启动即开始试用。

**定价页。** Lazyweb 在 2026 年 7 月扫描了 301 个定价实验：57% 涉及年付，34% 用了月付/年付切换，18% 预先突出默认方案（通常是年付）。但来源自己也说明，这些只是"检测到的改动"，**不是实测的提升** ([Lazyweb](https://www.lazyweb.com/research/monthly-vs-annual-billing-toggle-pricing))。Zintriq 的"年付 = 10 个月"最诚实的表述是"**年付 · 送 2 个月**"（实际省 16.7%，写"省 17%"可以接受，写"省 20%"就是虚假宣传）。年付状态下的主价格写"$8.33/月"，下方紧跟"按年付费 $100"，不能藏进小字。Team 写"$20/席位/月"，并给出"5 席 = $100/月"这样的具体例子。上方用 Personal 和 Team 两张自助卡片，Enterprise 和 Education 合进一条"联系销售"的窄带，下面接完整对比表，再下面是 FAQ。每个自助 CTA 下面直接写试用条款，核心一句是"**试用结束后工作区变为只读，数据不会删除**"，用来消除只读模式带来的"会丢数据"的担心。FAQ 必须回答"安装包还没出，我现在付费买的是什么"。产品未上线时不要挂"最受欢迎"徽章，可以改成"适合团队"。价格切换时数字淡出、换值、再淡入，配合 `tabular-nums`，宽度不跳动。

**硬件候补页。** 关于硬件候补的严谨证据很少。PreProduct 分析了 113 万笔预购，**91.7% 没有打折**，43.8% 采用"之后再扣款" ([PreProduct](https://preproduct.io/11-best-pre-order-landing-page-examples/))；Framework 分地区开放预购，用户会在社区里公开追踪各批次的发货日期 ([Framework blog](https://frame.work/blog/now-available-for-pre-order-in-uk-germany-and-france)；[Framework community](https://community.frame.work/t/shipping-dates-fw-16/35491?page=2))。可见进度透明本身就会变成公开话题，所以要主动、带日期地公布。可信度元素按顺序排：标明"原型/渲染图"的真实图片；标明"目标值"的规格；阶段指示器（概念 → 原型 → EVT/DVT → 量产），高亮当前阶段；带日期的开发日志；分地区发货 FAQ。表单只要必填邮箱，加上可选的国家/地区和"感兴趣的模块"复选框，不要手机号，不要注册账号。营销订阅用单独的、默认不勾选的同意框，并采用双重确认邮件。注意：本次没有核实 GDPR 一手资料，双重确认在德国被判例要求一事需要找法务确认。不要用假倒计时，也不要写"仅剩 N 个名额"。

**手机号 + 短信 + 密码的注册登录。** 这里有三份权威依据。web.dev 要求验证码用**单个**输入框，`type="text"`、`inputmode="numeric"`、`autocomplete="one-time-code"`，短信末尾使用绑定域名的格式 `@zintriq.com #123456`，这样可以启用 WebOTP 并减少钓鱼 ([web.dev SMS OTP](https://web.dev/articles/sms-otp-form))。GOV.UK 要求验证码输入接受空格和连字符，提供"没收到短信？"入口，注册时允许核对和修改号码，登录时不暴露号码，有效期 15 分钟，连续错 10 次后加延迟，错误信息要具体 ([GOV.UK](https://design-system.service.gov.uk/patterns/confirm-a-phone-number/))。NIST SP 800-63B-4（2025 年 8 月定稿）规定：密码作为 MFA 的一部分时**最少 8 位**，单因素时最少 15 位；最大长度至少允许 64 位；**不得强制字符组合规则**，但必须对照泄露库和常见密码黑名单检查；必须允许粘贴、密码管理器和显示密码；短信 OTP 属于"受限"认证器 ([NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html))。WCAG 2.2 的 SC 3.3.8 明确，验证码"至少必须能粘贴"，密码管理器和复制粘贴都属于合格的辅助机制 ([WCAG 3.3.8](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html))；SC 2.5.8 要求目标至少 24×24 CSS px，关键控件建议 44×44 ([WCAG 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html))。

据此，注册流程分三步。第一步，国家区号（按 IP/语言预选，可按国名或区号搜索）+ 号码，接受粘贴进来的 E.164 格式，服务端用 Python `phonenumbers` 规范化。第二步，单个验证码输入框，满 6 位自动提交；上一步填的号码直接显示，并附"更换号码"链接，满足 SC 3.3.7 不重复输入的要求；60 秒倒计时结束后"重新发送"才变为可用，读屏器只在"已发送"和"可以重发"两个时刻播报，不逐秒播报。第三步，设置密码：规则只写一条"至少 8 位"，配显示/隐藏切换，用 zxcvbn 类估算器给出**文字建议**，文字比彩色进度条更显眼；命中泄露库时提示"该密码出现在数据泄露中，请换一个"。如果视觉上一定要分格显示验证码，就把分格画在一个真实的 `<input>` 上方，否则粘贴、自动填充和退格都会出问题。登录默认"手机号 + 密码"，旁边提供"改用验证码登录"；"忘记密码"统一用"如果该号码已注册，我们已发送验证码"这样的中性文案，防止账号枚举。Team/Enterprise 应额外提供通行密钥或 TOTP，因为 NIST 不把短信视为强认证。邮箱作为第二登录方式，放到账户设置里"稍后添加"。

**移动端导航。** NN/g 2016 年的研究（179 名受试者，数据较旧，但仍是主要证据）发现：隐藏式导航让可发现性**下降 20% 以上**；移动端组合式导航（部分链接可见 + 菜单）的使用率是 86%，纯隐藏式只有 57%；它还建议**桌面端不要用汉堡菜单**，链接不超过 4 个时直接全部显示 ([NN/g](https://www.nngroup.com/articles/hamburger-menus/))。菜单触发器最好带"菜单"文字，并且看起来可点击 ([NN/g](https://www.nngroup.com/articles/find-navigation-desktop-not-hamburger/))。Zintriq 的移动端头部可以是：logo · "定价"（可见文字链接）· "菜单"按钮。点开后是全屏面板，顺序为产品、硬件（附"候补"小标签）、定价、下载、文档、登录，主 CTA 固定在面板底部，文案用"获取通知"而不是"下载"。头部下滑时隐藏、上滑时出现；`html{scroll-padding-top}` 保证获得焦点的元素不被吸顶头部遮住（SC 2.4.11）；面板打开时锁定焦点，Esc 关闭，关闭后焦点回到触发按钮。

## 结论

这次研究得出一个结论：Zintriq 网站显得"粗糙"，问题不在缺少特效，而在**缺少证据和体系**。标杆网站的精致感来自真实界面、真实数据、带日期的进展，再加上一套严格的令牌，发光和毛玻璃只是点缀。对一个还没发布安装包的产品，这其实是好消息：最能建立信任的元素，比如咖啡馆模拟图、构建日志、诚实的状态徽章，用 Jinja 模板加 CSS 就能做，成本很低，而且比任何动效都更有说服力。

技术上，2024–2026 年的平台进展让"不用框架"不再是妥协。`light-dark()` + `color-scheme` + 服务端 cookie 解决了三态主题和首屏闪烁；`text-autospace` 解决了中英间距；`@starting-style`、Popover 和 View Transitions 解决了菜单、弹层和页面过渡。剩下的差距只在 Firefox 对跨文档过渡和滚动驱动动画的支持上，而按"默认最终状态、渐进增强"的写法，这些差距对用户是不可见的。本报告有几处没有核实：APCA 阈值、RTL 细节、中国大陆安卓输入法对 `one-time-code` 的支持、HarmonyOS Sans/MiSans 的 web font 授权，上线前应逐项验证。

---

## 附录：实施规格（可直接交给编码代理）

### A. 全局约束

- 技术栈：Flask + Jinja2 + 原生 CSS/JS，不用框架、不用动画库。CSS 拆为 `tokens.css`、`base.css`、`components.css`，JS 全部 `defer`。
- `<html lang="{{ locale_tag }}" dir="{{ 'rtl' if is_rtl else 'ltr' }}" {% if theme in ('light','dark') %}data-theme="{{ theme }}"{% endif %}>`，`theme` 从 cookie `theme` 读取，取值 `light|dark|system`。
- 组件只引用语义令牌，禁止直接写 hex。所有间距和定位用逻辑属性（`*-inline-*`、`*-block-*`、`inset-inline-*`）。
- 交互目标至少 24×24，主要按钮和移动端菜单项至少 44×44。
- 合规底线：WCAG 2.2 AA，对比度按 WCAG 2 公式计算。

### B. 颜色令牌（hex 对比度已逐一计算）

```css
:root{
  color-scheme: light dark;
  /* 品牌 */
  --yellow-9: #F5D547;
  /* 语义：light-dark(浅, 深) */
  --color-bg:            light-dark(#FAFAF8, #0B0C0E);
  --color-bg-subtle:     light-dark(#F3F2EE, #111215);
  --color-surface:       light-dark(#FFFFFF, #16171B);
  --color-surface-2:     light-dark(#F7F6F2, #1C1D22);
  --color-border:        light-dark(#E4E2DC, #26272D);   /* 装饰性分隔线 */
  --color-border-strong: light-dark(#8E8B82, #6A6B74);   /* 输入框/控件边框：≥3:1（3.26 / 3.7） */
  --color-text:          light-dark(#17171A, #EDEDEF);   /* 17.1:1 / 16.7:1 */
  --color-text-muted:    light-dark(#5C5B57, #A1A1AA);   /* 6.5:1 / 7.6:1 */
  --color-accent-solid:       var(--yellow-9);
  --color-accent-solid-hover: light-dark(#E9C736, #F8E07A);
  --color-on-accent:     #141414;                         /* 黄底上 12.7:1，两种主题都不用白字 */
  --color-accent-text:   light-dark(#7A5C00, #F5D547);   /* 6.25:1 白底 / 13.5:1 */
  --color-accent-subtle-bg:   light-dark(#FFF6CC, #2A2612);
  --color-accent-subtle-text: light-dark(#6B5000, #F5D547); /* 6.96:1 / 10.5:1 */
  --color-focus:         light-dark(#17171A, #F5D547);
  --color-danger-text:   light-dark(#B42318, #F97066);   /* 6.6:1 / 7.0:1 */
  --color-success-text:  light-dark(#067647, #47CD89);   /* 5.7:1 / 9.7:1 */
  /* chip 色调（内部设计实验室）：只作浅底和图标，文字仍用 --color-text */
  --tint-data:      oklch(0.70 0.12 240 / .14);
  --tint-interface: oklch(0.70 0.12 300 / .14);
  --tint-logic:     oklch(0.72 0.13 150 / .14);
  --tint-connect:   oklch(0.72 0.13 30  / .14);
  --tint-publish:   oklch(0.86 0.15 95  / .18);
}
:root[data-theme="light"]{ color-scheme: light; }
:root[data-theme="dark"] { color-scheme: dark; }
```

黄色使用规则：
- 每个视口最多 1 个黄色主按钮，每个区块最多 1 处黄色高亮。黄色在整页像素中的占比应很小，这条是设计判断，没有数据来源。
- 黄色永远不做文字、细边框或浅色主题下的焦点环。
- 深色主题下不做大面积黄色铺底；首屏光晕最多用 `radial-gradient(600px circle at 50% 0%, oklch(0.86 0.15 95 / .12), transparent)`。

### C. 字体与字号

```css
@font-face{ font-family:"Inter"; src:url(/static/fonts/InterVariable.woff2) format("woff2");
  font-weight:100 900; font-display:swap; }
:root{
  --font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
    "PingFang SC", "HarmonyOS Sans SC", "MiSans", "Hiragino Sans GB", "Microsoft YaHei",
    "Noto Sans SC", "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  --step--1: clamp(0.875rem, 0.85rem + 0.1vw, 0.9375rem);  /* 14–15 标签/说明 */
  --step-0:  clamp(1rem, 0.96rem + 0.2vw, 1.125rem);       /* 16–18 正文 */
  --step-1:  clamp(1.25rem, 1.15rem + 0.45vw, 1.5rem);     /* 20–24 小标题 */
  --step-2:  clamp(1.5rem, 1.3rem + 0.9vw, 2rem);          /* 24–32 H3 */
  --step-3:  clamp(2rem, 1.6rem + 1.8vw, 3rem);            /* 32–48 H2 */
  --step-4:  clamp(2.5rem, 1.8rem + 3vw, 4.5rem);          /* 40–72 首屏 H1 */
  --lh-body: 1.6; --lh-heading: 1.15; --tracking-display: -0.02em;
  --measure: 65ch;
}
:lang(zh),:lang(ja),:lang(ko){ --lh-body:1.75; --lh-heading:1.35; --tracking-display:0; --measure:40em; }
:lang(zh) h1{ font-size: calc(var(--step-4) * .9); }        /* 中文首屏比英文小约 10% */
html{ font-family:var(--font-sans); text-autospace:normal; text-spacing-trim:normal; font-synthesis:none;
  -webkit-text-size-adjust:100%; }
body{ font-size:var(--step-0); line-height:var(--lh-body); color:var(--color-text); background:var(--color-bg); }
h1,h2,h3{ line-height:var(--lh-heading); letter-spacing:var(--tracking-display); text-wrap:balance; font-weight:650; }
p,li,figcaption{ text-wrap:pretty; max-inline-size:var(--measure); }
:lang(zh),:lang(ja){ line-break:strict; }
:lang(ko){ word-break:keep-all; }
:lang(ar){ letter-spacing:0 !important; --lh-body:1.8; }
.nowrap{ white-space:nowrap; }
.num{ font-variant-numeric:tabular-nums; }
```

字重只用 400、500、650 三档。全站最多两个字族（Sans + Mono）。中文文案中，汉字与西文、数字之间**不手敲空格**。

### D. 间距、布局、圆角、层级

```css
:root{
  --space-1:.25rem; --space-2:.5rem; --space-3:.75rem; --space-4:1rem; --space-5:1.5rem;
  --space-6:2rem; --space-7:3rem; --space-8:4rem; --space-9:6rem; --space-10:8rem;
  --container:1200px; --gutter:clamp(16px, 4vw, 24px);
  --section-y: clamp(var(--space-8), 10vw, var(--space-10));   /* 64→128px */
  --header-h: 64px;
  --radius-sm:6px; --radius-md:10px; --radius-lg:16px; --radius-pill:999px;
  --shadow-1: 0 1px 2px oklch(0 0 0 / .08), 0 1px 1px oklch(0 0 0 / .04);
  --shadow-2: 0 4px 12px oklch(0 0 0 / .10), 0 2px 4px oklch(0 0 0 / .06);
  --shadow-3: 0 16px 40px oklch(0 0 0 / .18), 0 4px 12px oklch(0 0 0 / .08);
}
:root[data-theme="dark"], :root:not([data-theme]) { /* 深色：靠表面变亮表达层级，阴影仅浮层 */ }
html{ scroll-padding-top: calc(var(--header-h) + var(--space-4)); }
```

圆角使用：按钮和输入框用 `--radius-md`；卡片和模拟窗口用 `--radius-lg`；徽章和标签用 `--radius-pill`；同一层级的组件圆角必须一致。阴影使用：卡片在浅色下用 `--shadow-1`，深色下不加阴影而改用 `--color-surface`；下拉菜单和弹层用 `--shadow-3`。

### E. 动效令牌

```css
:root{
  --dur-instant:100ms; --dur-fast:150ms; --dur-base:220ms; --dur-slow:300ms; --dur-reveal:500ms;
  --ease-std:  cubic-bezier(0.2, 0, 0, 1);       /* 屏内移动 */
  --ease-out:  cubic-bezier(0.05, 0.7, 0.1, 1);  /* 入场 */
  --ease-in:   cubic-bezier(0.3, 0, 0.8, 0.15);  /* 退场 */
  --ease-soft: cubic-bezier(0.33, 0, 0.1, 1);    /* 滚动渐显 */
  --stagger: 50ms;  /* 最多 6 项 */
}
@view-transition{ navigation:auto; }
::view-transition-old(root),::view-transition-new(root){ animation-duration:250ms; }
@media (prefers-reduced-motion: reduce){
  ::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){ animation:none !important; }
}
```

| 交互 | 规格 |
|---|---|
| 按钮悬停 | 背景色 `--dur-fast` `--ease-std` |
| 按钮按下 | `scale:.97`，100ms；仅在 `no-preference` 下启用 |
| 焦点 | 无动画，`outline:3px solid var(--color-focus); outline-offset:2px`；`forced-colors` 下改为 `Highlight` |
| 移动菜单（Popover + `@starting-style`） | 打开 300ms `--ease-out`、关闭 200ms `--ease-in`，`translate` 偏移 -12px→0；减少动效时只做淡入淡出 |
| 下拉 / 标签指示条 | 220ms `--ease-std`；面板内容只淡入 150ms，不滑动 |
| FAQ | `<details>`，在 `@supports (interpolate-size: allow-keywords)` 内做 220ms 高度动画，其余浏览器瞬时展开 |
| 价格切换 | WAAPI：旧值淡出加 -6px 位移 120ms `--ease-in`，新值 180ms `--ease-out`；`.num`；减少动效时瞬时替换 |
| 滚动渐显 | `[data-reveal]`，opacity + 16px，500ms `--ease-soft`，只播一次；用 IntersectionObserver，`.js` 前缀，不开 JS 也可见；**首屏不用** |
| 主题切换 | `startViewTransition` + `clip-path` 圆形揭示 400ms；不支持或减少动效时瞬时切换；禁止对 `*` 设置颜色过渡 |
| 校验错误 | 错误文字淡入 + 4px 位移 150ms；不抖动 |
| 禁止 | 键盘操作动画、视差、自动轮播（如有，必须带暂停按钮）、超过 1 秒的数字滚动计数、动画化 width/height/top/left、首屏 opacity:0 |

### F. 组件规则

- **按钮**：`.btn-primary` 用黄色填充 + `--color-on-accent`，高 44px，左右内边距 20px，字重 500；`.btn-secondary` 用透明底 + 1px `--color-border-strong` + `--color-text`；`.btn-ghost` 只有文字和图标。文字型 CTA 末尾加"→"，RTL 下镜像。每个区块最多一个 primary。
- **导航**：桌面端链接全部可见，不用汉堡菜单。移动端显示 logo + "定价" + 带文字的"菜单"按钮，菜单用全屏 Popover，主 CTA 固定在底部，Esc 关闭，关闭后焦点回到触发按钮。头部吸顶，下滑隐藏、上滑出现（用 `translate`）。
- **主题控件**：三态（跟随系统 / 浅色 / 深色）单选组或 `<select>`，可见标签为"主题"，不能只放图标；写入 cookie `theme`（`path=/; max-age=31536000; SameSite=Lax`）。
- **语言切换**：可搜索对话框；每项用母语名并带 `lang`/`hreflang`；当前项标 `aria-current="true"`；不用国旗；输出 `<link rel="alternate" hreflang>`。
- **卡片 / 产品模拟窗**：`--color-surface`、1px `--color-border`、`--radius-lg`，顶部可加三点窗口栏。示例数据必须逼真（订单号、日期、金额），禁止 Lorem。
- **积木标签（chip）**：仅内部 `/__design` 实验室使用。公开页不用 chip 轨，也不把数据/界面/逻辑/连接/发布写成产品分类。
- **状态徽章**：`Beta 可用`（accent-subtle）、`开发中`、`计划中`（中性：`--color-bg-subtle` + `--color-text-muted`）。不用灰色禁用样式。
- **表单字段**：可见 `<label>`，提示文字放在输入框上方，用 `aria-describedby` 关联；错误文字加视觉隐藏的"错误："前缀，并设 `aria-invalid`；提交出错时，焦点移到顶部错误摘要，`<title>` 前加"错误："；保留用户已填的值；绝不阻止粘贴。
- **图片**：一律写 `width`/`height` 或 `aspect-ratio`；首屏图加 `fetchpriority="high"`，不懒加载；其他图片 `loading="lazy"`。

### G. 页面规则

- **首页**：首屏（元空间 H1、副标题、主 CTA 下载 + 次 CTA 产品、咖啡馆模拟图）→ 订单 / 规则 / 点单标签页 → 空间里的实例卡（不标积木）→ 硬件预告条 → 项目保存在电脑上 → 构建日志 → 结尾 CTA（没有产品边界）。
- **下载页**：识别出的系统卡片排第一并标"已识别"；三平台卡片展示架构（macOS：Apple silicon / Intel 或 Universal；Windows：x64 / Arm64；Linux：.deb / .rpm / AppImage）、最低系统、版本、大小、SHA-256、更新日志，未知项写"待公布"；未发布时显示"即将推出"徽章和"就绪时通知我"表单（邮箱 + 预勾选平台）；手机访客显示"把下载链接发到我邮箱"；发布后点击下载即展示"接下来"三步面板。订阅成功后，按浏览器记住并显示"已加入 macOS 通知列表"。
- **定价页**：顶部切换"月付 / 年付 · 送 2 个月"，默认年付；Personal 显示 $8.33/月，下方"按年付费 $100"；Team 显示 $16.67/席位/月，下方"每席位每年 $200"和"5 席示例"。（价格用模板变量，以上按 $10 / $20 计算。）Enterprise 和 Education 放在"联系销售"窄带。每个 CTA 下注明试用时长、是否需要银行卡、"试用结束后只读，数据不删除"。下方依次是对比表和 FAQ（包括"安装包未发布时付费买的是什么"）。未上线前不放"最受欢迎"徽章。
- **硬件页**：家族卡片（名称、芯片、能力、状态）→ 单个模块页：统一机位的照片 + SVG 标注 → 6–10 行规格（标明"目标值"）→ 包装清单 → 文档和引脚图链接 → 阶段指示器（概念 / 原型 / EVT / DVT / 量产）→ 开发日志 → 候补表单（必填邮箱，可选地区和模块复选框，营销同意框默认不勾选，双重确认邮件）。不用倒计时，不写"剩余名额"。
- **注册**：
  1. 第一步：区号（可搜索，按地区预选）+ `type="tel" inputmode="tel" autocomplete="tel-national" dir="ltr"`。
  2. 第二步：单个输入框 `type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="6" dir="ltr"`，满 6 位自动提交；显示上一步的号码并附"更换号码"；60 秒后可重发，`role="status"` 只在开始和可重发时播报；附"没收到短信？"折叠说明。短信末行使用 `@zintriq.com #123456`。
  3. 第三步：`autocomplete="new-password"`，至少 8 位，最大 ≥64 位，不设组合规则，检查泄露黑名单，显示/隐藏按钮用 `aria-pressed`，强度反馈以文字为主，`aria-live="polite"` 防抖 500ms。
- **登录**：手机号 + 密码（`current-password`），提供"改用验证码登录"；"忘记密码"使用中性文案；对每个号码和每个 IP 限流；可选通行密钥。邮箱在账户设置中"稍后添加"为第二登录方式。

### H. 验收清单

- Lighthouse / CrUX 目标：LCP ≤2.5s，INP ≤200ms，CLS ≤0.1。
- 关闭 JS 时所有内容可见；开启 `prefers-reduced-motion: reduce` 后没有位移类动画。
- 浅色、深色、`forced-colors` 三种模式下，焦点环都可见，且不被吸顶头部遮挡。
- 用 `lang="zh-Hans"`、`en`、`ar`（RTL）三种语言各走查一遍首页和注册流程；手机号在 RTL 下不乱序。
- 验证码可粘贴，iOS/Android 能自动填充，密码管理器能保存凭据。
- 所有颜色组合都来自 B 节令牌，没有新增 hex。
