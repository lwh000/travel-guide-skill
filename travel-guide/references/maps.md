# 路线图与停靠点

按这次需求只读对应小节。对话里的自驾不要读「两种画法」和「#trip-geo」。
自驾疲劳见 [planning.md](planning.md)。HTML 章节结构见 [html-guide.md](html-guide.md)。天气与飞机 / 高铁 / 火车票价见 [live-data.md](live-data.md)。
本 skill 只做中国大陆及港澳台自驾；境外不排自驾路线，也不接境外驾车地图。

## 对话里的自驾

不要网页时只写这些：高速名、公里、小时、缓冲夜、停靠表、主要地点的高德搜索链接。不要接 AMap JS，不要复制 HTML 壳子。

## HTML 模式

复制壳子前先定 `htmlMode`、`mapRenderer`、`linkProvider`、`coordinateSystem`，写入 `#trip-geo`：

| htmlMode | 何时 | 地图做什么 | lineMode | 不要出现 |
|---|---|---|---|---|
| `self_drive` | 这次主要是开车 | 私人本地页可加载高德地图；分享版或无凭据时用 SVG 示意图 + 驾车折线 + 停靠/补能 | `route` | — |
| `city_trip` | 一城，电车/步行/出租 | **不要地图界面**；列市内票价（地铁官网票价表，不调高德公交）；正文给搜索链接 | 默认 `none` | `#map`、高德地图脚本、Driving、驾车全程、补能、服务区 |
| `multi_city_transit` | 多城，飞机/高铁/火车 | **不要地图界面**；列飞机 / 高铁 / 火车价格（12306 / 航司） | 默认 `none` | 把城际画成驾车导航；`#map` |
| `mixed` | 大交通 + 市内/某段自驾混合 | 有自驾段才画地图；飞机 / 高铁 / 火车只列表、不加载地图 | 每个视图按段定 | 把非自驾段画成驾车 |

`#trip-geo` 写三元组代替旧的 `mapProvider`：

- `mapRenderer`：`amap`（境内私人本地页且有 JS 凭据）或 `svg`（境内分享版、缺凭据及一切境外；只用路线示意图，不接地图 JS）
- `linkProvider`：`amap`（境内）或 `google`（境外，Google Maps search 链接）；决定正文链接、按钮和状态文案用哪家
- `coordinateSystem`：境内 `gcj02`，境外 `wgs84`

**要不要地图界面（`needs_map_ui`）**：`htmlMode` 是 `self_drive`，或 `mixed` 且存在 `drive:true` 且 `lineMode:route` 的视图。只有这时才保留 `#map`；只有 `mapRenderer=amap` 时才加载 `webapi.amap.com`。否则删掉 `#map` 和导航「路线图」；写交通的行程用 `#transit` 展示已核实票价或官方查询入口。points / views 可空，不为画图查无关坐标，也不用 jsKey 调高德 Web 服务。

非自驾默认不连线。境外不接 AMap，也不接 Google Maps JS API（不引入 Key / 计费 / 配额），更不排境外自驾。

## 每天路线卡片

自驾日写出发地 → 高速名 → 到达地、公里 / 时长量级、建议出发时刻、相关路况提醒及「当天导航」。长途再安排适量停靠；只有本次行程确需地图界面时提供「当天地图」。超过约 5 小时标明「转运日」。

用户说了车型 / 能源再写：酒店停车限高、有无桩、加油或充电。没说不要编车高。

非自驾日：步行/地铁分钟数 + 地图搜索，不要「当天驾车导航」。

## 停靠点表

仅自驾。非自驾 HTML 整节隐藏。

| 列 | 写什么 |
|---|---|
| 路段 | 出发城 → 过夜城 |
| 停靠 | 真名字 |
| 类型 | 服务区 / 加油 / 充电 / 停车 / 拍照 / 用餐 / 酒店 |
| 建议停留 | 15–20 分钟 / 午餐 1 小时 |
| 油或电 | 用户说了能源才写 |
| 备注 | 限高、节假日排队、是否公共观景台 |
| 地图 | 高德搜索或 marker |

怎么选：车程 ≥ 2 小时至少一个厕所/服务区；≥ 4 小时考虑加油；拍照点必须是公共地点；每段 1–3 个停靠。HTML 里过滤芯片用 `data-kind`（含 `fuel` / `charge` / `park`）。

## 两种画法（仅 HTML）

用户要 HTML / 可预览 / 可点击，且本次含自驾路线时才画路线。

**有 Key（包外配置或兼容 `local-keys.json` 中 `jsKey` 和 `securityJsCode` 都已填，且 `needs_map_ui` 为真、私人本地页 `mapRenderer=amap`）：**

- 私人本地页可接 **AMap JS API 2.0**。钥匙从配置文件读，不要等聊天里再贴，也不要把 key 打到对话里。自驾：全程折线、每天折线、停靠 / 酒店 / 景点标记。`mixed` 只有 `lineMode=route` 且 `drive: true` 的自驾视图用 Driving，其余段不画成驾车。分享版即使本地有 Key 也走 SVG。
- Key 和安全密钥都非空、都不是 `{{` 占位，才加载 AMap；缺一就走路线示意图。
- `window._AMapSecurityConfig.securityJsCode` **必须写在** `https://webapi.amap.com/maps?v=2.0&key=` **之前**，否则鉴权失败。
- 同步加载示例（即壳子 `{{AMAP_LOADER}}` 注释块的替换结果；插件必须在生成时按模式定好）：

```html
<script>
window._AMapSecurityConfig = { securityJsCode: "用户的安全密钥" };
</script>
<script src="https://webapi.amap.com/maps?v=2.0&key=用户的JS_Key&plugin=AMap.Scale,AMap.ToolBar,AMap.Driving"></script>
```

- 插件：`AMap.Scale,AMap.ToolBar` 必加；`AMap.Driving` 按 **needsDriving** 加载——`htmlMode=self_drive`，或 `mixed` 且存在 `drive: true` 且 `lineMode=route` 的视图；纯 transit 的 `mixed` 不加载。不要用运行时 `document.write` 补载。Driving 返回 `error` / `no_data` 或初始化异常时，降级到 `AMap.Polyline`，状态栏写「驾车规划不可用」，**不要空白图**。
- 页签由 `#trip-geo.views` 生成：有去程才加「去程」，有返程才加「返程」，不要默认两头都留。切换时清覆盖物再画，并 `setFitView`。
- 容器 `#amap-box` 高度约 460–760px。私人本地文件的 JS Key 会暴露给打开文件的人；需要分享时用 SVG，不把解除域名限制当成默认配置。
- 禁止抄旧 HTML、示例或别人的 Key。自驾私人页只把 jsKey + 安全码写进加载脚本；和风 key / 高德 Web 服务 key 不得出现在 HTML 里。交付时说明私人地图凭据随文件可见。
- 壳子里用 `{{AMAP_LOADER}}` 注释块占位：有 Key + 安全密钥就整块替换成上面两行（插件按模式定），没有就整块删除。交出去的文件里不能残留这个占位，也不要去请求空 Key。

**没有 Key（或缺安全密钥）：**

- 用壳子 SVG **路线示意图**（按 `#trip-geo` 经纬度连线）+ 高德 URI 导航。它不是地理底图，没有道路和地形。
- 不要为了画图去编 Key 或抄别人的 Key。

**境外（`mapRenderer=svg`、`linkProvider=google`、`coordinateSystem=wgs84`）：**

- 境外不排自驾；非自驾行程不给地图界面，正文使用 Google Maps search / 官方交通链接。仅在其他确有示意图需求的场景使用壳子 SVG；不加载地图 JS，不申请 Google Key。
- 坐标用 WGS84（Google Maps / 官方页面取值）；拿不到就只写地点名和搜索链接，不要假造坐标。
- 境外不排自驾，也不给境外 `/dir` 驾车导航。

自驾还要：每天一条真实高德 URI、停靠表。飞机 / 高铁 / 火车行程不要为了标记点去画地图，搜索链接写在正文和价格表即可。

地图画在深色舞台上；AMap 用浅色底（`whitesmoke`）以便看清折线。中心点必须来自这次 `#trip-geo`，不要沿用壳子样例坐标。

## 禁止

- 抄用户旧文件里的上兆 SPA、酒店图床、别人的 Key
- 编造精确到门口的坐标，或把片区中心说成酒店大门
- 交出去的文件里还留着「出发地 / 过夜城 / 终点」样例点名，或 `{{占位}}`
- 非自驾还保留 `#map`、驾车全程按钮、补能表，或加载 `webapi.amap.com`

## 坐标怎么查

- 中国用高德（GCJ-02）。来源：高德搜索页、景区官网、百科。写进出处，带查询日期。
- 境外用 WGS-84（Google Maps / 官方页面）。境外行程 `mapRenderer=svg`，但非自驾无需地图界面；确需坐标时精度要求同境内，查不到就只给搜索链接。
- 城市过夜点：保留 2 位小数就够。酒店 / 景区尽量 3–4 位。
- 查不到精确点：用片区中心，备注写「片区中心，不是门口」。
- **无地图时 `points` / `views` 可空**。一旦写进 `points`，`lon` / `lat` 都要有，且 lon ∈ −180~180、lat ∈ −90~90。查不到坐标的点只写正文表格，不要放进 `points`（进场的无坐标点会让示意图算出 NaN）。
- Driving 失败时按上节降级，不要猜测失败原因，也不要假装调用了路径规划 API。

## `#trip-geo` 数据

复制 [assets/guide-shell.html](../assets/guide-shell.html) 后，**整段替换** `#trip-geo` 的 JSON。成品里必须是这一次的真地名。

`views[].path` 只负责连线。`views[].markers` 负责要显示的点。不要让 path 同时承担两件事。没有 `markers` 时，壳子在全程页会显示全部有坐标的点。

```json
{
  "version": "1.4",
  "tripId": "hangzhou-202609",
  "htmlMode": "self_drive",
  "mapRenderer": "amap",
  "linkProvider": "amap",
  "coordinateSystem": "gcj02",
  "defaultView": "full",
  "fullNav": "https://uri.amap.com/navigation?from=经度,纬度,出发城&to=经度,纬度,终点&via=经度,纬度,途经1;经度,纬度,途经2&mode=car&policy=1&src=mypage&coordinate=gaode&callnative=0",
  "transport": {
    "default": "self_drive",
    "legs": [
      {"from": "start", "to": "stay1", "mode": "self_drive"}
    ]
  },
  "views": [
    {"id": "full", "label": "全程", "lineMode": "route", "path": ["start", "stay1", "end"], "markers": ["start", "stay1", "end", "hotel1", "spot1"]},
    {"id": "go", "label": "去程", "lineMode": "route", "path": ["start", "stay1"]},
    {"id": "d1", "label": "D1", "day": 1, "lineMode": "route", "path": ["start", "stay1"], "markers": ["start", "stay1", "spot1"], "nav": "https://uri.amap.com/navigation?from=…&to=…&mode=car&…"},
    {"id": "back", "label": "返程", "lineMode": "route", "path": ["stay1", "end"]}
  ],
  "points": [
    {"id": "start", "name": "出发城", "lon": 120.00, "lat": 31.00, "kind": "start"},
    {"id": "stay1", "name": "过夜城", "lon": 121.00, "lat": 30.00, "kind": "stay", "day": 1},
    {"id": "end", "name": "终点", "lon": 120.00, "lat": 31.00, "kind": "end"}
  ],
  "legs": [
    {"from": "start", "to": "stay1", "day": 1, "label": "D1 高速名 · 约 Xh"}
  ]
}
```

字段：

- `version`：数据结构版本，当前 `1.4`；用 `mapRenderer` + `linkProvider` 代替旧版的 `mapProvider`
- `tripId`：稳定短 id；localStorage 键必须带上它，避免同名文件换行程后残留旧勾选
- `htmlMode`：`self_drive` / `city_trip` / `multi_city_transit` / `mixed`
- `mapRenderer`：`amap`（境内私人本地页接 AMap JS）或 `svg`（境内分享版/缺凭据与一切境外，路线示意图）
- `linkProvider`：`amap` / `google`；按钮与状态文案按它生成
- `coordinateSystem`：`gcj02`（境内）/ `wgs84`（境外）
- `weather`：可选。只有实际写天气节时才加入，例如 `{"asOf":"YYYY-MM-DD","source":"qweather","mode":"forecast","places":["杭州"]}`；其日期和来源须与正文一致
- `defaultView`：可选。首屏显示哪个页签，取值必须是某个 `views[].id`；不写则用 `views[0]`。页签顺序和默认页解耦，别再靠「第一个必须是全程」
- `fullNav`：**`self_drive` 必须有**，且必须是 `https://uri.amap.com/navigation?` 并含 `from=`、`to=`、`mode=car`（没有合格 URI，页面的「打开全程导航」按钮就是没用的空壳，壳子会把它藏掉）；`city_trip` / `multi_city_transit` / `mixed` 不存在「全程驾车」，不要写。随便写一个非空字符串不算数
- `transport.default`：`self_drive` / `transit` / `mixed`（`self_drive` 行程必须是 `self_drive`，`city_trip` / `multi_city_transit` 不能是 `self_drive`）
- `transport.legs[].mode`：`self_drive` / `train` / `flight` / `bus` / `ferry` / `metro` / `taxi` / `rideshare` / `walk` / `bike` / `other`
- `kind`：`start` / `stay` / `end` / `hotel` / `spot` / `food` / `service` / `fuel` / `charge` / `park` / `photo`
- `views[].path`：连线顺序；只给 `lineMode=route` 的视图用。**`lineMode=route` 时至少 2 个有效 point ID**（空数组或只有 1 个点会画出没有路线的路线页，校验器直接 FAIL）
- `views[].lineMode`：`route` 才连线；`none` 只显示标记，缺省时非自驾为 `none`、自驾为 `route`
- **同一页签的 id 不能重复**（壳子按 id 取第一个，重复会静默覆盖）；**`points[].id` 也不能重复**
- `views[].drive`：仅 `mixed` 用；`true` 表示该视图是纯自驾段，可用 Driving 并按驾车画。**`drive: true` 必须同时是 `lineMode: "route"`**，两者不一致会既不加载 Driving 也不显示停靠。非自驾视图不要标；混合行程里非自驾段画**虚线**示意（SVG 与 AMap 两边一致）
- `views[].nav`：本段链接。`mixed` 的自驾段必备（全程没有 fullNav），必须是高德驾车 URI（`from` / `to` / `mode=car`），不能是普通搜索链接或随意字符串；`self_drive` 可选，缺省用 `fullNav`。自驾段按钮写「导航」；非自驾段给的通常是搜索 / 地点页，按钮文案写成「查看地点」——壳子按 `drive` 自动区分，别把搜索链接写成导航
- `views[].markers`：该页签要显示的点 id；可省略
- `legs` 只连过夜或当天主终点
- 停靠点进 `points`；没有坐标就只写表，不要假造点
- **点要铺到整条路线**：酒店（含过夜点）、每天主景点、点名服务区 / 充电站有坐标就进 `points`，不要只放城市中心。只放城市中心会让地图看起来空、也看不出当天怎么走
- 没有返程就把 `back` 从 `views` 删掉；没有单独去程就删 `go`

页面按钮和状态文案按 `linkProvider` 生成：`amap` 用「在高德打开全程」和「路况以高德导航为准」，`google` 用 Google Maps 文案；不要把供应商文案写死成另一家。页头导航提示也按 `htmlMode` 走：`city_trip`「市内以步行 / 地铁 / 公交为主」，`multi_city_transit`「车次 / 航班以官方页面为准」，`mixed` 不放统一导航提示。

## 高德链接（不用 Key 也要有）

中国大陆：

- 搜索：`https://www.amap.com/search?query={URL编码的地名}`
- 打开 App/网页搜：`https://uri.amap.com/search?keyword={URL编码}&src=mypage`
- 标记点：`https://uri.amap.com/marker?position={lon},{lat}&name={名称}&src=mypage&coordinate=gaode&callnative=0`
- 驾车导航：`https://uri.amap.com/navigation?from={lon},{lat},{名}&to={lon},{lat},{名}&via={lon},{lat},{名}&mode=car&policy=1&src=mypage&coordinate=gaode&callnative=0`
- 步行：同上，`mode=walk`

`via` 多个途经用英文分号连接，最多 16 个。按钮文字用地名。

境外非自驾可用 `https://www.google.com/maps/search/{URL编码}`；不要给境外驾车 `/dir` 导航。
