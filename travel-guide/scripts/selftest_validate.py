#!/usr/bin/env python3
"""validate_html.py 的自查用例。

每个用例是一段合成 HTML + 期望退出码（0 通过 / 1 应被拦下）。
改 validate_html.py 之后跑一次，确认没有误报 / 漏报：

    python scripts/selftest_validate.py

退出码 0 = 全部符合预期。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
VALIDATOR = HERE / "validate_html.py"
SKILL_ROOT = HERE.parent


def needs_map_ui(geo: dict) -> bool:
    mode = geo.get("htmlMode")
    if mode == "self_drive":
        return True
    if mode == "mixed":
        for v in geo.get("views") or []:
            if isinstance(v, dict) and v.get("drive") is True and v.get("lineMode") == "route":
                return True
    return False


WX_SAMPLE = (
    '<p>天气查询日期 2026-09-18；来源：中央气象台。</p>'
    '<div class="wx-grid">'
    '<div class="wx-card"><span class="wx-date">2026-09-20</span>'
    "<b>24–18°C</b><span>多云</span></div></div>"
)
SOURCES_SAMPLE = '<section id="sources"><h2>出处</h2><p>来源：景区官网（查询 2026-09-18）</p></section>'
FARE_SAMPLE = (
    '<div class="table-wrap"><table>'
    "<thead><tr><th>路段</th><th>方式</th><th>参考价</th></tr></thead>"
    "<tbody><tr><td>上海 → 杭州</td><td>高铁</td><td>73 元</td></tr></tbody>"
    "</table></div>"
)


def make(geo: dict, head: str = "", stops: bool = False, extra: str = "",
         shell_based: bool = False, weather: bool = True,
         include_map=None, include_transit=None,
         weather_html=None, transit_html=None) -> str:
    """构造测试用 HTML。

    shell_based=True 时基于真实 assets/guide-shell.html 生成，
    用来覆盖“壳子自带 JS 里有 AMap / 各家文案”这类只有在真实文件上才暴露的误判。
    """
    map_ui = needs_map_ui(geo) if include_map is None else include_map
    transit_ui = (not map_ui) if include_transit is None else include_transit
    wx_inner = WX_SAMPLE if weather_html is None else weather_html
    tr_inner = FARE_SAMPLE if transit_html is None else transit_html

    if shell_based:
        shell = (SKILL_ROOT / "assets" / "guide-shell.html").read_text(encoding="utf-8")
        h = re.sub(r"<!--\s*\{\{AMAP_LOADER\}\}.*?-->", "", shell, flags=re.S)
        if not stops:
            h = re.sub(r'<section id="stops".*?</section>\s*(<!--.*?-->\s*)?', "", h, flags=re.S)
        if not map_ui:
            h = re.sub(r'<section id="map".*?</section>\s*', "", h, flags=re.S)
            h = re.sub(r'<a href="#map">.*?</a>\s*', "", h)
        if not transit_ui:
            h = re.sub(r'<section id="transit".*?</section>\s*', "", h, flags=re.S)
            h = re.sub(r'<a href="#transit">.*?</a>\s*', "", h)
        if not weather:
            h = re.sub(r'<section id="weather".*?</section>\s*', "", h, flags=re.S)
            h = re.sub(r'<a href="#weather">.*?</a>\s*', "", h)
        if weather:
            h = h.replace("{{WEATHER}}", wx_inner)
        h = h.replace("{{SOURCES}}", "来源：景区官网（查询 2026-09-18）")
        if transit_ui:
            h = h.replace("{{TRANSIT_FARES}}", tr_inner)
        h = re.sub(r"\{\{[A-Z_]+\}\}", "示例", h)
        if head:
            h = h.replace("</head>", head + "</head>")
        h = re.sub(
            r'(<script type="application/json" id="trip-geo">).*?(</script>)',
            lambda m: m.group(1) + json.dumps(geo, ensure_ascii=False) + m.group(2),
            h, flags=re.S,
        )
        if extra:
            h = h.replace("</main>", extra + "</main>")
        return h

    stops_html = ""
    if stops:
        stops_html = (
            '<section id="stops" data-drive-only><div id="stop-filters">'
            '<button data-stop-filter="all">全部</button>'
            '<button data-stop-filter="food">吃饭</button></div>'
            '<table><tr data-kind="service"><td>嘉兴服务区</td></tr></table></section>'
        )
    wx = f'<section id="weather"><h2>天气</h2>{wx_inner}</section>' if weather else ""
    tr = f'<section id="transit"><h2>交通票价</h2>{tr_inner}</section>' if transit_ui else ""
    mp = (
        '<section id="map"><div id="amap-box"></div>'
        '<svg id="route-canvas" role="img" aria-label="路线"></svg></section>'
    ) if map_ui else ""
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        f"<title>自测</title>{head}</head><body><header><h1>测试行程</h1></header><main>"
        f"{wx}{mp}{tr}{stops_html}{extra}{SOURCES_SAMPLE}</main>"
        f'<script type="application/json" id="trip-geo">{json.dumps(geo, ensure_ascii=False)}</script>'
        '<script>var d=JSON.parse(document.getElementById("trip-geo").textContent);</script>'
        "</body></html>"
    )
KEY = ('<script>window._AMapSecurityConfig = { securityJsCode: "x" };</script>'
       '<script src="https://webapi.amap.com/maps?v=2.0&key=k'
       '&plugin=AMap.Scale,AMap.ToolBar,AMap.Driving"></script>')
NOKEY = ('<script>window._AMapSecurityConfig = { securityJsCode: "x" };</script>'
         '<script src="https://webapi.amap.com/maps?v=2.0&key=k'
         '&plugin=AMap.Scale,AMap.ToolBar"></script>')


def geo(mode, renderer, provider, coords, views, *, full=False, points=None,
        transport=None, default_view=None, legs=None):
    pts = points if points is not None else [
        {"id": "start", "name": "上海", "lon": 121.47, "lat": 31.23, "kind": "start"},
        {"id": "h1", "name": "杭州西湖", "lon": 120.15, "lat": 30.25, "kind": "hotel"},
        {"id": "end", "name": "上海", "lon": 121.47, "lat": 31.23, "kind": "end"},
    ]
    d = {
        "version": "1.4", "tripId": "selftest", "htmlMode": mode,
        "mapRenderer": renderer, "linkProvider": provider,
        "coordinateSystem": coords, "points": pts, "views": views,
        "legs": legs if legs is not None else [{"from": "start", "to": "h1", "day": 1, "label": "D1"}],
    }
    if transport is not None:
        d["transport"] = transport
    if default_view is not None:
        d["defaultView"] = default_view
    if full:
        d["fullNav"] = ("https://uri.amap.com/navigation?from=121.47,31.23,上海"
                        "&to=120.15,30.25,杭州&mode=car&policy=1&src=mypage"
                        "&coordinate=gaode&callnative=0")
    return d


DRIVE_VIEWS = [{"id": "full", "label": "全程", "lineMode": "route",
                "path": ["start", "h1", "end"], "markers": ["start", "h1"]}]
CITY_VIEWS = [{"id": "d1", "label": "D1", "lineMode": "none", "markers": ["h1"]}]
NAV_URL = ("https://uri.amap.com/navigation?from=121.47,31.23,上海"
           "&to=120.15,30.25,杭州&mode=car&policy=1&src=mypage"
           "&coordinate=gaode&callnative=0")


def build() -> list[tuple]:
    cases: list[tuple] = []

    def add(name, content, want, bom=False, warn=None, fail=None, absent=None):
        """warn/fail = 必须出现的诊断；absent = 不应出现的诊断。"""
        cases.append((name, content, want, bom, warn, fail, absent))

    # ── 应当通过 ──
    g_drive = geo("self_drive", "amap", "amap", "gcj02", DRIVE_VIEWS, full=True,
                  transport={"default": "self_drive",
                             "legs": [{"from": "start", "to": "h1", "mode": "self_drive"}]},
                  default_view="full")
    add("self_drive + Key", make(g_drive, KEY, stops=True), 0)
    add("self_drive 无 Key（SVG 降级）", make(g_drive, "", stops=True), 0)

    g_city = geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                 transport={"default": "transit",
                            "legs": [{"from": "start", "to": "h1", "mode": "metro"}]},
                 default_view="d1")
    add("city_trip 无 Key", make(g_city), 0)

    g_intl = geo(
        "city_trip", "svg", "google", "wgs84",
        [{"id": "full", "label": "全程", "lineMode": "none", "markers": ["a", "b"]}],
        points=[{"id": "a", "name": "浅草寺", "lon": 139.79, "lat": 35.71, "kind": "spot"},
                {"id": "b", "name": "明治神宫", "lon": 139.70, "lat": 35.67, "kind": "spot"}],
        transport={"default": "transit", "legs": [{"from": "a", "to": "b", "mode": "train"}]},
        default_view="full",
        legs=[{"from": "a", "to": "b", "day": 1, "label": "电车"}],
    )
    add("境外 svg + google", make(g_intl), 0)
    add("境外 svg + 真实壳子（防误判）", make(g_intl, shell_based=True), 0)

    g_mixed = geo(
        "mixed", "amap", "amap", "gcj02",
        [{"id": "d1", "label": "D1", "lineMode": "route", "drive": True,
          "path": ["start", "h1"], "nav": NAV_URL},
         {"id": "d2", "label": "D2", "lineMode": "none", "markers": ["h1"]}],
        transport={"default": "mixed",
                   "legs": [{"from": "start", "to": "h1", "mode": "self_drive"}]},
        default_view="d1",
    )
    add("mixed 自驾段 + nav", make(g_mixed, KEY, stops=True), 0)

    g_mixed_transit = geo(
        "mixed", "amap", "amap", "gcj02",
        [{"id": "d1", "label": "D1", "lineMode": "none", "markers": ["h1"]}],
        transport={"default": "transit",
                   "legs": [{"from": "start", "to": "h1", "mode": "train"}]},
        default_view="d1",
    )
    add("mixed 无自驾段（无地图）", make(g_mixed_transit), 0)

    add("city 空 points（无地图可空）",
        make(geo("city_trip", "amap", "amap", "gcj02", [],
                 points=[], legs=[],
                 transport={"default": "transit"})), 0)

    # ── 应当拦下 ──
    bad = geo("city_trip", "amap", "amap", "gcj02",
              [{"id": "d1", "label": "D1", "lineMode": "none", "markers": ["abc"]}])
    add("markers 引用不存在的点", make(bad), 1)

    add("city_trip 带 fullNav",
        make(geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS, full=True)), 1)
    add("境外却接 AMap", make(g_intl, KEY), 1)
    add("需要 Driving 但插件漏了", make(g_drive, NOKEY, stops=True), 1)

    wrong_order = ('<script src="https://webapi.amap.com/maps?v=2.0&key=k'
                   '&plugin=AMap.Scale,AMap.ToolBar,AMap.Driving"></script>'
                   '<script>window._AMapSecurityConfig = { securityJsCode: "x" };</script>')
    add("安全密钥写在 maps 之后", make(g_drive, wrong_order, stops=True), 1)
    add("残留占位符", make(g_intl).replace("</main>", "{{EAT}}</main>"), 1)
    add("带 BOM", make(g_intl), 1, True)
    add("img 缺 alt",
        make(g_city).replace("</main>", '<img src="https://upload.wikimedia.org/a.jpg"></main>'), 1)

    g_mixed_nav = geo("mixed", "amap", "amap", "gcj02",
                      [{"id": "d1", "label": "D1", "lineMode": "route",
                        "drive": True, "path": ["start", "h1"]}])
    add("mixed 自驾段缺 nav", make(g_mixed_nav, KEY, stops=True), 1)

    add("route path 为空",
        make(geo("self_drive", "amap", "amap", "gcj02",
                 [{"id": "full", "label": "全程", "lineMode": "route",
                   "path": [], "markers": ["start", "h1"]}],
                 full=True), KEY, stops=True), 1)
    add("route path 只有 1 个点",
        make(geo("self_drive", "amap", "amap", "gcj02",
                 [{"id": "full", "label": "全程", "lineMode": "route",
                   "path": ["start"], "markers": ["start", "h1"]}],
                 full=True), KEY, stops=True), 1)
    g_hello_nav = geo("self_drive", "amap", "amap", "gcj02", DRIVE_VIEWS, full=True)
    g_hello_nav["fullNav"] = "hello"
    add("fullNav=hello", make(g_hello_nav, KEY, stops=True), 1)
    g_mixed_hello = geo("mixed", "amap", "amap", "gcj02",
                        [{"id": "d1", "label": "D1", "lineMode": "route",
                          "drive": True, "path": ["start", "h1"], "nav": "hello"}])
    add("mixed nav=hello", make(g_mixed_hello, KEY, stops=True), 1)

    dup_point = geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                    points=[{"id": "a", "name": "A", "lon": 120.1, "lat": 30.1, "kind": "spot"},
                            {"id": "a", "name": "A2", "lon": 120.2, "lat": 30.2, "kind": "spot"},
                            {"id": "h1", "name": "H", "lon": 120.15, "lat": 30.25, "kind": "hotel"}])
    add("31 重复 point ID", make(dup_point), 1)

    dup_view = geo("city_trip", "amap", "amap", "gcj02",
                   [{"id": "d1", "label": "D1", "lineMode": "none", "markers": ["h1"]},
                    {"id": "d1", "label": "D1 再来一次", "lineMode": "none", "markers": ["h1"]}])
    add("32 重复 view ID", make(dup_view), 1)

    no_coord = geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                   points=[{"id": "start", "name": "上海", "lon": 121.47, "lat": 31.23, "kind": "start"},
                           {"id": "b", "name": "B", "kind": "spot"},
                           {"id": "h1", "name": "H", "lon": 120.15, "lat": 30.25, "kind": "hotel"}])
    add("33 point 缺 lon/lat", make(no_coord), 1)

    bad_mixed = geo("mixed", "amap", "amap", "gcj02",
                    [{"id": "d1", "label": "D1", "lineMode": "none",
                      "drive": True, "path": ["start", "h1"]}])
    add("34 mixed drive=true + lineMode=none", make(bad_mixed, KEY, stops=True), 1)

    add("35 self_drive 缺 fullNav",
        make(geo("self_drive", "amap", "amap", "gcj02", DRIVE_VIEWS), "", stops=True), 1)

    svg_js = (SKILL_ROOT / "assets" / "guide-shell.html").read_text(encoding="utf-8")
    if 'const dashed = isMixed && !canDrive(view);' not in svg_js:
        cases.append(("36 壳子 SVG 缺少虚线逻辑", "<html></html>", 999, False, None, None, None))
    else:
        add("36 壳子 SVG mixed 虚线逻辑在位", make(g_intl, shell_based=True), 0)

    add("非法坐标（越界）",
        make(geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                 points=[{"id": "start", "name": "上海", "lon": 999, "lat": 31.23, "kind": "start"},
                         {"id": "h1", "name": "H", "lon": 120.15, "lat": 30.25, "kind": "hotel"}])), 1)

    add("defaultView 不存在",
        make(geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                 default_view="nope")), 1)

    add("transport.default 非法值",
        make(geo("city_trip", "amap", "amap", "gcj02", CITY_VIEWS,
                 transport={"default": "banana"})), 1)

    add("专题页可省天气节", make(g_city, weather=False), 0,
        absent="缺 #weather 天气节")
    add("无自驾行程带地图界面", make(g_city, include_map=True), 1)
    add("自驾缺地图节", make(g_drive, include_map=False, stops=True), 1)
    add("无地图缺票价节", make(g_city, include_transit=False), 1)
    add("天气只留标题", make(g_city, weather_html=""), 1)
    add("天气只有空说明", make(g_city, weather_html=(
        '<p class="muted">查询 。出行日在约 10 天内用预报；更远则气候规律 + 近期参考。</p>'
    )), 1)
    add("票价无 table", make(g_city, transit_html="<p>示例票价说明</p>"), 1)
    add("天气和风失败但有气候数字", make(g_city, weather_html=(
        '<div class="callout">查询 2026-09-18；来源：中国天气网。'
        '和风暂不可用。9月气候约 22–28°C，多云为主，出发前再核。</div>'
    )), 0)
    add("只有失败说明无气温", make(g_city, weather_html=(
        '<div class="callout">和风暂不可用。按气候规律填写，并写出发前再核。</div>'
    )), 1)
    official_link = '<a href="https://www.nmc.cn/publish/forecast.html">中央气象台官方查询</a>'
    unavailable_html = ('<p>查询 2026-09-18；中央气象台尚未发布出行日预报，'
                        '暂无可核实气温，请出发前一周再核。' + official_link + '</p>')
    add("明确无数据天气状态", make(g_city, weather_html=unavailable_html).replace(
        '<section id="weather">', '<section id="weather" data-weather-status="unavailable">'), 0)
    add("无数据状态缺复核提醒", make(g_city, weather_html='<p>暂无气温。' + official_link + '</p>').replace(
        '<section id="weather">', '<section id="weather" data-weather-status="unavailable">'), 1,
        fail="须写明出行前复查")
    add("无数据状态缺官方入口", make(g_city, weather_html=(
        '<p>查询 2026-09-18；中央气象台尚未发布出行日预报，暂无可靠气温，请出发前再核。</p>'
    )).replace('<section id="weather">',
               '<section id="weather" data-weather-status="unavailable">'), 1,
        fail="缺可点击的官方天气查询入口")

    # Targeted regressions: assert the decisive diagnostic, not merely exit 1.
    add("空天气卡", make(g_city, weather_html=(
        '<p>查询 2026-09-18；来源：中央气象台。</p><div class="wx-card"></div>'
    )), 1, fail="缺有效气温单位")
    add("日期区间不算气温", make(g_city, weather_html=(
        '<p>查询 2026-09-18；来源：中央气象台。9月20日至9月22日天气待核。</p>'
    )), 1, fail="不能把日期范围当气温")
    add("天气缺查询日期", make(g_city, weather_html=(
        '<p>来源：中央气象台。天气 22–28°C。</p>'
    )), 1, fail="缺有效查询日期")
    add("天气缺来源", make(g_city, weather_html=(
        '<p>查询 2026-09-18。天气 22–28°C。</p>'
    )), 1, fail="缺可见来源")
    g_weather = dict(g_city, weather={"asOf": "2026-09-17", "source": "nmc",
                                      "mode": "forecast", "places": ["杭州"]})
    add("天气元数据查询日期与正文冲突", make(g_weather), 1,
        fail="weather.asOf 与天气节查询日期不一致")
    add("天气元数据来源与正文冲突", make(dict(g_city, weather={
        "asOf": "2026-09-18", "source": "qweather", "mode": "forecast", "places": ["杭州"]
    })), 1, fail="weather.source 与天气节可见来源不一致")
    add("天气元数据非法类型", make(dict(g_city, weather={
        "asOf": "2026-09-18", "source": ["nmc"], "mode": ["forecast"], "places": ["杭州"]
    })), 1, fail="weather.source 应为")
    article = ('<section id="days"><article class="day"><div class="day-head">'
               '<span class="day-date">2026年9月27日</span>'
               '<span class="day-week">周一</span></div></article></section>')
    add("逐日卡片星期错误", make(g_city, extra=article), 1, fail="实际周日")
    article_ok = article.replace("周一", "周日")
    add("逐日卡片星期正确", make(g_city, extra=article_ok,
        weather_html=WX_SAMPLE.replace("2026-09-20", "2026-09-27")), 0)
    add("天气预报日期与行程错位", make(g_city, extra=article_ok), 1,
        fail="预报卡日期 2026-09-20 不在逐日行程日期内")
    add("其它气候文字不得掩盖错日预报", make(g_city, extra=article_ok,
        weather_html=WX_SAMPLE + '<p>长期气候规律仅供衣物准备。</p>'), 1,
        fail="预报卡日期 2026-09-20 不在逐日行程日期内")
    table_bad = ('<section id="schedule"><table><tr><th>日期</th><th>星期</th></tr>'
                 '<tr><td>2026年9月27日</td><td>周一</td></tr></table></section>')
    add("每日总表星期错误", make(g_city, extra=table_bad), 1, fail="每日总表 2026-09-27")
    add("总表行程与天气预报错位", make(g_city, extra=table_bad.replace("周一", "周日")), 1,
        fail="预报卡日期 2026-09-20 不在逐日行程日期内")
    add("气候近期参考允许不同日期", make(dict(g_city, weather={
        "asOf": "2026-09-18", "source": "nmc", "mode": "climate_plus_recent", "places": ["杭州"]
    }), extra=article_ok, weather_html=WX_SAMPLE + '<p>气候规律 + 近期参考，出发前再核。</p>'), 0)

    add("缺出处节", make(g_city).replace(SOURCES_SAMPLE, ""), 1, fail="缺 #sources 出处节")
    add("空出处节", make(g_city).replace(SOURCES_SAMPLE,
        '<section id="sources"><h2>出处</h2><p>示例</p></section>'), 1,
        fail="出处节没有具体来源")
    add("inline script 残留占位符", make(g_city).replace("</body>",
        '<script>const city="{{CITY}}";</script></body>'), 1,
        fail="还有未替换的占位符")
    add("inline script document.write", make(g_city).replace("</body>",
        '<script>document.write("x")</script></body>'), 1, fail="document.write")
    add("javascript href", make(g_city, extra='<a href="javascript:alert(1)">点击</a>'), 1,
        fail="不安全 href")
    add("img data-alt 不算 alt", make(g_city, extra='<img src="a.jpg" data-alt="风景">'), 1,
        fail="data-alt 不能代替 alt")
    add("无地图行程加载 AMap", make(g_city,
        '<script src="https://webapi.amap.com/maps?v=2.0&amp;key=k"></script>'), 1,
        fail="无地图行程不该加载高德地图脚本")
    g_hotel_only = geo("city_trip", "amap", "amap", "gcj02", [], points=[], legs=[])
    add("酒店专题页无天气或交通价", make(g_hotel_only, weather=False,
        include_transit=False), 0, absent="杂志版容易显得空")
    add("境内自驾静态 SVG + 高德链接", make(dict(g_drive, mapRenderer="svg"),
        stops=True), 0)
    g_mixed_train = geo("mixed", "amap", "amap", "gcj02",
        [{"id": "d1", "label": "D1", "lineMode": "route", "drive": True,
          "path": ["start", "h1"], "nav": NAV_URL}],
        transport={"default": "mixed", "legs": [
            {"from": "start", "to": "h1", "mode": "self_drive"},
            {"from": "h1", "to": "end", "mode": "train"}]})
    add("mixed 自驾加高铁缺票价表", make(g_mixed_train, KEY, stops=True), 1,
        fail="mixed 含城际大交通时必须保留 #transit 票价表")
    add("mixed 自驾加高铁含票价表", make(g_mixed_train, KEY, stops=True,
        include_transit=True), 0)
    add("换行的高德 Web key", make(g_city, extra=(
        '<a href="https://restapi.amap.com/v3/route/driving?origin=1,2\n&amp;key=secret">路书</a>'
    )), 1, fail="高德 Web 服务请求")
    add("换行的和风 key", make(g_city, extra=(
        '<a href="https://abc.qweatherapi.com/v7/weather/3d?location=101\n&amp;key=secret">天气</a>'
    )), 1, fail="和风天气请求")
    for name, bad_nav in (
        ("空 from", NAV_URL.replace("from=121.47,31.23,上海", "from=")),
        ("空 to", NAV_URL.replace("to=120.15,30.25,杭州", "to=")),
        ("mode 子串", NAV_URL.replace("mode=car", "mode=carpool")),
        ("重复 mode", NAV_URL + "&mode=bus"),
        ("from 不是坐标", NAV_URL.replace("from=121.47,31.23,上海", "from=上海")),
        ("from 越界", NAV_URL.replace("from=121.47,31.23,上海", "from=999,31.23,上海")),
    ):
        g_bad_nav = dict(g_drive, fullNav=bad_nav)
        add(f"驾车 URI {name}", make(g_bad_nav, KEY, stops=True), 1,
            fail="fullNav 必须是 https://uri.amap.com/navigation")

    # ── 杂志版提醒（只 WARN，不拦交付）──
    dated_day = ('<section id="days"><article class="day"><div class="day-head">'
                 '<span class="day-date">2026年9月20日</span>'
                 '<span class="day-week">周日</span></div></article></section>')
    add("46 无图也无氛围块", make(g_city, extra=dated_day), 0,
        warn="整页没有 <img> 也没有 .art-fig")
    add("47 每日一个时段也有实际安排",
        make(g_city, extra=(
            '<section id="days"><h2>逐日行程</h2>'
            '<article class="day"><div class="day-copy"><span class="day-no">D1</span>'
            '<div class="slot"><b>上午</b> 地点</div></div></article>'
            '<article class="day"><div class="day-copy"><span class="day-no">D2</span>'
            '<div class="slot"><b>上午</b> 地点</div></div></article></section>'
        )), 0, absent=("逐日卡片缺少实际行程安排", "每天至少上午/下午两段"))
    add("单日自由文字安排无需时段", make(g_city, extra=(
        '<section id="days"><article class="day"><div class="day-head">'
        '<span class="day-no">D1</span><span class="day-date">2026年9月20日</span>'
        '<span class="day-week">周日</span></div>'
        '<p>上午抵达后入住酒店，下午在附近散步。</p></article></section>'
    )), 0, absent="逐日卡片缺少实际行程安排")
    add("只有日期、装饰图和空时段的日卡提醒", make(g_city, extra=(
        '<section id="days"><article class="day">'
        '<div class="art-fig" style="background:linear-gradient(#123,#456)">西湖</div>'
        '<div class="day-copy"><div class="day-head"><span class="day-no">D1</span>'
        '<span class="day-date">2026年9月20日</span><span class="day-week">周日</span>'
        '</div><div class="slot"><b>上午</b></div></div></article></section>'
    )), 0, warn="逐日卡片缺少实际行程安排：D1 内容为空")
    add("48 住宿节只有一句话",
        make(g_city, extra=(dated_day + '<section id="stay"><h2>怎么住</h2><p>住在西湖边。</p></section>')),
        0, warn="住宿节既没有表格也没有 .stay-card")
    add("简版跳过杂志视觉提醒", make(g_city, extra=dated_day).replace(
        '<html lang="zh-CN">', '<html lang="zh-CN" data-guide-style="minimal">'), 0,
        absent="整页没有 <img>")
    add("打印版跳过杂志视觉提醒", make(g_city, extra=dated_day).replace(
        '<html lang="zh-CN">', '<html lang="zh-CN" data-guide-style="print">'), 0,
        absent="页头没有 .hero-bg")
    add("渐变封面无需缺图提醒", make(g_city, extra=(
        '<div class="hero-bg" style="background:linear-gradient(#123,#456)"></div>' + dated_day
    )), 0, absent=("整页没有 <img> 也没有 .art-fig", "页头没有 .hero-bg"))
    add("多 class 单引号渐变封面也有效", make(g_city, extra=(
        "<div class='hero-bg themed' style='background-image:radial-gradient(#123,#456)'></div>"
        + dated_day
    )), 0, absent="页头没有 .hero-bg")
    add("49 有 .art-fig 就不提醒空",
        make(g_city, extra=(
            '<section id="days"><article class="day">'
            '<div class="art-fig" style="background:#12343a">石塘</div>'
            '<div class="day-copy"><div class="slot">上午游览石塘老街</div>'
            '<div class="slot">下午看渔港日落</div></div></article></section>'
        )), 0, absent=("整页没有 <img> 也没有 .art-fig", "逐日卡片缺少实际行程安排"))

    return cases


def test_secret_path_union(tmp: pathlib.Path) -> bool:
    """Synthetic keys only: override and legacy must both be inspected."""
    sys.path.insert(0, str(HERE))
    import validate_html as validator

    legacy = tmp / "legacy-keys.json"
    external = tmp / "external-keys.json"
    legacy.write_text(json.dumps({"amap": {"jsKey": "LEGACY_JS_123456",
                                            "webKey": "LEGACY_WEB_123456"},
                                  "qweather": {"key": "LEGACY_QW_123456"}}), encoding="utf-8")
    external.write_text(json.dumps({"amap": {"jsKey": "EXTERNAL_JS_123456",
                                              "webKey": "EXTERNAL_WEB_123456"},
                                    "qweather": {"key": "EXTERNAL_QW_123456"}}), encoding="utf-8")
    prior_legacy = validator.KEYS_PATH
    prior_override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE")
    prior_cwd = pathlib.Path.cwd()
    try:
        validator.KEYS_PATH = legacy
        os.chdir(tmp)
        os.environ["TRAVEL_GUIDE_KEYS_FILE"] = "external-keys.json"
        paths = validator.keys_paths()
        if paths != [external.resolve(), legacy.resolve()]:
            print("BAD  包外与 legacy 路径优先级 / 相对路径语义")
            return False
        for name, sample, want in (
            ("包外和风", "EXTERNAL_QW_123456", "和风 key"),
            ("legacy 和风", "LEGACY_QW_123456", "和风 key"),
            ("包外 Web", "EXTERNAL_WEB_123456", "高德 Web 服务 key"),
            ("legacy Web", "LEGACY_WEB_123456", "高德 Web 服务 key"),
            ("私人地图 JS", "EXTERNAL_JS_123456", None),
        ):
            rep = validator.Report(quiet=True)
            validator.check_secret_leak(f"<p>{sample}</p>", rep)
            ok = (want is None and not rep.fails) or (want is not None and any(want in f for f in rep.fails))
            print(f"{'OK  ' if ok else 'BAD '} 合成钥匙 {name}")
            if not ok:
                return False
        return True
    finally:
        validator.KEYS_PATH = prior_legacy
        os.chdir(prior_cwd)
        if prior_override is None:
            os.environ.pop("TRAVEL_GUIDE_KEYS_FILE", None)
        else:
            os.environ["TRAVEL_GUIDE_KEYS_FILE"] = prior_override


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not VALIDATOR.exists():
        print(f"找不到 {VALIDATOR}")
        return 1

    wrong = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, content, want, bom, warn, fail, absent in build():
            path = pathlib.Path(tmp) / "case.html"
            path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + content.encode("utf-8"))
            r = subprocess.run([sys.executable, str(VALIDATOR), str(path)],
                               capture_output=True, text=True, encoding="utf-8")
            out = (r.stdout or "") + (r.stderr or "")
            ok = r.returncode == want
            if ok and warn and warn not in out:
                ok = False
                print(f"      期望 WARN 未出现：{warn}")
            if ok and fail and fail not in out:
                ok = False
                print(f"      期望 FAIL 未出现：{fail}")
            for snippet in ((absent,) if isinstance(absent, str) else (absent or ())):
                if snippet in out:
                    ok = False
                    print(f"      不应出现的诊断：{snippet}")
            wrong += 0 if ok else 1
            print(f"{'OK  ' if ok else 'BAD '} {name}（期望 {want}，实际 {r.returncode}）")
            if not ok:
                print((r.stdout or "")[-700:])
        if not test_secret_path_union(pathlib.Path(tmp)):
            wrong += 1
    print()
    print("自查通过" if wrong == 0 else f"有 {wrong} 个用例不符合预期")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
