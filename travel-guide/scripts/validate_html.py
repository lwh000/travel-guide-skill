#!/usr/bin/env python3
"""交付前校验单份 HTML 攻略（纯标准库，不联网）。

用法：
    python validate_html.py <攻略.html>
    python validate_html.py --quiet <攻略.html>

退出码：0 = 没有 FAIL；1 = 有 FAIL。
WARN 不阻塞交付，但要在对话里说明。

职责边界：本校验器只做输出结构 / 格式 / 完整性检查。
不得在这里加研究逻辑：不搜网页、不补研究、不重新验证旅游事实、不触发外部工具。
（唯一例外在研究侧：自驾地图缺一个会挡住已确认路线的关键坐标时，最多补 3 单位，
由生成方按 research-playbook.md 处理，不由本脚本发起。）
"""
from __future__ import annotations

import argparse
from datetime import date
from html import unescape
from html.parser import HTMLParser
import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SKILL_ROOT = Path(__file__).resolve().parent.parent
KEYS_PATH = SKILL_ROOT / "local-keys.json"


def keys_paths() -> list[Path]:
    """Inspect configured and legacy keys, even when an override is active.

    live_data.py resolves a relative override from the current working directory.
    Validation also checks the legacy file so an old key cannot be hidden by an
    unrelated override. No key value or file contents are logged.
    """
    override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE", "").strip()
    paths = [Path(override).expanduser()] if override else []
    paths.append(KEYS_PATH)
    return list(dict.fromkeys(path.resolve() for path in paths))

PLACEHOLDER_RE = re.compile(r"\{\{\s*[A-Z_]+\s*\}\}")
GEO_RE = re.compile(r'<script[^>]*id=["\']trip-geo["\'][^>]*>(.*?)</script>', re.S | re.I)
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
DAY_RE = re.compile(r'<article\b[^>]*class=["\'][^"\']*\bday\b[^"\']*["\']', re.I)
SLOT_RE = re.compile(r'class=["\'][^"\']*\bslot\b[^"\']*["\']', re.I)
STAY_CARD_RE = re.compile(r'class=["\'][^"\']*\bstay-card\b[^"\']*["\']', re.I)
ART_FIG_RE = re.compile(r'class=["\'][^"\']*\bart-fig\b[^"\']*["\']', re.I)
SECTION_RE = re.compile(r"<section\b[^>]*\bid=[\"']([^\"']+)[\"'][^>]*>", re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# 判文案/图片只看得见的部分：剥掉 script、style、注释
NON_VISIBLE_RE = re.compile(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", re.S | re.I)

MODES = {"self_drive", "city_trip", "multi_city_transit", "mixed"}
TRIPLETS = {"amap": ("amap", "gcj02"), "svg": ("google", "wgs84")}
KINDS = {"start", "stay", "end", "hotel", "spot", "food",
         "service", "fuel", "charge", "park", "photo"}
STOP_FILTERS = {"all", "service", "fuel", "charge", "park", "hotel", "spot", "food", "photo"}
LEG_MODES = {"self_drive", "train", "flight", "bus", "ferry",
             "metro", "taxi", "rideshare", "walk", "bike", "other"}
SAMPLE_JSON_NAMES = ("出发地", "过夜城", "终点", "途经1", "sample-trip")
PROVIDER_TEXT = {
    "amap": ("在高德打开全程", "在高德打开本段导航", "路况以高德导航为准"),
    "google": ("在 Google Maps 打开全程", "在 Google Maps 打开本段导航", "路况以 Google Maps 为准"),
}


class Report:
    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.fails.append(msg)
        if not self.quiet:
            print(f"  FAIL  {msg}")

    def warn(self, msg: str) -> None:
        self.warns.append(msg)
        if not self.quiet:
            print(f"  WARN  {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(msg)
        if not self.quiet:
            print(f"  info  {msg}")


def strip_non_visible(html: str) -> str:
    """去掉 script / style / 注释，只留用户能看到的静态内容。"""
    return NON_VISIBLE_RE.sub(" ", html)


# 这几个元素的文案由壳子 JS 在运行时写入（`textContent` / `setStatus`），
# 静态默认值不是交付给用户看的 UI，检查“可见文案”时要先剥掉。
JS_MANAGED_RE = re.compile(
    r'<a\b[^>]*\bid=["\'](?:nav-full|view-nav)["\'][^>]*>.*?</a>'
    r'|<span\b[^>]*\bid=["\']hero-nav-note["\'][^>]*>.*?</span>'
    r'|<p\b[^>]*\bid=["\']map-status["\'][^>]*>.*?</p>',
    re.S | re.I,
)


def strip_js_managed(visible: str) -> str:
    return JS_MANAGED_RE.sub(" ", visible)


def coord_problem(value: object, lo: float, hi: float) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "缺失或不是数字"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "不是有限数字"
    if not (lo <= float(value) <= hi):
        return f"超出 {lo:g} ~ {hi:g}"
    return None


def find_duplicates(values: list) -> list:
    seen, dup = set(), []
    for v in values:
        if v in seen and v not in dup:
            dup.append(v)
        seen.add(v)
    return dup


def is_amap_car_nav(url: object) -> bool:
    """self_drive.fullNav / mixed 自驾段 nav 必须是高德驾车 URI。"""
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.netloc != "uri.amap.com" or parsed.path != "/navigation":
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(query.get(key, [])) != 1 for key in ("from", "to", "mode")):
        return False

    def coordinates(value: str) -> bool:
        parts = value.split(",", 2)
        if len(parts) < 2:
            return False
        try:
            lon, lat = float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            return False
        return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90

    return (coordinates(query["from"][0]) and coordinates(query["to"][0])
            and query["mode"][0] == "car")



def needs_map_ui(mode: object, views: list) -> bool:
    """自驾，或 mixed 里存在 drive:true 且 lineMode:route 的视图，才要地图界面。"""
    if mode == "self_drive":
        return True
    if mode == "mixed":
        for v in views:
            if not isinstance(v, dict):
                continue
            if v.get("drive") is True and v.get("lineMode") == "route":
                return True
    return False


def section_inner(html: str, section_id: str) -> str | None:
    pat = re.compile(
        rf'<section\b[^>]*\bid=["\']{re.escape(section_id)}["\'][^>]*>(.*?)</section>',
        re.S | re.I,
    )
    m = pat.search(html)
    return m.group(1) if m else None


ISO_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})\s*日?")
MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[月/]\s*(\d{1,2})\s*日?")
TEMP_RE = re.compile(
    r"-?\d+(?:\.\d+)?\s*(?:[–\-~〜至到]\s*-?\d+(?:\.\d+)?)?\s*(?:°\s*C|℃|摄氏度)"
    r"|(?:气温|温度|高温|低温)\s*[:：]?\s*-?\d+(?:\.\d+)?\s*[–\-~〜至到]\s*-?\d+(?:\.\d+)?",
    re.I,
)
WEEKDAYS = "一二三四五六日"
ARTICLE_DAY_RE = re.compile(
    r'<article\b[^>]*class=["\'][^"\']*\bday\b[^"\']*["\'][^>]*>.*?</article>', re.S | re.I)


class Markup(HTMLParser):
    """Small structural index for attributes and class text; no network or browser execution."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.blocks: list[tuple[str, str]] = []
        self.stack: list[tuple[str, set[str], list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.tags.append((tag, values))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, set(values.get("class", "").split()), []))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1][2].append(data)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                while len(self.stack) > index:
                    _tag, classes, parts = self.stack.pop()
                    value = " ".join(parts).strip()
                    for class_name in classes:
                        self.blocks.append((class_name, value))
                    if self.stack:
                        self.stack[-1][2].append(value)
                break

    def class_text(self, name: str) -> list[str]:
        return [value for class_name, value in self.blocks if class_name == name]


def parse_markup(fragment: str) -> Markup:
    parsed = Markup()
    parsed.feed(fragment)
    parsed.close()
    return parsed


def parse_display_date(text: str, year_hint: int | None = None) -> date | None:
    match = ISO_DATE_RE.search(text)
    if match:
        values = tuple(map(int, match.groups()))
    else:
        match = MONTH_DAY_RE.search(text)
        if not match or year_hint is None:
            return None
        values = (year_hint, *map(int, match.groups()))
    try:
        return date(*values)
    except ValueError:
        return None


def page_year_hint(visible: str) -> int | None:
    """Infer the trip year only when title/header/overview give one unambiguous year."""
    context_parts = []
    for pattern in (r"<title\b[^>]*>(.*?)</title>", r"<header\b[^>]*>(.*?)</header>"):
        match = re.search(pattern, visible, re.S | re.I)
        if match:
            context_parts.append(match.group(1))
    context_parts.append(section_inner(visible, "overview") or "")
    context = " ".join(context_parts)
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})\s*(?:年|[-/.]\d{1,2})", context)}
    return next(iter(years)) if len(years) == 1 else None


def trip_day_dates(visible: str, rep: "Report") -> set[date]:
    """Use explicit year or a single year in title/header/overview; never guess across years."""
    year_hint = page_year_hint(visible)
    dates: set[date] = set()
    for article in ARTICLE_DAY_RE.findall(visible):
        parsed = parse_markup(article)
        labels = parsed.class_text("day-date")
        if not labels:
            continue
        day = parse_display_date(labels[0], year_hint)
        if day is None:
            if MONTH_DAY_RE.search(labels[0]) and year_hint is None:
                rep.warn(f"逐日卡片缺年份上下文，无法校验星期：{labels[0]!r}")
            else:
                rep.fail(f"逐日卡片日期无效：{labels[0]!r}")
            continue
        dates.add(day)
        weeks = parsed.class_text("day-week")
        if weeks:
            match = re.search(r"周([一二三四五六日天])", weeks[0])
            if match and WEEKDAYS[day.weekday()] != match.group(1).replace("天", "日"):
                rep.fail(f"{day.isoformat()} 星期写成 {match.group(0)}，实际周{WEEKDAYS[day.weekday()]}")
    return dates


def check_schedule_weekdays(visible: str, trip_dates: set[date], rep: "Report") -> set[date]:
    inner = section_inner(visible, "schedule")
    if inner is None:
        return set()
    years = {day.year for day in trip_dates}
    year_hint = next(iter(years)) if len(years) == 1 else page_year_hint(visible)
    schedule_dates: set[date] = set()
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", inner, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", " ", cell).strip() for cell in
                 re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        for cell in cells:
            day = parse_display_date(cell, year_hint)
            if day:
                schedule_dates.add(day)
        for date_cell, week_cell in zip(cells, cells[1:]):
            day = parse_display_date(date_cell, year_hint)
            week = re.fullmatch(r"周([一二三四五六日天])", week_cell)
            if day and week and WEEKDAYS[day.weekday()] != week.group(1).replace("天", "日"):
                rep.fail(f"每日总表 {day.isoformat()} 星期写成 {week.group(0)}，实际周{WEEKDAYS[day.weekday()]}")
    return schedule_dates


def is_editorial_guide(src: str, visible: str) -> bool:
    """Decoration checks apply only to dated itinerary guides in editorial style."""
    if re.search(r'<(?:html|body)\b[^>]*data-guide-style=["\'](?:minimal|print)["\']',
                 COMMENT_RE.sub(" ", src), re.I):
        return False
    return bool(DAY_RE.search(visible))


def day_has_itinerary_content(article: str) -> bool:
    """Ignore date badges and decorative art when checking for an actual day plan."""
    class DayText(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.skip_depth = 0
            self.parts: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
                return
            classes = set((dict(attrs).get("class") or "").split())
            if self.skip_depth or tag == "figure" or classes & {"day-head", "day-no", "art-fig"}:
                self.skip_depth += 1

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            pass

        def handle_endtag(self, tag: str) -> None:
            if self.skip_depth:
                self.skip_depth -= 1

        def handle_data(self, data: str) -> None:
            if not self.skip_depth:
                self.parts.append(data)

    parsed = DayText()
    parsed.feed(article)
    text = " ".join(parsed.parts)
    # A slot label without a destination or activity is still an empty plan.
    text = re.sub(r"(?:清晨|上午|中午|下午|傍晚|晚上|夜间|全天)\s*[:：]?", " ", text)
    return bool(re.search(r"[\w\u4e00-\u9fff]", text))


def hero_background_styles(visible: str) -> list[str]:
    return [attrs.get("style", "") for _tag, attrs in parse_markup(visible).tags
            if "hero-bg" in attrs.get("class", "").split()]


def check_magazine(visible: str, rep: "Report") -> None:
    """杂志版底线：只 WARN，不阻塞交付。

    2.8.0 的「少图少卡」把 HTML 做得像合规表格；2.9.0 起用户要 HTML 就是默认杂志版，
    这几条只是提醒「内容是不是又瘦回去了」，不拦交付。
    """
    imgs = len(IMG_RE.findall(visible))
    figs = len(ART_FIG_RE.findall(visible))
    days = len(DAY_RE.findall(visible))
    slots = len(SLOT_RE.findall(visible))
    stay_cards = len(STAY_CARD_RE.findall(visible))
    hero_visual = any(re.search(r"(?:gradient|url)\s*\(", style, re.I)
                      for style in hero_background_styles(visible))

    if imgs == 0 and figs == 0 and not hero_visual:
        rep.warn("整页没有 <img> 也没有 .art-fig 氛围块：杂志版容易显得空，用封面/过夜城风景图或渐变块补上")
    empty_days = [index for index, article in enumerate(ARTICLE_DAY_RE.findall(visible), 1)
                  if not day_has_itinerary_content(article)]
    if empty_days:
        rep.warn(f"逐日卡片缺少实际行程安排：D{', D'.join(map(str, empty_days))} 内容为空")
    stay_inner = section_inner(visible, "stay")
    if stay_inner is not None and stay_cards == 0 and "<table" not in stay_inner.lower():
        rep.warn("住宿节既没有表格也没有 .stay-card：杂志版建议用卡片写主选 + 备选")

    rep.note(f"杂志版：img={imgs} art-fig={figs} day={days} slot={slots} stay-card={stay_cards}")


def check_hero_cover(html: str, rep: "Report") -> None:
    """Gradient is a valid cover; only authored photo needs an attribution cue."""
    styles = hero_background_styles(html)
    if not styles:
        rep.warn("页头没有 .hero-bg：杂志版可用合法实拍图或渐变色作封面")
        return
    has_image = any(re.search(r"url\s*\(", style, re.I) for style in styles)
    if not has_image:
        return
    if not re.search(r"hero-credit|CC BY", html, re.I):
        rep.warn("页头封面用了图片但没看到署名：Commons 图需标注 地点·作者·许可证")


def check_weather_body(visible: str, weather_meta: object, trip_dates: set[date], rep: "Report") -> None:
    inner = section_inner(visible, "weather")
    if inner is None:
        return
    parsed = parse_markup(inner)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
    cards = parsed.class_text("wx-card")
    weather_open = re.search(r'<section\b[^>]*\bid=["\']weather["\'][^>]*>', visible, re.I)
    unavailable = bool(weather_open and re.search(
        r'data-weather-status=["\']unavailable["\']', weather_open.group(0), re.I))
    if unavailable:
        if cards or TEMP_RE.search(text):
            rep.fail("天气标为 unavailable 却仍有气温卡或气温数字")
        if not re.search(r"暂无|尚未|未查到|无法核实|未发布", text):
            rep.fail("天气 unavailable 状态须说明缺数据的原因")
        if not re.search(r"出发前|临近出行|临行前|再核|再查", text):
            rep.fail("天气 unavailable 状态须写明出行前复查")
        if len(text) < 20:
            rep.fail("天气 unavailable 状态说明过短")
        official_link = False
        for anchor in re.finditer(r'<a\b([^>]*)>(.*?)</a>', inner, re.S | re.I):
            href_match = re.search(r'\bhref=["\']([^"\']+)["\']', anchor.group(1), re.I)
            if not href_match:
                continue
            try:
                url = urlsplit(unescape(href_match.group(1)))
            except ValueError:
                continue
            label = re.sub(r"<[^>]+>", " ", anchor.group(2))
            host = (url.hostname or "").lower()
            known_source = host == "nmc.cn" or host.endswith(".nmc.cn") or host == "weather.com.cn" or host.endswith(".weather.com.cn")
            if url.scheme == "https" and host and (known_source or re.search(r"官方|气象局|气象台", label)):
                official_link = True
                break
        if not official_link:
            rep.fail("天气 unavailable 状态缺可点击的官方天气查询入口")
        return
    if cards:
        for index, card in enumerate(cards, 1):
            if not TEMP_RE.search(card):
                rep.fail(f"天气 .wx-card 第 {index} 张缺有效气温单位（°C / ℃ / 摄氏度）")
    elif not TEMP_RE.search(text):
        rep.fail("天气节必须有带单位的气温数字，不能把日期范围当气温或只写失败说明")
    if len(text) < 12:
        rep.fail("天气节不能只留标题或空说明，必须有预报/气候正文")

    asof_match = re.search(r"(?:查询(?:日期|时间)?|资料截至|截至)\s*[:：]?\s*"
                           r"(20\d{2}[-年/.]\d{1,2}[-月/.]\d{1,2}\s*日?)", text)
    asof = parse_display_date(asof_match.group(1)) if asof_match else None
    if asof is None:
        rep.fail("天气节缺有效查询日期（YYYY-MM-DD）")
    source_names = {"qweather": "和风", "nmc": "中央气象台", "china-weather": "中国天气网"}
    if not re.search(r"来源\s*[:：]\s*\S|以(?:和风|中央气象台|中国天气网)[^。]{0,12}为准", text):
        rep.fail("天气节缺可见来源")

    mode = None
    if weather_meta is not None:
        if not isinstance(weather_meta, dict):
            rep.fail("#trip-geo.weather 必须是对象")
        else:
            meta_asof = parse_display_date(str(weather_meta.get("asOf", "")))
            if meta_asof is None:
                rep.fail("#trip-geo.weather.asOf 必须是有效 YYYY-MM-DD 日期")
            elif asof and meta_asof != asof:
                rep.fail("#trip-geo.weather.asOf 与天气节查询日期不一致")
            source = weather_meta.get("source")
            if not isinstance(source, str) or source not in source_names:
                rep.fail("#trip-geo.weather.source 应为 qweather / nmc / china-weather")
            elif source_names[source] not in text:
                rep.fail("#trip-geo.weather.source 与天气节可见来源不一致")
            mode = weather_meta.get("mode")
            if not isinstance(mode, str) or mode not in {"forecast", "climate_plus_recent"}:
                rep.fail("#trip-geo.weather.mode 应为 forecast / climate_plus_recent")
            places = weather_meta.get("places")
            if not isinstance(places, list) or not places or not all(isinstance(p, str) and p.strip() for p in places):
                rep.fail("#trip-geo.weather.places 必须是非空地点列表")

    # Only dated forecast cards are compared with itinerary days. Climate / recent
    # reference cards can legitimately describe another date, if labelled so.
    if trip_dates:
        years = {d.year for d in trip_dates}
        year_hint = next(iter(years)) if len(years) == 1 else None
        for index, label in enumerate(parsed.class_text("wx-date")):
            card_day = parse_display_date(label, year_hint)
            card_text = cards[index] if index < len(cards) else ""
            explicit_reference = bool(re.search(r"近期参考|历史气候|气候规律|非出行日预报", card_text))
            if card_day and card_day not in trip_dates and mode != "climate_plus_recent" and not (mode is None and explicit_reference):
                rep.fail(f"预报卡日期 {card_day.isoformat()} 不在逐日行程日期内")


def check_sources(visible: str, rep: "Report") -> None:
    inner = section_inner(visible, "sources")
    if inner is None:
        rep.fail("完整 HTML 缺 #sources 出处节")
        return
    body = re.sub(r"<h[1-6]\b[^>]*>.*?</h[1-6]>", " ", inner, flags=re.S | re.I)
    body_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
    if not body_text or body_text in {"示例", "待补", "暂无", "出处", "来源"}:
        rep.fail("#sources 出处节没有具体来源")


def check_markup_attributes(visible: str, rep: "Report") -> None:
    parsed = parse_markup(visible)
    for tag, attrs in parsed.tags:
        if tag == "a":
            href = attrs.get("href", "").strip()
            if re.match(r"(?i)^(?:javascript|vbscript|data)\s*:", href):
                rep.fail(f"链接使用不安全 href：{href[:80]}")
        if tag == "img":
            if "alt" not in attrs:
                rep.fail("有 <img> 没有 alt（data-alt 不能代替 alt）")


def check_secret_leak(html: str, rep: "Report") -> None:
    # Bounded same-attribute/string search allows wrapped URLs without matching
    # a separate unrelated key much later in the document.
    src = unescape(COMMENT_RE.sub(" ", html))
    if re.search(r"restapi\.amap\.com(?:(?![\"'<>]).){0,500}[?&]\s*key\s*=", src, re.I | re.S):
        rep.fail("HTML 里出现了高德 Web 服务请求（含 key）。票价在生成时查好写入表格，不要把 Web 服务 key 写进页面")
    if re.search(r"(?:qweather\.com|qweatherapi\.com)(?:(?![\"'<>]).){0,500}[?&]\s*key\s*=", src, re.I | re.S):
        rep.fail("HTML 里出现了和风天气请求（含 key）。天气在生成时查好，不要把和风 key 写进页面")
    leaked_web = leaked_qw = False
    for path in keys_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        amap = data.get("amap") if isinstance(data.get("amap"), dict) else {}
        qw = data.get("qweather") if isinstance(data.get("qweather"), dict) else {}
        js_key = str(amap.get("jsKey") or "").strip()
        web_key = str(amap.get("webKey") or "").strip()
        qw_key = str(qw.get("key") or "").strip()
        # 私人 AMap 地图脚本允许 jsKey；独立的 Web 服务 key 和和风 key 必须拦下。
        leaked_web |= len(web_key) >= 8 and web_key != js_key and web_key in html
        leaked_qw |= len(qw_key) >= 8 and qw_key in html
    if leaked_web:
        rep.fail("HTML 里泄漏了 高德 Web 服务 key")
    if leaked_qw:
        rep.fail("HTML 里泄漏了 和风 key")


def check_geo(data: dict, src: str, visible: str, geo_text: str, rep: Report) -> None:
    for key in ("version", "tripId", "htmlMode", "mapRenderer", "linkProvider", "coordinateSystem"):
        if not data.get(key):
            rep.fail(f"#trip-geo 缺 {key}")

    mode = data.get("htmlMode")
    renderer = data.get("mapRenderer")
    provider = data.get("linkProvider")
    coords = data.get("coordinateSystem")

    if mode and mode not in MODES:
        rep.fail(f"htmlMode={mode!r} 不是 {'/'.join(sorted(MODES))} 之一")
    if renderer == "svg" and mode in {"self_drive", "mixed"} and (provider, coords) == ("amap", "gcj02"):
        # Shareable domestic drive guide: static SVG route, AMap navigation links.
        pass
    elif renderer in TRIPLETS:
        want_provider, want_coords = TRIPLETS[renderer]
        if provider != want_provider:
            rep.fail(f"mapRenderer={renderer} 时 linkProvider 应为 {want_provider}，实际 {provider!r}")
        if coords != want_coords:
            rep.fail(f"mapRenderer={renderer} 时 coordinateSystem 应为 {want_coords}，实际 {coords!r}")
    elif renderer:
        rep.fail(f"mapRenderer={renderer!r} 不是 amap / svg")

    # ---------- points ----------
    points = data.get("points") or []
    for p in points:
        if not isinstance(p, dict):
            rep.fail(f"points 里有非对象元素：{p!r}")
            continue
        if not p.get("id"):
            rep.fail(f"points 缺 id：{p!r}")
        if not p.get("name"):
            rep.fail(f"points[{p.get('id')}] 缺 name")
        if p.get("kind") is not None and p["kind"] not in KINDS:
            rep.warn(f"points[{p.get('id')}] kind={p['kind']!r} 不在约定集合里")
        for axis, (lo, hi) in (("lon", (-180.0, 180.0)), ("lat", (-90.0, 90.0))):
            why = coord_problem(p.get(axis), lo, hi)
            if why:
                rep.fail(f"points[{p.get('id')}].{axis} {why}"
                         "（无坐标的点只写正文表格，不要放进 points）")

    dup_points = find_duplicates([p.get("id") for p in points if isinstance(p, dict)])
    if dup_points:
        rep.fail("points 里有重复 id：" + ", ".join(map(str, dup_points))
                 + "（壳子按 id 建索引，后面的会静默覆盖前面的）")
    ids = {p.get("id") for p in points if isinstance(p, dict)}

    # ---------- views ----------
    views = data.get("views") or []
    bad_refs: list[str] = []
    for v in views:
        if not isinstance(v, dict):
            rep.fail(f"views 里有非对象元素：{v!r}")
            continue
        vid = v.get("id")
        for key in ("path", "markers"):
            for ref in v.get(key) or []:
                if ref not in ids:
                    bad_refs.append(f"views[{vid}].{key} -> {ref}")
        lm = v.get("lineMode")
        if lm is not None and lm not in ("route", "none"):
            rep.fail(f"views[{vid}].lineMode={lm!r} 不是 route / none")
        effective_lm = lm if lm is not None else ("route" if mode == "self_drive" else "none")
        if effective_lm == "route":
            valid_path = [ref for ref in (v.get("path") or []) if ref in ids]
            if len(valid_path) < 2:
                rep.fail(f"views[{vid}] lineMode=route 的 path 至少要 2 个有效 point ID，"
                         f"实际 {len(valid_path)}")
        if "drive" in v and mode != "mixed":
            rep.fail(f"views[{vid}] 有 drive 字段，但 htmlMode={mode!r}（drive 只给 mixed）")
        if mode == "mixed" and v.get("drive") is True and lm != "route":
            rep.fail(f"views[{vid}] drive=true 但 lineMode={lm!r}"
                     "（自驾段必须是 route，否则不加载 Driving、也不显示停靠）")

    dup_views = find_duplicates([v.get("id") for v in views if isinstance(v, dict)])
    if dup_views:
        rep.fail("views 里有重复 id：" + ", ".join(map(str, dup_views)))

    # ---------- legs 引用 ----------
    for leg in data.get("legs") or []:
        if not isinstance(leg, dict):
            rep.fail(f"legs 里有非对象元素：{leg!r}")
            continue
        for key in ("from", "to"):
            if leg.get(key) not in ids:
                bad_refs.append(
                    f"legs[{leg.get('from')}->{leg.get('to')}].{key} -> {leg.get(key)}"
                )
    if bad_refs:
        rep.fail("path / markers / legs 引用了 points 里不存在的 ID："
                 + "; ".join(sorted(set(bad_refs))))

    # ---------- transport ----------
    transport = data.get("transport")
    if transport is not None:
        if not isinstance(transport, dict):
            rep.fail("transport 必须是对象")
        else:
            default = transport.get("default")
            if default is not None and default not in (LEG_MODES | {"transit", "mixed"}):
                rep.fail(f"transport.default={default!r} 不是约定取值")
            if mode == "self_drive" and default is not None and default != "self_drive":
                rep.fail(f"htmlMode=self_drive 时 transport.default 应为 self_drive，实际 {default!r}")
            if mode in ("city_trip", "multi_city_transit") and default == "self_drive":
                rep.fail(f"htmlMode={mode} 时 transport.default 不该是 self_drive")
            for leg in transport.get("legs") or []:
                if not isinstance(leg, dict):
                    rep.fail(f"transport.legs 里有非对象元素：{leg!r}")
                    continue
                lm = leg.get("mode")
                if lm is not None and lm not in LEG_MODES:
                    rep.fail(f"transport.legs {leg.get('from')}->{leg.get('to')} "
                             f"mode={lm!r} 不是约定取值")

    # ---------- fullNav / 导航 ----------
    if data.get("fullNav") and mode != "self_drive":
        rep.fail(f"fullNav 只在 self_drive 出现，当前 htmlMode={mode!r}")

    def line_mode_of(v: dict):
        lm = v.get("lineMode")
        if lm is None:
            return "route" if mode == "self_drive" else "none"
        return lm

    def can_drive_js(v: object) -> bool:
        if not isinstance(v, dict):
            return False
        if line_mode_of(v) != "route":
            return False
        if mode == "self_drive":
            return True
        return mode == "mixed" and v.get("drive") is True

    drive_views = [v for v in views if can_drive_js(v)]
    needs_driving = bool(drive_views) and renderer == "amap"

    if mode == "self_drive":
        full = data.get("fullNav")
        if not is_amap_car_nav(full):
            if not full:
                rep.fail('self_drive 必须有 fullNav（否则「在高德打开全程」按钮是 href="#" 的空壳）')
            else:
                rep.fail("self_drive 的 fullNav 必须是 https://uri.amap.com/navigation? 且含 from / to / mode=car")
    if mode == "mixed":
        for v in drive_views:
            nav = v.get("nav")
            if not is_amap_car_nav(nav):
                if not nav:
                    rep.fail(f"mixed 的自驾段 views[{v.get('id')}] 缺 nav（mixed 没有 fullNav）")
                else:
                    rep.fail(f"mixed 的自驾段 views[{v.get('id')}].nav 必须是 "
                             "https://uri.amap.com/navigation? 且含 from / to / mode=car")

    map_ui = needs_map_ui(mode, views)

    if map_ui and not points:
        rep.fail("points 为空：地图没有可画的点")

    # ---------- 脚本加载（看整份源码）----------
    amap_src = []
    for tag, attrs in parse_markup(src).tags:
        if tag != "script" or not attrs.get("src"):
            continue
        try:
            url = urlsplit(attrs["src"])
        except ValueError:
            continue
        if url.hostname == "webapi.amap.com" and url.path.startswith("/maps"):
            amap_src.append(attrs["src"])
    if not map_ui and amap_src:
        rep.fail("无地图行程不该加载高德地图脚本")
    if renderer == "svg" and amap_src:
        rep.fail("mapRenderer=svg 却引用了 webapi.amap.com/maps 脚本")
    if map_ui and renderer == "amap" and amap_src:
        joined = amap_src[0]
        if needs_driving and "AMap.Driving" not in joined:
            rep.fail("该行程需要驾车规划，但 AMap 脚本的 plugin 里没有 AMap.Driving")
        if not needs_driving and "AMap.Driving" in joined:
            rep.fail("非自驾行程不该加载 AMap.Driving")
        authored_src = COMMENT_RE.sub(" ", src)
        sec = authored_src.find("_AMapSecurityConfig")
        maps_at = authored_src.find("webapi.amap.com/maps")
        if sec < 0:
            rep.fail("加载了 AMap 但没有 window._AMapSecurityConfig（缺安全密钥会鉴权失败）")
        elif sec > maps_at:
            rep.fail("_AMapSecurityConfig 必须写在 AMap maps 脚本之前")

    # ---------- 天气 / 地图 / 票价 ----------
    sections = {s.lower() for s in SECTION_RE.findall(visible)}
    if map_ui:
        if "map" not in sections:
            rep.fail("自驾行程必须有 #map 地图节")
        if mode == "mixed" and isinstance(transport, dict):
            legs = transport.get("legs") or []
            has_intercity = any(
                isinstance(leg, dict) and
                (leg.get("mode") in {"train", "flight", "ferry"} or
                 (leg.get("mode") == "bus" and leg.get("intercity") is True))
                for leg in legs
            )
            if has_intercity:
                inner = section_inner(visible, "transit")
                if inner is None or not re.search(r"<table\b", inner, re.I):
                    rep.fail("mixed 含城际大交通时必须保留 #transit 票价表")
    else:
        if "map" in sections:
            rep.fail("飞机/高铁/火车或市内行程不要 #map 地图界面")
        if 'href="#map"' in visible or "href='#map'" in visible:
            rep.fail("无地图行程还留着导航「路线图」")
        transport_in_scope = bool(data.get("legs") or data.get("transport"))
        if "transit" not in sections and transport_in_scope:
            rep.fail("有交通路段的无地图行程必须有 #transit 票价节")
        else:
            inner = section_inner(visible, "transit")
            if inner is not None and not re.search(r"<table\b", inner, re.I):
                rep.fail("无地图行程的票价节必须有价格表")

    # ---------- 停靠节 ----------
    has_stops = "stops" in sections
    if drive_views and not has_stops:
        rep.warn("有自驾段但没有 #stops 停靠节")
    if has_stops and not drive_views:
        rep.fail("非自驾行程还留着 #stops 整节（会露出一排空筛选按钮）")
    odd = set(re.findall(r'data-stop-filter=["\']([^"\']+)["\']', visible, re.I)) - STOP_FILTERS
    if odd:
        rep.warn("停靠筛选用了约定外的 data-stop-filter：" + ", ".join(sorted(odd))
                 + "（壳子约定 food，别写 eat）")

    # ---------- 默认视图 ----------
    dv = data.get("defaultView")
    if dv and dv not in {v.get("id") for v in views if isinstance(v, dict)}:
        rep.fail(f"defaultView={dv!r} 不在 views[].id 里")

    # ---------- 可见文案 vs linkProvider ----------
    # 只查可见 UI；壳子 JS 里的 NAV_TEXT 是运行逻辑，不算错误文案
    authored = strip_js_managed(visible)
    for wrong_provider, texts in PROVIDER_TEXT.items():
        if wrong_provider == provider:
            continue
        for t in texts:
            if t in authored:
                rep.fail(f"linkProvider={provider!r}，但页面可见文案出现了 {wrong_provider} 的「{t}」")

    # ---------- 样例名（只在 geo JSON 里查）----------
    for name in SAMPLE_JSON_NAMES:
        if name in geo_text:
            rep.fail(f"#trip-geo 里还留着壳子样例点名「{name}」")

    # ---------- 图片 ----------
    img_srcs = re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', visible, re.I)
    if any(s.startswith("http") and "wikimedia" not in s for s in img_srcs):
        rep.warn("有非 Wikimedia 的远程图：确认是官网可热链图，不是酒店 CDN")

    rep.note(f"htmlMode={mode} mapRenderer={renderer} "
             f"linkProvider={provider} coordinateSystem={coords}")
    rep.note(f"points={len(points)} views={len(views)} "
             f"legs={len(data.get('legs') or [])} driveViews={len(drive_views)}")
    if data.get("tripId"):
        rep.note(f"tripId={data['tripId']}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="校验单份 HTML 攻略的交付硬条件")
    ap.add_argument("html", type=Path, help="要校验的 HTML 文件")
    ap.add_argument("--quiet", action="store_true", help="只输出总结")
    args = ap.parse_args()

    path: Path = args.html
    if not path.is_file():
        print(f"找不到文件：{path}")
        return 1

    raw = path.read_bytes()
    rep = Report(quiet=args.quiet)
    if raw[:3] == b"\xef\xbb\xbf":
        rep.fail("文件带 UTF-8 BOM，应改成无 BOM")
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"不是合法 UTF-8：{exc}")
        return 1

    if "<html" not in html.lower():
        rep.warn("这看起来不是完整 HTML 文件")

    visible = strip_non_visible(html)
    authored_source = COMMENT_RE.sub(" ", html)

    sections_all = {s.lower() for s in SECTION_RE.findall(visible)}
    check_secret_leak(html, rep)

    leftovers = PLACEHOLDER_RE.findall(authored_source)
    if leftovers:
        rep.fail("还有未替换的占位符：" + ", ".join(sorted(set(leftovers))))

    if re.search(r"\bdocument\s*\.\s*write\s*\(", authored_source):
        rep.fail("文件里有 document.write（禁止运行时补载）")

    check_markup_attributes(visible, rep)
    if re.search(r"<html\b", html, re.I):
        check_sources(visible, rep)
    trip_dates = trip_day_dates(visible, rep)
    trip_dates.update(check_schedule_weekdays(visible, trip_dates, rep))

    m = GEO_RE.search(html)
    if not m:
        rep.fail('没有找到 <script id="trip-geo"> 数据块')
    else:
        geo_text = m.group(1)
        data: object = {}
        try:
            data = json.loads(geo_text)
        except json.JSONDecodeError as exc:
            rep.fail(f"#trip-geo JSON 解析失败：{exc}")
        if not isinstance(data, dict):
            rep.fail("#trip-geo 必须是 JSON 对象")
        else:
            check_geo(data, html, visible, geo_text, rep)
            if "weather" in sections_all:
                check_weather_body(visible, data.get("weather"), trip_dates, rep)

    if is_editorial_guide(html, visible):
        check_magazine(visible, rep)
        check_hero_cover(html, rep)

    print()
    print(f"{path.name}: {len(rep.fails)} FAIL / {len(rep.warns)} WARN")
    for w in rep.warns:
        print(f"  WARN  {w}")
    for f in rep.fails:
        print(f"  FAIL  {f}")
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
