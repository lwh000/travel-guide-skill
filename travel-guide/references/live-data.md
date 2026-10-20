---
name: travel-guide-live-data
description: travel-guide 内部参考文档，不单独作为技能导入。
---

# 天气与城际票价

只有行程涉及天气、城际票价或境内自驾地图时读。配置可由 `TRAVEL_GUIDE_KEYS_FILE` 指向包外文件；未设置时读取根目录 `local-keys.json`，格式见 `local-keys.example.json`。私用安装包可在根目录自带此配置。聊天里不要打印 key，HTML 里不要出现和风 key。

私人本地自驾页可将高德 JS Key 和安全码写进 `{{AMAP_LOADER}}` 以加载地图；它们会对打开 HTML 的人可见。准备分享或公开发布 HTML 时改用 SVG 路线图 + 导航链接，不嵌入个人地图凭据。jsKey 不用于 `restapi.amap.com`，也不顶 Web 服务 key。

## 每次先看钥匙在不在

```
python scripts/live_data.py status
```

只显示「已填 / 空」，不会把 key 打出来。

脚本单次网络请求超时为 8 秒；它只做短链路 fallback，失败就尽快返回，**不要让天气查询拖住整份攻略**。

| 字段 | 用途 |
|---|---|
| `amap.jsKey` + `amap.securityJsCode` | 境内自驾 HTML 加载高德真地图。只干这件事 |
| `amap.webKey` | 不用。空着。不要用 jsKey 去填，也不要拿这把地图钥匙查公交 |
| `qweather.key` | 和风天气 API Key；请求时仅放 `X-QW-Api-Key` 请求头，不放 URL query |
| `qweather.host` | 控制台「设置」里的专用 API Host，去掉 `https://`，形如 `xxxx.xx.qweatherapi.com`。`credentialId` 不是 Host，不得互填；Host 空着就不要调和风 |

没有可用专用 Host 时脚本会跳过和风，改走公开气象来源，不让天气查询卡住整份攻略。

缺哪把钥匙，对应能力降级，**不要卡住整份攻略**。

## 什么时候写天气

有目的地、可用日期且天气影响户外安排或交通时，给独立天气节。只问酒店、餐厅、打包，或尚未确定日期时不强加天气。只有拿到与地点和日期匹配、可注明来源的预报或历史气候数据，才写数字气温；没有可靠数字就给官方查询入口，说明需在出发前再核。

**天气独立执行，不阻塞主流程。** 天气研究和攻略研究是两条线：

- 天气获取失败不得触发整份攻略重研。
- **天气不影响行程结构时，不为天气反复搜索。**只有台风、暴雨、停航、封路等会改变安排的事件才作为硬缺口处理，见 research-playbook.md。
- 脚本返回的 `coverage.matchedDates` / `coverage.missingDates` 要与正文逐日对齐；缺失日期不借其他日期的气温补齐。

```
python scripts/live_data.py weather --city 杭州 --start 2026-10-20 --days 3
```

脚本顺序：

1. 和风：仅当 `qweather.key` 和合法 API Host（`*.qweatherapi.com`）都有。先用 GeoAPI v2 查城市经纬度，再用 `/weather/v1/daily/{lat}/{lon}` 查逐日预报（10 → 7 → 3 天按可用档降级），用 `/weatheralert/v1/current/{lat}/{lon}` 查预警；保留返回的 `metadata.attributions` 数据声明。API Key 只走请求头，不在 URL 带 key
2. 中央气象台（优先 HTTPS；有明确连接故障时才尝试 HTTP，并保留来源）
3. 仍失败：`ok: false`，`html` 为空，`mustSearch: true`，并给出中央气象台 / 中国天气网页面。不要走 Open-Meteo

HTML 的 `{{WEATHER}}`：

- 返回里已有与出行日期相符、带来源和查询日期的 `.wx-card`：使用对应日期的 `html`
- `coverage.missingDates` 非空：只展示 `matchedDates` 对应的卡片，逐日注明缺口；缺口会改变安排时再核官方页面
- `mustSearch: true` 或 `html` 为空：按 `open` 的官方页面核查；仍无对应日期或有来源的历史数据，就给官方入口与复核时间，不造 `.wx-card` 或数字

规则：

- 日期在预报窗口内：仅使用与出行日期完全匹配的预报记录；部分覆盖就逐日标明
- 更远：脚本的旧兼容模式 `climate_plus_recent` 实际只有近期预报参考，带 `referenceKind=recent_forecast`、`coverage.referenceDates`；必须写成「近期参考，非出行日预报，也非历史气候」。另有来源的历史气候才可标为「历史气候，非预报」
- 查询日期必带
- 不要把和风 key 写进 HTML 或 `#trip-geo`
- 打开气象台页面计入研究量；不为补足视觉卡片而额外搜无关数据

`#trip-geo` 可选 `weather` 对象（版本 `1.4`）：

```json
"weather": { "asOf": "2026-10-13", "source": "nmc", "mode": "forecast", "places": ["杭州"] }
```

来源按实际：`qweather` / `nmc` / `china-weather`（手工打开中央气象台或中国天气网写成卡片）。不要写 `open-meteo`。留痕格式见 research-playbook.md 的「天气 / 假期 / 时效事实的留痕格式」。

HTML 没有对应日期预报时，可用 `<section id="weather" data-weather-status="unavailable">` 写明缺口、官方查询入口和出发前复核时间；不要放空 `.wx-card`。天气与本次交付无关时删掉整个 `#weather`。

## 飞机 / 高铁 / 火车（无地图时必写）

这里说的是 **飞机 / 高铁 / 火车**，不是市内公交。高德这把钥匙不能查公交，也不要为了画图去查坐标。

`city_trip` / `multi_city_transit` / 没有自驾段的 `mixed`：**不要地图界面**。去查票价，列成表。

```
python scripts/live_data.py transit --from 上海虹桥 --to 杭州东
```

脚本只给检索词和一张占位表，`ok: false`。真正的数字靠网页检索填进去：

- 高铁 / 火车票价以 **12306** 为准
- 机票以航司官网或官方渠道为准
- 一城地铁 / 步行仍无图；市内票价用当地地铁官网票价表，**不要调高德公交**
- 不提供余票、可订座位
- 境外：检索官方交通或 Google，表格仍要有
- 无图模式 `#trip-geo` 的 points / views 可空

多段交通按路段分行：出发站、方式、参考价或「待官网确认」、耗时、来源日期。票价是会改变行程结构的硬事实；预算只是候选研究基线，不让无来源数字进入表格。

## 自驾才加载地图

`needs_map_ui` = `htmlMode` 是 `self_drive`，或 `mixed` 且存在 `drive:true` 且 `lineMode:route` 的视图。

这时才保留 `#map`。私人本地 HTML 可从配置文件填 `{{AMAP_LOADER}}`（先安全码，再 maps 脚本；`needsDriving` 才带 `AMap.Driving`）；缺凭据或计划分享 HTML 就用 SVG 示意图。纯自驾可删 `#transit`；`mixed` 同时有飞机 / 高铁 / 火车段时保留票价表或官方查询入口。境外仍 `mapRenderer=svg`，不接地图 JS，也不排境外自驾。

若交付的私人本地 HTML 内嵌高德 JS Key，明确提示该文件含地图凭据；分享版默认剔除凭据。

细则见 [maps.md](maps.md) 和 [html-guide.md](html-guide.md)。
