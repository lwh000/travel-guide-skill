---
name: travel-guide-html-guide
description: travel-guide 内部参考文档，不单独作为技能导入。
---

# HTML 攻略

用户要可预览、可点击、HTML、网页攻略时使用。先读 [maps.md](maps.md)、[live-data.md](live-data.md) 和 [media.md](media.md)。

**HTML 默认杂志版，用户指定的样式优先。** 用户只说「导出 HTML / 要网页 / 能点开」时按杂志排版：页头封面、行程主线、日卡、住宿卡；明确要极简或打印优先时简化装饰，保留内容、链接和来源。

极简或打印优先版在 `<body>` 标 `data-guide-style="minimal"` 或 `data-guide-style="print"`，让校验器跳过杂志版装饰提醒。未指定时保留默认样式。

**HTML 只转换已核实的事实。** 不要仅为网页装饰再搜酒店、餐厅、图片或坐标；没图用壳子渐变 / `.art-fig`，缺坐标的点不进 `points`。若制作 HTML 时发现原行程的关键事实缺证据，回到内容核实或删去具体断言，而不是把猜测填进网页。天气只在 [live-data.md](live-data.md) 的适用条件下加入；无对应日期数据时给官方查询入口。

## 文件

写一份可双击打开的**单 HTML 文件**（UTF-8，**不要 BOM**），无需构建。地图、图片、高德脚本允许依赖公开网络资源，不是完全离线包。样式写在 `<style>`。

从 [assets/guide-shell.html](../assets/guide-shell.html) 开工。保留：

- 杂志版视觉与勾选记忆脚本（`travel-guide:` + `tripId` + `location.pathname`）
- `#trip-geo` 必留；`#weather` 仅在天气影响本次行程且有目的地、日期时保留。无对应日期预报时可标 `data-weather-status="unavailable"` 并给官方查询入口；无关时删整节
- 自驾才留 `#map` / `#amap-box` / `#route-canvas` / 页签；飞机 / 高铁 / 火车、一城地铁步行留 `#transit`，删掉 `#map`
- 停靠筛选只在自驾
- 其余章节骨架

壳子负责视觉和 JS。用整块占位填充数据，不要复制 D1 再手搓 D2–D5：

| 占位 | 换成 |
|---|---|
| `{{DAILY_TABLE}}` | 完整 `<table>…</table>`（含表头；非自驾把「车程」改成「交通」）。**「日期」和「星期」必须是两列**，不要合成 `D1 · 9/27 周日` 一格 |
| `{{DAILY_CARDS}}` | 有逐日行程时每天一篇 `<article class="day">…</article>`，文案区给完整日期和星期；默认杂志版有图配 `<figure><img>`（只用合规景观图），无图可用 `.art-fig`，极简/打印版可省装饰；时段按实际负荷写 |
| `{{STOPS_TABLE}}` | 停靠表的 `<table>…</table>`；没有自驾内容（非 `self_drive`，或 `mixed` 无自驾段）时删掉整个 `<section id="stops">`，不只是留空表格，否则会露出一排空筛选按钮 |
| `{{WEATHER}}` | 需要天气时填入与地点、日期、来源相符的预报或历史气候；脚本缺数据时用 `data-weather-status="unavailable"` 的天气节说明缺口、官方入口与复核时间，不编气温卡。不需要天气时删整个 `#weather` 节及占位符 |
| `{{TRANSIT_FARES}}` | 交通在本次交付范围内且不画路线图时，填交通 `<table>`；查到价格则写来源和日期，查不到写「待官网确认」及官方入口。只要酒店/餐厅等单项或自驾页可删整个 `#transit` |
| `{{AMAP_LOADER}}` | 见下方「AMap 加载」；飞机 / 高铁 / 火车、一城地铁步行整块删除（含注释），自驾缺钥匙也整块删除，不要留注释占位 |

页头胶囊：`{{CHIP1}}` / `{{CHIP2}}` 填天数·交通、同行·预算这类短标签，两个都要有；`{{CHIP_WARN}}` 填季节风险，这次没有风险项时连同那一行 `<span class="chip warn">` 一起删掉，不要留空胶囊。

壳子的 `<style>` 里已备好可选排版类（`.summary-grid` / `.meter` / `.spine` / `.kvs` / `.callout` / `.quote` / `.budget-grid` / `.formula` / `.day-copy` 等），`</main>` 之前和 `#stops` 附近有可直接套用的最小片段注释。用得到才用，一律填真数据，不要为了用满样式去凑内容。

把其余样例和 `{{占位}}` 换成这次行程。交出去的文件里不能再有占位符，也不能再出现「出发地 / 过夜城 / 终点 / 服务区样例」。

## 要不要地图，以及 AMap 怎么加载

先算 `needs_map_ui`：`htmlMode` 是 `self_drive`，或 `mixed` 且存在 `drive:true` 且 `lineMode:route` 的视图。

- **不要地图**（一城地铁/步行、多城飞机/高铁/火车、没有自驾段的混合）：删掉 `#map`、导航「路线图」、`{{AMAP_LOADER}}` 整块注释。不要加载 `webapi.amap.com`。若本次写交通，保留 `#transit`，填已核实的价格或官方查询入口；只交付住/吃等单项时可删。`#trip-geo` 的 points / views 可空。
- **要地图**：保留 `#map`。分享或公开发布的文件默认 `mapRenderer=svg`，不嵌入地图凭据。私人本地文件使用 AMap 时，`{{AMAP_LOADER}}` 在生成时处理，不用运行时 `document.write`；钥匙从配置文件读 `jsKey` + `securityJsCode`，不要在聊天里贴。`mapRenderer=amap` 且两者都有时，先注入 `window._AMapSecurityConfig`，再加载 `https://webapi.amap.com/maps?v=2.0&key=…`。**插件按 needsDriving 定**：`htmlMode=self_drive`，或 `mixed` 且存在 `drive:true` 且 `lineMode:route` 的视图 → 加 `AMap.Driving`；否则只到 `AMap.Scale,AMap.ToolBar`。缺钥匙或 `mapRenderer=svg`：删除脚本，走路线示意图。纯自驾可删 `#transit`；`mixed` 若含飞机 / 高铁 / 火车段，保留票价表或官方查询入口。
- 交出去的文件里不能残留 `{{AMAP_LOADER}}` / `{{WEATHER}}` / `{{TRANSIT_FARES}}`，也不能残留 `document.write` 动态补载。
- 不要把和风 key 或高德 Web 服务 key 写进页面。

境外行程不接任何地图 JS：`mapRenderer=svg` + `linkProvider=google`（Google Maps search 链接）+ `coordinateSystem=wgs84`，坐标查不到就只给搜索链接。

`#trip-geo` 必须写 `version`（当前 `1.4`）、`tripId`、`htmlMode`、`mapRenderer`、`linkProvider`、`coordinateSystem`；`defaultView` 可选，写了就必须是某个 `views[].id`。可选 `weather` 对象见 maps.md。`htmlMode` 必须是 `self_drive` / `city_trip` / `multi_city_transit` / `mixed` 之一；境内 `linkProvider=amap` + `gcj02`，私人本地页有地图凭据才用 `mapRenderer=amap`，分享版用 `svg`；境外 `mapRenderer=svg` + `linkProvider=google` + `wgs84`。`fullNav`（全程驾车）在 `self_drive` 应有，且是 `https://uri.amap.com/navigation?`，`from` / `to` 是非空合法点位、`mode` 真为 `car`；`mixed` 的导航放自驾段 `views[].nav`，不放全程。`lineMode=route` 的 `path` 至少 2 个有效 point ID。非自驾不要保留驾车按钮或补能；`mixed` 按每段交通渲染，只在 `drive: true` 的视图用 Driving。

文件名跟行程走。用户用中文就用中文名，例如 `杭州3日.html` 或 `东京5日亲子.html`。

有 outputs 目录就放到那里，否则放工作区。对话里用 markdown 链接给出**绝对路径**。不要把整份 HTML 贴进聊天。运行环境确实没有文件写入能力时，再把完整 HTML 代码贴进对话，先说一句原因。

## 信息结构

即使用户的参考文件是巨大的地图 SPA，也只学结构，不抄他们的 JavaScript、JSON 或 Key。

1. **页头** — 标题、日期、同行、交通、资料截止日期；有 Commons 图可做满幅封面。
2. **摘要卡** — 过夜数、公里、免费高速窗口、预算带。里程 / 过路 / 预算构成用原生 `<details>`。非自驾不要硬写公里和过路。
3. **吸顶导航** — 只保留实际有内容的入口；天气、路线图、交通价、停靠分别按行程需求显示。
4. **天气** — 需要时独立成节，填入与出行日期相符的预报或有来源的历史气候；没有可靠数字就写官方查询入口和复核时间，不显示空卡。
5. **路线图与交通价** — 自驾：私人本地页有凭据可用 AMap 2.0，分享版或无凭据用 SVG。飞机 / 高铁 / 火车段列出已核实参考价或官方查询入口；`mixed` 有自驾又有城际大交通时两节并存。只交付住/吃等单项可省交通节。页签来自实际 `views`；地图中心来自这次坐标。
6. **每日总表** — `{{DAILY_TABLE}}`：日期列写全（`9 月 27 日`）、星期单独一列，别把 `D1 · 9/27 周日` 塞进同一格。
7. **逐日卡片** — `{{DAILY_CARDS}}`：**日期头（`D1` 徽章 + 粗体几月几日 + 星期胶囊，三段分开）**；有合规景观图时配图，无图用 `.art-fig` 或纯文字；按实际行程写有内容的时段与备选，自驾日按路线需要写导航和停靠，不硬凑固定数量。
8. **每天链接** — 自驾用高德 navigation URI；飞机 / 高铁 / 火车用 search / marker，不要为此留 `#map`；`mixed` 按每段交通写，不把非自驾段画成驾车。
9. **停靠 / 补能** — `self_drive` 或有自驾段的 `mixed` 才保留；筛选仅显示本次实际使用的服务区 / 加油 / 充电 / 停车等类别。
10. **住 / 吃 / 票 / 预算 / 打包** — 真名字、价格带、注意点、预订和地图按钮。住宿用 `.stay-grid` + `.stay-card`（每城主选 + 备选），卡里 `.rate` 放价格、`.kvs` 放片区 / 车位 / 预订；有片区风景图才上图，不要酒店 CDN。
11. **费用公式** — 区间 + 一行公式。有上限时推荐合计尽量低于上限；不够则按 planning.md 直说。
12. **关键提醒** — 限高（用户说了车型才写）、台风、施工绕行、上班日前车程、末班轮渡。
13. **说明 / 出处 / 图片许可**

出发前必订用复选框，并走壳子的 `localStorage`（失败时勾选降级，页面不能坏）。

## 视觉

默认像一本小旅行杂志，壳子已带好这些样式；用户要极简或打印优先时保留内容层级与清晰链接即可：

- **页头封面（默认杂志版可有图）**：已有本行程实际地点的合规 Commons 实拍图时可放入 `.hero-bg`；无图直接用壳子渐变，不为填封面拖延事实核实；极简/打印版可省图。
  - 在生成器里用 `HERO_IMAGE` / `HERO_CREDIT` 常量注入，**不要写进 `assets/guide-shell.html`**，否则会把某一次行程的地点泄漏给之后所有行程。
  - 图片上必须压一层深色渐变（上轻下重，如 `rgba(6,38,46,.34) → rgba(7,34,40,.88)`），保证白色大标题在任何底图上都清晰。
  - `{{HERO_CREDIT}}` 写「地点 · 作者 · 许可证」，渲染在 `hero-meta` 里；使用 Commons 图必须署名。
  - 打印样式已含 `.hero-bg{display:none}`，不要再加内联 `background` 覆盖它。
  - `{{LEDE}}` 写一句这次为什么值得走。
- **行程主线**：`.spine` 列 3–6 个节点（城市或地标），让人一眼看懂走向
- **摘要卡**：`.summary-grid` + `.summary-card` 写里程、过夜数、免费高速窗口这类硬数字
- **明信片式日卡**：`.day` + 可选 figure/`.art-fig` + `.day-copy`；`.day-copy` 顶部放日期头（`.day-head`：`.day-no` + `.day-date` + `.day-week`），日期用全写（`9 月 27 日`）不要简写成 `9/27`；`.slot` 只写当天实际有内容的时段，自驾段再加当天路线和必要停靠。HTML 里若壳子没有 `.day-head` / `.day-date` / `.day-week` 样式就补上，打印时保持黑字可读
- **住宿卡**：`.stay-grid` + `.stay-card`，`.rate` 放评分 / 价格，`.kvs` 放片区 / 车位 / 预订
- **预算**：`.budget-grid` + `.budget-card`，有上限时加 `.meter`
- 手机优先，字号偏大，对比足够，点击区域 ≥ 40px
- 中文字体栈必须含 `PingFang SC, Microsoft YaHei`
- 导航链接：`display:flex; align-items:center`；警告用 `.chip.warn`；提示块用 `.callout`
- 地图画在深色舞台上；AMap 用浅色底以便看清折线；过夜、停靠、景点用不同标记
- `#amap-box` 约 460–760px
- 不要加载 Google Fonts。不要热链酒店图库。

## 无障碍与打印

壳子已带基础无障碍属性和打印样式，填充内容时保持：

- 正文对比度足够；不要在浅底上放浅色字（`--muted` 这类灰只用于次要说明）
- 每个 `<img>` 都要有中文 `alt`（说清地点），装饰图用 `alt=""`
- 链接文字用地名，不要「点击这里」；按钮/链接点击区域 ≥ 40px
- 地图容器 `#route-canvas` 已有 `role="img"` + `aria-label`，换成这次行程的描述
- 壳体自带 `@media print`：隐藏导航/筛选/地图 iframe，链接后附 URL，`section` 和日卡避免跨页断开。用户打印时应当得到一份黑字白底、能照着走的纸质版
- 打印样式里 `#amap-box` 被隐藏、`#route-canvas` 强制显示，所以即使做了 AMap 真地图，打印出来也是示意图，不用额外处理

## 禁止

- 抄别人的高德 / Google Key
- 抄用户旧 HTML 里 1MB JSON + SPA
- 虚构 POI 或精确房价
- 残留 `{{WEATHER_ASOF}}` 等占位符；把空天气卡、无来源或其他日期的气温当成预报
- 无地图行程的 `#transit` 没有价格表
- 交出去的文件里还留着 `{{placeholders}}`
- 东京电车行程却画出驾车全程和补能，或一城地铁行程还留着 `#map`

## 交出去前

**先跑一遍 [../scripts/validate_html.py](../scripts/validate_html.py)：**`python scripts/validate_html.py 杭州3日.html`。它检查占位符、日期与星期、来源结构、`#trip-geo`、坐标与引用、地图模式、导航 URI、必要时的天气卡与来源、外部脚本和链接安全等离线条件。FAIL 先修；WARN 只报告真正影响交付的事项。校验器不联网核实旅游事实，来源内容仍由研究阶段确认。

FAIL 优先通过修结构、删无效字段或降级展示解决。若暴露出原行程关键事实缺证据，则按研究手册定向核实或删具体断言；不要为视觉完整度开启新一轮研究。

脚本过了之后，再人工确认这几条：

- 用户要打印 / PDF 时：直接让浏览器打印即可（壳子已带 `@media print`，真地图会被换成示意图）；确认打印预览是黑字白底、能照着走，链接后有 URL
- 没有 `{{`，也没有 `document.write` 补载脚本；壳子样例名（`出发地` `过夜城` `终点` `sample-trip`）一个不剩
- 壳子里的示例 / 可选片段注释块（摘要卡、主线、日卡、预算、kvs、callout）没有被整块留下当内容
- 页头两个 chip 都填了；没有风险项时 `chip warn` 整行已删除，没有空胶囊
- 点名的不是「出发地 / 过夜城 / 终点 / 服务区样例」
- 需要天气时有独立 `#weather`：有对应日期、有来源的气温才做卡片；缺数据时用 `data-weather-status="unavailable"` 说明缺口、官方入口及复核时间，不造气温卡；天气无关时删整节
- 飞机 / 高铁 / 火车、一城地铁步行没有 `#map` / `webapi.amap.com`，且有价格表；自驾才有路线图
- 要地图时，中心来自这次 `#trip-geo`
- 没有别人的 Key，也没有未替换的 `{{AMAP_LOADER}}` / `{{WEATHER}}` / `{{TRANSIT_FARES}}`
- `#trip-geo` JSON 可解析；`version` / `tripId` / `mapRenderer` / `linkProvider` / `coordinateSystem` 都已写
- `views[].path` / `markers` / `legs.from` / `legs.to` 的 ID 都存在于 `points`；不确定就搜成品文件里的 ID 核一遍，不要靠壳子静默忽略
- `htmlMode`、`linkProvider`、`lineMode` 与交通和链接一致；无去程/返程则无对应页签
- 无地图行程没有 Driving、驾车全程、补能、服务区、`#map`，且 `#stops` 整节（含筛选条）已删；`city_trip` 没有驾车 URI；`mixed` 只有 `drive: true` 的视图画驾车，导航在自驾段的 `views[].nav`
- `fullNav` 只在 `self_drive` 出现；纯 transit 的 `mixed` 不加载 Driving
- 每个 `<img>` 有中文 `alt`；外部链接文字是地名不是「点击这里」
- 境外文件：`mapRenderer=svg`，没有 `webapi.amap.com` 脚本、没有高德全程按钮；境内分享版或无 Key 的文件也不该有 `webapi.amap.com/maps` 引用

聊天里只摘要行程并给 HTML 文件链接。仅在有决策缺口时追问一个问题；私人本地自驾页若写入高德 JS Key，提醒文件持有人该钥匙会随 HTML 暴露，分享前改用 SVG 版。
